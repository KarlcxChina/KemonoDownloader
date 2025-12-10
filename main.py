import argparse
import json
import os
import platform
import time
from pathlib import Path
from typing import Dict, Iterable, Optional, List
from dataclasses import dataclass, field
import logging
import unicodedata
import re
import subprocess

import requests

# ---------------------------
# Logger 配置（基础 - 控制台）
# ---------------------------
logger = logging.getLogger("Kemono_downloader")
logger.setLevel(logging.DEBUG)

_console_handler = logging.StreamHandler()
_console_handler.setLevel(logging.INFO)
_console_formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s",
    "%Y-%m-%d %H:%M:%S",
)
_console_handler.setFormatter(_console_formatter)

if not logger.handlers:f
    logger.addHandler(_console_handler)


# ---------------------------
# 配置类 & 常量
# ---------------------------
@dataclass
class Config:
    postCounts: int = 0
    baseUrl: str = ""
    proxies: Optional[Dict[str, str]] = None
    maxRetries: int = 5
    baseBackoffFactor: float = 1.0
    targetOS: str = "windows"
    folder: str = ""
    embedCount: int = 0
    skipPic: List[str] = field(
        default_factory=lambda: [
            "/5e/46/5e46bc830d84fbad826963d2e2223f15fba27a05bef94814efa84e3bb3fcb7ef.png"
        ]
    )
    headers: Dict[str, str] = field(default_factory=lambda: {"accept": "text/css"})
    aria2_rpc_url: str = "http://localhost:6888/jsonrpc"


SMALL_RETRY_TIMES = 2
SMALL_RETRY_INTERVAL = 5

BIG_RETRY_TIMES = 5
BIG_RETRY_BASE_INTERVAL = 20

MAX_TOTAL_RETRY = BIG_RETRY_TIMES * (SMALL_RETRY_TIMES + 1)


# ---------------------------
# Aria2 RPC 相关
# ---------------------------
def aria2_rpc_call(
        method: str,
        params: list,
        aria2_rpc_url: str = "http://localhost:6888/jsonrpc",
        aria2_token: str | None = None,
):
    """通用 aria2 RPC 调用封装。"""
    rpc_params = []
    if aria2_token:
        rpc_params.append(f"token:{aria2_token}")
    rpc_params.extend(params)

    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": method,
        "params": rpc_params,
    }
    resp = requests.post(aria2_rpc_url, json=payload)
    resp.raise_for_status()
    return resp.json()


# ---------------------------
# 文件 / 下载相关
# ---------------------------
def cleanup_files(targetFolder: str, attachmentName: str):
    """删除目标文件及其 .aria2 临时文件。"""
    file_path = os.path.join(targetFolder, attachmentName)
    aria2_file = file_path + ".aria2"

    for f in (file_path, aria2_file):
        try:
            if os.path.exists(f):
                os.remove(f)
                logger.info(f"已删除文件: {f}")
        except Exception as e:
            logger.warning(f"删除文件 {f} 失败: {e}")


def downloadRes(
        path: str,
        server: str,
        attachmentName: str,
        targetFolder: str,
        aria2_rpc_url: str = "http://localhost:6888/jsonrpc",
        aria2_token: str = None,
) -> str:
    """
    使用 aria2 RPC 添加下载任务，返回 aria2 分配的 GID。
    """
    targetUrl = server.rstrip("/") + "/data" + path + "?f=" + attachmentName

    options = {
        "dir": targetFolder,
        "out": attachmentName,
    }

    params = []

    if aria2_token:
        params.append(f"token:{aria2_token}")

    params.append([targetUrl])
    params.append(options)

    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "aria2.addUri",
        "params": params,
    }

    response = requests.post(aria2_rpc_url, json=payload)
    response.raise_for_status()
    res_json = response.json()
    logger.info(f"Added aria2 task for {attachmentName} -> GID: {res_json.get('result')}")
    return res_json.get("result")


def saveRes(targetFolder: str, filename: str, picContent: bytes, config: Config):
    """
    将字节内容写入文件，文件名先做 sanitize。
    使用 config.targetOS 来决定 sanitize 风格。
    """
    filename = sanitizeFilenameAdvanced(filename, config.targetOS)
    if not os.path.exists(targetFolder):
        os.makedirs(targetFolder)
        logger.info(f"Created folder: {targetFolder}")

    filePath = os.path.join(targetFolder, filename)

    try:
        with open(filePath, "wb") as f:
            f.write(picContent)
        logger.info(f"Saved file: {filePath}")
    except IOError as e:
        logger.error(f"Error saving file {filePath}: {e}")
        raise Exception(f"Error saving file {filePath}: {e}")


# ---------------------------
# 批量附件下载任务结构 & 逻辑
# ---------------------------
@dataclass
class DownloadTask:
    gid: str
    attachment: dict
    targetFolder: str
    retry_count: int = 0


def submit_all_attachments(
        attachments: List[dict],
        targetFolder: str,
        config: Config,
) -> List[DownloadTask]:
    """
    先循环提交所有附件，记录 GID，返回 DownloadTask 列表。
    """
    tasks: List[DownloadTask] = []
    for attachment in attachments:
        attachmentName = attachment.get("name")
        path = attachment.get("path")
        server = attachment.get("server")

        try:
            gid = downloadRes(
                path,
                server,
                attachmentName,
                targetFolder,
                aria2_rpc_url=config.aria2_rpc_url,
                aria2_token=None,
            )
            logger.info(f"成功提交附件: {attachmentName}, GID={gid}")
            tasks.append(
                DownloadTask(
                    gid=gid,
                    attachment=attachment,
                    targetFolder=targetFolder,
                    retry_count=0,
                )
            )
        except Exception as e:
            logger.error(f"提交附件 {attachmentName} 到 Aria2 时失败: {e}")
    return tasks


def poll_and_retry_tasks(
        tasks: List[DownloadTask],
        config: Config,
        max_retries: int = MAX_TOTAL_RETRY,
        poll_interval: int = 3,
) -> bool:
    """
    轮询所有 GID 的状态：
      - 成功：从列表中移除，并提示下载成功；
      - 失败：从列表中移除，执行重试，将重试后的 GID 重新加入列表；
    直到所有任务都结束（成功或耗尽重试次数）。
    """
    active_tasks: List[DownloadTask] = list(tasks)
    all_success = True

    if not active_tasks:
        logger.info("没有附件需要下载。")
        return True

    logger.info(f"开始轮询下载任务，任务数量: {len(active_tasks)}")

    while active_tasks:
        for task in list(active_tasks):
            gid = task.gid
            attachment = task.attachment
            attachmentName = attachment.get("name")

            try:
                res = aria2_rpc_call(
                    "aria2.tellStatus",
                    [gid],
                    aria2_rpc_url=config.aria2_rpc_url,
                    aria2_token=None,
                )
                status = res.get("result", {}).get("status")
            except Exception as e:
                logger.error(f"查询 GID={gid} (附件 {attachmentName}) 状态失败: {e}")
                continue

            if status == "complete":
                logger.info(f"附件 {attachmentName} 下载完成 (GID={gid})")
                active_tasks.remove(task)


            elif status in ("error", "removed"):
                logger.warning(
                    f"附件 {attachmentName} 下载失败 (GID={gid})，当前重试次数: {task.retry_count}"
                )
                # 先从当前轮询列表中移除该任务
                active_tasks.remove(task)
                # 在重试之前，删除 aria2 中旧的任务记录
                try:
                    aria2_rpc_call(
                        "aria2.removeDownloadResult",
                        [gid],
                        aria2_rpc_url=config.aria2_rpc_url,
                        aria2_token=None,
                    )
                    logger.info(f"已从 aria2 中删除任务记录 (GID={gid})")
                except Exception as e:
                    # 删除失败不影响后续重试，只记录一下
                    logger.warning(f"从 aria2 删除任务记录失败 (GID={gid}): {e}")
                if task.retry_count >= max_retries:
                    logger.error(
                        f"附件 {attachmentName} 已耗尽最大重试次数 ({max_retries})，放弃下载。"
                    )
                    all_success = False
                    continue
                # 删除失败任务产生的文件（包括 .aria2）
                cleanup_files(task.targetFolder, attachmentName)
                # 计算退避时间
                if task.retry_count < SMALL_RETRY_TIMES:
                    backoff = SMALL_RETRY_INTERVAL
                else:
                    backoff = BIG_RETRY_BASE_INTERVAL * (
                            task.retry_count - SMALL_RETRY_TIMES + 1
                    )
                logger.info(
                    f"附件 {attachmentName} 将在 {backoff} 秒后重试 "
                    f"(当前重试次数: {task.retry_count + 1}/{max_retries})"
                )
                time.sleep(backoff)
                # 重新提交新的下载任务
                try:
                    new_gid = downloadRes(
                        attachment.get("path"),
                        attachment.get("server"),
                        attachmentName,
                        task.targetFolder,
                        aria2_rpc_url=config.aria2_rpc_url,
                        aria2_token=None,
                    )
                    logger.info(
                        f"已重新提交附件 {attachmentName}，新 GID={new_gid} "
                        f"(重试次数: {task.retry_count + 1})"
                    )
                    new_task = DownloadTask(
                        gid=new_gid,
                        attachment=attachment,
                        targetFolder=task.targetFolder,
                        retry_count=task.retry_count + 1,
                    )
                    active_tasks.append(new_task)
                except Exception as e:
                    logger.error(f"重试提交附件 {attachmentName} 到 Aria2 失败: {e}")
                    all_success = False
            else:
                logger.debug(
                    f"附件 {attachmentName} 状态: {status} (GID={gid})，继续等待..."
                )

        if active_tasks:
            time.sleep(poll_interval)

    logger.info("全部附件的下载任务已处理完毕。")
    return all_success


def process_attachments_batch(
        attachments: List[dict],
        postFolder: str,
        config: Config,
) -> bool:
    """
    对一个帖子里的所有附件：
      1. 先统一提交任务并记录 GID；
      2. 再统一轮询所有 GID 的状态并按需重试。
    """
    tasks = submit_all_attachments(attachments, postFolder, config)
    return poll_and_retry_tasks(tasks, config)


# ---------------------------
# 帖子抓取核心逻辑
# ---------------------------
def process_attachment(attachment, postFolder: str, config: Config):
    attachmentName = attachment.get("name")
    att_type = attachment.get("type")

    if att_type == "thumbnail":
        if attachment.get("name") == "https://mega.nz/rich-folder.png":
            config.skipPic.insert(0, attachment.get("path"))
        for i in config.skipPic:
            if i == attachment.get("path"):
                return f"跳过垃圾附件 (path: {i})"
        try:
            downloadRes(
                attachment.get("path"),
                attachment.get("server"),
                attachment.get("name"),
                postFolder,
                aria2_rpc_url=config.aria2_rpc_url,
                aria2_token=None,
            )
            return f"成功处理图片附件: {attachmentName}"
        except Exception as e:
            return f"处理图片附件 {attachmentName} 时发生错误: {e}"

    if att_type == "embed":
        urlContent = "[InternetShortcut]\nURL=" + attachment.get("url")
        bUrlContent = bytes(urlContent, encoding="utf8")
        subject = attachment.get("subject")
        saveRes(
            postFolder,
            "em" + str(config.embedCount) + "_" + subject + ".url",
            bUrlContent,
            config,
        )
        config.embedCount += 1
        return f"成功处理嵌入附件: {subject}"

    return f"跳过非图附件: {attachmentName} (类型: {att_type})"


def getPost(postID: str, userID: str, service: str, config: Config):
    """
    通过 config 提供的参数（baseUrl, proxies, headers, maxRetries, baseBackoffFactor, folder, targetOS, skipPic, embedCount）
    """
    url = config.baseUrl + service + "/user/" + userID + "/post/" + postID
    data = None

    for attempt in range(config.maxRetries):
        response = None
        data = None
        flag = False
        try:
            response = requests.get(
                url,
                proxies=config.proxies,
                headers=config.headers,
            )
            response.raise_for_status()
            flag = True

        except requests.exceptions.Timeout:
            logger.warning(f"获取帖子超时 (尝试 {attempt + 1}/{config.maxRetries}): {url}")
        except requests.exceptions.HTTPError as e:
            if e.response is not None and 500 <= e.response.status_code < 600:
                logger.warning(
                    f"获取帖子遭遇服务器错误 (HTTP {e.response.status_code}) "
                    f"(尝试 {attempt + 1}/{config.maxRetries}): {e}"
                )
            elif e.response.status_code == 429:
                logger.warning(
                    f"获取帖子遭遇服务器错误 (HTTP 429) "
                    f"(尝试 {attempt * 5}/{config.maxRetries}): {e}"
                )
            else:
                logger.error(
                    f"获取帖子失败 (HTTP {e.response.status_code if e.response else 'Unknown'})，不重试: {e}"
                )
                return None
        except requests.exceptions.RequestException as e:
            logger.warning(
                f"获取帖子时发生网络错误 (尝试 {attempt + 1}/{config.maxRetries}): {e}"
            )
        except Exception as e:
            logger.error(
                f"获取帖子时发生未知错误 (尝试 {attempt + 1}/{config.maxRetries}): {e}"
            )

        try:
            data = response.json()
            flag = True
        except json.JSONDecodeError as e:
            logger.warning(
                f"错误：无效的 JSON 字符串，可能是网络错误 "
                f"(尝试 {attempt + 1}/{config.maxRetries}): {e}"
            )
        except AttributeError as e:
            logger.warning(
                f"错误：JSON 对象结构不符合预期，可能是网络错误 "
                f"(尝试 {attempt + 1}/{config.maxRetries}): {e}"
            )

        if flag:
            break

        if attempt < config.maxRetries - 1:
            waitTime = config.baseBackoffFactor * (2 ** attempt)
            logger.info(f"将在 {waitTime:.2f} 秒后重试...")
            time.sleep(waitTime)
        else:
            logger.error(f"所有 {config.maxRetries} 次尝试获取帖子均失败。")
            return None

    if not data:
        logger.error("未收到有效数据，终止处理该帖子。")
        return None

    post = data.get("post")
    if not post:
        logger.error("返回的数据中没有 'post' 字段，跳过。")
        return None

    path = post.get("published")[2:10] + "_" + post.get("title") + "_" + post.get("id")
    path = sanitizeFilenameAdvanced(path, config.targetOS)
    postFolder = os.path.join(config.folder, path)
    logger.info(f"\n\n正在取帖子 {path}")

    if not os.path.exists(postFolder):
        os.makedirs(postFolder)
        logger.info(f"Created folder: {postFolder}")

    contentContent = post.get("content")

    if contentContent is not None and contentContent != "":
        contentContent = contentContent.replace('src="/', 'src="https://kemono.cr/')
        contentContent = f"""
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{post.get("title")}</title>
            <style>
                .container {{
                    width: 60%;
                    margin: 10% auto 0;
                    background-color: #f0f0f0;
                    padding: 2% 5%;
                    border-radius: 10px
                }}

                ul {{
                    padding-left: 20px;
                }}

                    ul li {{
                        line-height: 2.3
                    }}

                a {{
                    color: #20a53a
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Content of<br><br>{post.get("title")}</h1>
                {contentContent}
            </div>
        </body>
        </html>
        """
        contentPath = os.path.join(postFolder, "!Content.html")
        try:
            with open(contentPath, "w", encoding="utf-8") as file:
                file.write(contentContent)
            logger.info(f"内容已成功写入文件: {contentPath}")
        except IOError:
            logger.error(f"错误: 无法写入文件 {contentPath}")
        except Exception as e:
            logger.error(f"发生了一个预料之外的错误: {e}")

    logger.info(f"准备下载 {path}")

    config.embedCount = 0

    for attachment in data.get("previews", []):
        res = process_attachment(attachment, postFolder, config)
        logger.debug(f"process_attachment (preview) result: {res}")

    attachments = data.get("attachments", [])
    if attachments:
        all_success = process_attachments_batch(attachments, postFolder, config)
        if all_success:
            logger.info("所有一般附件均下载成功，继续执行后续操作")
        else:
            logger.error("存在附件下载失败（已按规则重试），继续执行后续操作时请注意处理失败情况")
    else:
        logger.info("该帖子没有一般附件。")

    return None


def getPostFromPage(
        userID: str,
        service: str,
        postBegins: int = 0,
        config: Config = None,
):
    if config is None:
        raise ValueError("config 必须提供给 getPostFromPage")

    if postBegins > 0:
        o = postBegins - 1
    else:
        o = 0
    while not o % 50 == 0:
        o -= 1

    profileUrl = config.baseUrl + service + "/user/" + userID + "/profile"

    response = None
    for attempt in range(config.maxRetries):
        response = None
        flag = False
        try:
            response = requests.get(
                profileUrl,
                proxies=config.proxies,
                headers=config.headers,
            )
            response.raise_for_status()
            flag = True

        except requests.exceptions.Timeout:
            logger.warning(
                f"获取页面超时 (尝试 {attempt + 1}/{config.maxRetries}): {profileUrl}"
            )
        except requests.exceptions.HTTPError as e:
            if e.response is not None and 500 <= e.response.status_code < 600:
                logger.warning(
                    f"获取页面遭遇服务器错误 (HTTP {e.response.status_code}) "
                    f"(尝试 {attempt + 1}/{config.maxRetries}): {e}"
                )
            elif e.response.status_code == 429:
                logger.warning(
                    f"获取帖子遭遇服务器错误 (HTTP 429) "
                    f"(尝试 {attempt * 5}/{config.maxRetries}): {e}"
                )
            else:
                logger.error(
                    f"获取页面失败 (HTTP {e.response.status_code if e.response else 'Unknown'})，不重试: {e}"
                )
                return None
        except requests.exceptions.RequestException as e:
            logger.warning(
                f"获取页面时发生网络错误 (尝试 {attempt + 1}/{config.maxRetries}): {e}"
            )
        except Exception as e:
            logger.error(
                f"获取页面时发生未知错误 (尝试 {attempt + 1}/{config.maxRetries}): {e}"
            )

        if flag:
            break

        if attempt < config.maxRetries - 1:
            waitTime = config.baseBackoffFactor * (2 ** attempt)
            logger.info(f"将在 {waitTime:.2f} 秒后重试...")
            time.sleep(waitTime)
        else:
            logger.error(f"所有 {config.maxRetries} 次尝试获取页面均失败。")
            return None

    try:
        resp_json = response.json()
    except Exception as e:
        logger.error(f"解析 profile JSON 失败: {e}")
        return None

    userName = service + "_" + resp_json.get("name", "unknown")
    if (not resp_json.get("public_id") is None) and (
            not resp_json.get("name") == resp_json.get("public_id")
    ):
        userName += "_" + resp_json.get("public_id")

    config.folder = os.path.join(config.folder, userName)

    count = o

    while True:
        if not config.postCounts == 0 and o + 1 > postBegins + config.postCounts - 1:
            logger.info(f"\n\n{config.postCounts}个帖子取完了…")
            return None

        logger.info(f"\n\n正在取{userName}的第{o + 1}到{o + 50}个帖子…")

        if o == 0:
            url = config.baseUrl + service + "/user/" + userID + "/posts"
        else:
            url = config.baseUrl + service + "/user/" + userID + "/posts?o=" + str(o)

        for attempt in range(config.maxRetries):
            response = None
            flag = False
            try:
                response = requests.get(
                    url,
                    proxies=config.proxies,
                    headers=config.headers,
                )
                response.raise_for_status()
                flag = True

            except requests.exceptions.Timeout:
                logger.warning(
                    f"获取页面超时 (尝试 {attempt + 1}/{config.maxRetries}): {url}"
                )
            except requests.exceptions.HTTPError as e:
                if e.response is not None and 500 <= e.response.status_code < 600:
                    logger.warning(
                        f"获取页面遭遇服务器错误 (HTTP {e.response.status_code}) "
                        f"(尝试 {attempt + 1}/{config.maxRetries}): {e}"
                    )
                elif e.response.status_code == 429:
                    logger.warning(
                        f"获取帖子遭遇服务器错误 (HTTP 429) "
                        f"(尝试 {attempt * 5}/{config.maxRetries}): {e}"
                    )
                else:
                    logger.error(
                        f"获取页面失败 (HTTP {e.response.status_code if e.response else 'Unknown'})，不重试: {e}"
                    )
                    return None
            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"获取页面时发生网络错误 (尝试 {attempt + 1}/{config.maxRetries}): {e}"
                )
            except Exception as e:
                logger.error(
                    f"获取页面时发生未知错误 (尝试 {attempt + 1}/{config.maxRetries}): {e}"
                )

            if flag:
                break

            if attempt < config.maxRetries - 1:
                waitTime = config.baseBackoffFactor * (2 ** attempt)
                logger.info(f"将在 {waitTime:.2f} 秒后重试...")
                time.sleep(waitTime)
            else:
                logger.error(f"所有 {config.maxRetries} 次尝试获取页面均失败。")
                return None

        if response.text == "[]":
            logger.info(f"\n\n{userName}的帖子取完了…")
            return o

        o += 50

        try:
            data = response.json()
        except json.JSONDecodeError:
            logger.warning("错误：无效的 JSON 字符串")
            return None
        except AttributeError:
            logger.warning("错误：JSON 对象结构不符合预期")
            return None

        for post in data:
            if count < postBegins - 1:
                count += 1
                continue
            if config.postCounts == 0 or count < postBegins + config.postCounts - 1:
                getPost(post.get("id"), post.get("user"), post.get("service"), config)
                time.sleep(3)
                count += 1
            else:
                logger.info(f"\n\n{config.postCounts}个帖子取完了…")
                return None


# ---------------------------
# 文件名清洗工具
# ---------------------------
def sanitizeFilenameAdvanced(
        filename: str,
        targetOS: str = "windows",
        default_replacement_char: str = "_",
        max_filename_length: int = 255,
        visual_similar_replacements: Dict[str, str] = None,
        reserved_names_windows: Iterable[str] = None,
) -> str:
    if not isinstance(filename, str):
        raise TypeError("输入文件名必须是字符串。")

    target = targetOS.lower()
    if target not in ("windows", "linux"):
        raise ValueError("targetOS 必须是 'windows' 或 'linux'。")

    if visual_similar_replacements is None:
        visual_similar_replacements = {
            "<": "＜",
            ">": "＞",
            ":": "∶",
            '"': "＂",
            "|": "｜",
            "?": "？",
            "*": "＊",
            "/": "-",
            "\\": "_",
        }

    if reserved_names_windows is None:
        reserved_names_windows = {
            "CON", "PRN", "AUX", "NUL",
            "COM1", "COM2", "COM3", "COM4",
            "COM5", "COM6", "COM7", "COM8", "COM9",
            "LPT1", "LPT2", "LPT3", "LPT4",
            "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
        }

    base = Path(filename).name
    base = unicodedata.normalize("NFKC", base)
    name_part, ext_part = os.path.splitext(base)

    name_part = re.sub(r"[\x00-\x1f\x7f]", default_replacement_char, name_part)
    name_part = "".join(
        ch if unicodedata.category(ch) != "Cf" else default_replacement_char
        for ch in name_part
    )

    processed_chars = []
    for ch in name_part:
        illegal = False
        if target == "windows":
            if ch in '<>:"/\\|?*':
                illegal = True
        else:
            if ch == "/":
                illegal = True

        if illegal:
            if ch in visual_similar_replacements:
                processed_chars.append(visual_similar_replacements[ch])
            else:
                processed_chars.append(default_replacement_char)
        else:
            processed_chars.append(ch)

    clean_name = "".join(processed_chars)
    clean_name = clean_name.lstrip(" ")
    if target == "windows":
        clean_name = clean_name.rstrip(" .")
    else:
        clean_name = clean_name.rstrip(" ")

    if target == "windows":
        if clean_name.upper() in reserved_names_windows:
            clean_name = default_replacement_char + clean_name

    ext = ext_part or ""
    max_name_len = max_filename_length - len(ext)
    if max_name_len <= 0:
        clean_name = default_replacement_char
        ext = ext[: max(0, max_filename_length - 1)]
    elif len(clean_name) > max_name_len:
        clean_name = clean_name[:max_name_len]

    final_name = clean_name + ext

    if not final_name or set(final_name) <= {"."}:
        return default_replacement_char

    return final_name


# ---------------------------
# CLI & 主入口
# ---------------------------
def parse_args():
    default_baseUrl = "https://kemono.cr/api/v1/"
    default_max_retries = 5
    default_base_backoff_factor = 3.0
    default_folder = os.getcwd()

    parser = argparse.ArgumentParser(
        description="脚本参数配置"
    )
    parser.add_argument("userid", help="需要下载的用户的ID (必填)")
    parser.add_argument("service", help="服务名称，如 fanbox/patreon (必填)")
    parser.add_argument(
        "--base_url",
        type=str,
        default=default_baseUrl,
        help=f"API基础URL (默认: {default_baseUrl})",
    )
    parser.add_argument(
        "--proxy_url",
        type=str,
        default=None,
        help="代理URL (例如: http://localhost:7897)。如果提供，将启用代理。",
    )
    parser.add_argument(
        "--max_retries",
        type=int,
        default=default_max_retries,
        help=f"页面访问最大工作重试次数 (默认: {default_max_retries})",
    )
    parser.add_argument(
        "--base_backoff_factor",
        type=float,
        default=default_base_backoff_factor,
        help=f"页面访问基准重试延迟时间 (默认: {default_base_backoff_factor})",
    )
    parser.add_argument(
        "--folder",
        type=str,
        default=default_folder,
        help=f"目标文件夹 (默认: 当前工作目录，{default_folder})",
    )
    parser.add_argument(
        "--post_begins",
        type=int,
        default=1,
        help="从该账户的第 N 个 post 开始（默认: 1）",
    )
    parser.add_argument(
        "--post_counts",
        type=int,
        default=0,
        help="取 N 个 post，0 或小于等于0 表示无限制（默认: 0）",
    )
    parser.add_argument(
        "--aria2-rpc-url",
        dest="aria2_rpc_url",
        type=str,
        default=None,
        help=(
            "Aria2 JSON-RPC 地址，例如: http://localhost:6888/jsonrpc 。"
            "如果未指定，将在脚本开始时运行本地 aria2c.exe (--conf-path=aria2.conf)。"
        ),
    )

    args = parser.parse_args()

    return args


def init_file_logger(folder: str):
    """
    在知道 folder 后，添加文件日志 handler。
    """
    file_log_path = os.path.join(folder, "kemono_downloader.log")

    existing_same_file_handler = any(
        isinstance(h, logging.FileHandler)
        and getattr(h, "baseFilename", None) == os.path.abspath(file_log_path)
        for h in logger.handlers
    )

    if not existing_same_file_handler:
        try:
            file_handler = logging.FileHandler(file_log_path, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(_console_formatter)
            logger.addHandler(file_handler)
            logger.debug(f"File log initialized at: {file_log_path}")
        except Exception as e:
            logger.warning(f"无法创建文件日志 {file_log_path}: {e}")


def detect_target_os() -> str:
    current_os = platform.system().lower()
    if "windows" in current_os:
        return "windows"
    if "linux" in current_os:
        return "linux"

    logger.warning(
        f"检测到不支持的操作系统 '{platform.system()}'。将使用 Windows 默认设置。"
    )
    return "windows"


def start_aria2_process(proxy_url: Optional[str]):
    """
    如果命令行未提供 RPC 地址，则在最开始启动 aria2c：
    Windows: .\\aria2c.exe --conf-path=aria2.conf [--all-proxy=...]
    其他:   ./aria2c    --conf-path=aria2.conf [--all-proxy=...]
    """
    if os.name == "nt":
        exe_path = ".\\aria2c.exe"
    else:
        exe_path = "./aria2c"

    cmd = [exe_path, "--conf-path=aria2.conf"]

    if proxy_url:
        cmd.append(f"--all-proxy={proxy_url}")

    try:
        subprocess.Popen(cmd)
        logger.info("已尝试启动本地 aria2c 进程: " + " ".join(cmd))
    except FileNotFoundError:
        logger.error(f"启动 aria2c 失败，未找到可执行文件: {exe_path}")
        quit()
    except Exception as e:
        logger.error(f"启动 aria2c 失败: {e}")
        quit()

    logger.info("现在可以直接用浏览器打开程序目录下的 AriaNg.html 文件查看下载进度。")


def main():
    args = parse_args()

    userid = args.userid
    service = args.service

    cfg = Config()
    cfg.baseUrl = args.base_url
    cfg.maxRetries = args.max_retries
    cfg.baseBackoffFactor = args.base_backoff_factor
    cfg.targetOS = detect_target_os()
    cfg.folder = args.folder

    postBegins = max(1, int(args.post_begins))
    cfg.postCounts = max(0, int(args.post_counts))

    # 仅根据 proxy_url 判断是否使用代理
    if args.proxy_url:
        currentProxyUrlStr: Optional[str] = args.proxy_url
        cfg.proxies = {
            "http": currentProxyUrlStr,
            "https": currentProxyUrlStr,
        }
    else:
        currentProxyUrlStr = None
        cfg.proxies = None

    # 配置 Aria2 RPC 地址 & 启动 aria2c（如需要）
    if args.aria2_rpc_url:
        cfg.aria2_rpc_url = args.aria2_rpc_url
    else:
        cfg.aria2_rpc_url = "http://localhost:6888/jsonrpc"
        start_aria2_process(currentProxyUrlStr)

    init_file_logger(cfg.folder)

    logger.info("\n---- 配置来咯 ----")
    logger.info(f"User ID: {userid}")
    logger.info(f"Service: {service}")
    logger.info(f"Base URL: {cfg.baseUrl}")
    logger.info(f"MAX_RETRIES: {cfg.maxRetries}")
    logger.info(f"Base Backoff Factor: {cfg.baseBackoffFactor}")
    if cfg.proxies:
        logger.info("Proxy Enabled: True")
        logger.info(f"Proxy URL: {currentProxyUrlStr}")
        logger.info(f"Proxies: {cfg.proxies}")
    else:
        logger.info("Proxy Enabled: False")
    logger.info(f"Aria2 RPC URL: {cfg.aria2_rpc_url}")
    logger.info(f"Target OS: {cfg.targetOS}")
    logger.info(f"Folder: {cfg.folder}")
    logger.info(f"post begins: {postBegins}")
    logger.info(f"post counts: {cfg.postCounts}")
    logger.info("-------------------\n")

    logger.info("\n---- 抓取开始咯 ----")

    getPostFromPage(userid, service, postBegins, cfg)


if __name__ == "__main__":
    main()
