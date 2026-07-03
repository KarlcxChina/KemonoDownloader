import argparse
import atexit
import html
import json
import locale
import os
import platform
import signal
import time
from typing import Dict, Iterable, Optional, List
from dataclasses import dataclass, field
import logging
import unicodedata
import re
import subprocess
from urllib.parse import urlencode, urlparse

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

if not logger.handlers:
    logger.addHandler(_console_handler)


# ---------------------------
# I18N
# ---------------------------
def detect_language() -> str:
    """Return zh for Chinese environments, otherwise en."""
    override = os.environ.get("KEMONO_DOWNLOADER_LANG", "").strip().lower()
    if override:
        if override.startswith("zh") or override in ("cn", "chinese", "chs", "cht"):
            return "zh"
        return "en"

    candidates = []
    for env_name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(env_name)
        if value:
            candidates.append(value)

    for getter in (locale.getlocale, getattr(locale, "getdefaultlocale", None)):
        if getter is None:
            continue
        try:
            locale_value = getter()
        except Exception:
            continue

        if isinstance(locale_value, tuple):
            candidates.extend(str(part) for part in locale_value if part)
        elif locale_value:
            candidates.append(str(locale_value))

    try:
        candidates.append(locale.getencoding())
    except AttributeError:
        pass

    normalized_candidates = [
        candidate.strip().replace("-", "_").lower()
        for candidate in candidates
        if candidate
    ]
    return "zh" if any(
        candidate.startswith("zh")
        or "chinese" in candidate
        or "中文" in candidate
        or "汉语" in candidate
        or "漢語" in candidate
        or candidate in ("chs", "cht")
        for candidate in normalized_candidates
    ) else "en"


LANGUAGE = detect_language()


def i18n(zh: str, en: str) -> str:
    return zh if LANGUAGE == "zh" else en


ARGPARSE_ZH_TRANSLATIONS = {
    "usage: ": "用法: ",
    "positional arguments": "位置参数",
    "options": "选项",
    "optional arguments": "可选参数",
    "show this help message and exit": "显示帮助信息并退出",
    "the following arguments are required: %s": "缺少必需参数: %s",
    "unrecognized arguments: %s": "无法识别的参数: %s",
    "argument %(argument_name)s: %(message)s": "参数 %(argument_name)s: %(message)s",
    "invalid %(type)s value: %(value)r": "无效的 %(type)s 值: %(value)r",
    "expected one argument": "需要一个参数",
    "expected at most one argument": "最多需要一个参数",
    "expected at least one argument": "至少需要一个参数",
    "expected %s argument": "需要 %s 个参数",
    "expected %s arguments": "需要 %s 个参数",
}


def argparse_gettext(message: str) -> str:
    if LANGUAGE != "zh":
        return message
    return ARGPARSE_ZH_TRANSLATIONS.get(message, message)


def configure_argparse_language() -> None:
    argparse._ = argparse_gettext


# ---------------------------
# 配置类 & 常量
# ---------------------------
LOCAL_ARIA2_RPC_URL = "http://localhost:6888/jsonrpc"
ARIANG_OFFICIAL_DEMO_BASE_URL = "https://ariang.mayswind.net/latest"


@dataclass
class Config:
    postCounts: int = 0
    baseUrl: str = ""
    fileServer: str = ""
    kemonoMode: bool = False
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
    headers: Dict[str, str] = field(
        default_factory=lambda: {
            "accept": "text/css",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0"
            ),
        }
    )
    aria2_rpc_url: str = LOCAL_ARIA2_RPC_URL


SMALL_RETRY_TIMES = 2
SMALL_RETRY_INTERVAL = 5

BIG_RETRY_TIMES = 5
BIG_RETRY_BASE_INTERVAL = 20

MAX_TOTAL_RETRY = BIG_RETRY_TIMES * (SMALL_RETRY_TIMES + 1)

_local_aria2_process: Optional[subprocess.Popen] = None
_local_aria2_rpc_url: Optional[str] = None
_local_aria2_cleanup_started = False


def build_ariang_rpc_setup_url(aria2_rpc_url: str) -> str:
    parsed_url = urlparse(aria2_rpc_url)
    protocol = parsed_url.scheme or "http"
    host = parsed_url.hostname or "localhost"
    port = parsed_url.port or (443 if protocol in ("https", "wss") else 80)
    rpc_interface = parsed_url.path.strip("/") or "jsonrpc"
    query = urlencode(
        {
            "protocol": protocol,
            "host": host,
            "port": str(port),
            "interface": rpc_interface,
        }
    )
    return f"{ARIANG_OFFICIAL_DEMO_BASE_URL}/#!/settings/rpc/set?{query}"


def get_site_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/") + "/"
    api_suffix = "api/v1/"
    if normalized.endswith(api_suffix):
        return normalized[:-len(api_suffix)]
    return normalized


def build_kemono_referer(
        config: Config,
        service: str,
        userID: str,
        postID: str | None = None,
) -> str:
    user_page = f"{get_site_base_url(config.baseUrl)}{service}/user/{userID}"
    if postID:
        return f"{user_page}/post/{postID}"
    return user_page


def build_request_headers(config: Config, referer: str | None = None) -> Dict[str, str]:
    headers = dict(config.headers)
    if referer:
        headers["Referer"] = referer
    return headers


def get_attachment_server(attachment: dict, config: Config) -> str:
    if config.kemonoMode:
        return attachment.get("server")
    return config.fileServer


# ---------------------------
# Aria2 RPC 相关
# ---------------------------
def aria2_rpc_call(
        method: str,
        params: list,
        aria2_rpc_url: str = "http://localhost:6888/jsonrpc",
        aria2_token: str | None = None,
        timeout: float | None = None,
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
    resp = requests.post(aria2_rpc_url, json=payload, timeout=timeout)
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
                logger.info(i18n(f"已删除文件: {f}", f"Deleted file: {f}"))
        except Exception as e:
            logger.warning(i18n(f"删除文件 {f} 失败: {e}", f"Failed to delete file {f}: {e}"))


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
    logger.info(i18n(
        f"已添加 aria2 任务: {attachmentName} -> GID: {res_json.get('result')}",
        f"Added aria2 task for {attachmentName} -> GID: {res_json.get('result')}",
    ))
    return res_json.get("result")


def saveRes(targetFolder: str, filename: str, picContent: bytes, config: Config):
    """
    将字节内容写入文件，文件名先做 sanitize。
    使用 config.targetOS 来决定 sanitize 风格。
    """
    filename = sanitizeFilenameAdvanced(filename, config.targetOS)
    if not os.path.exists(targetFolder):
        os.makedirs(targetFolder)
        logger.info(i18n(f"已创建文件夹: {targetFolder}", f"Created folder: {targetFolder}"))

    filePath = os.path.join(targetFolder, filename)

    try:
        with open(filePath, "wb") as f:
            f.write(picContent)
        logger.info(i18n(f"已保存文件: {filePath}", f"Saved file: {filePath}"))
    except IOError as e:
        message = i18n(
            f"保存文件 {filePath} 时发生错误: {e}",
            f"Error saving file {filePath}: {e}",
        )
        logger.error(message)
        raise Exception(message)


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
        raw_name = str(attachment.get("name"))
        attachmentName = sanitizeFilenameAdvanced(raw_name, config.targetOS)
        path = attachment.get("path")
        server = get_attachment_server(attachment, config)

        try:
            gid = downloadRes(
                path,
                server,
                attachmentName,
                targetFolder,
                aria2_rpc_url=config.aria2_rpc_url,
                aria2_token=None,
            )
            logger.info(i18n(
                f"成功提交附件: {attachmentName}, GID={gid}",
                f"Submitted attachment: {attachmentName}, GID={gid}",
            ))
            tasks.append(
                DownloadTask(
                    gid=gid,
                    attachment=attachment,
                    targetFolder=targetFolder,
                    retry_count=0,
                )
            )
        except Exception as e:
            logger.error(i18n(
                f"提交附件 {attachmentName} 到 Aria2 时失败: {e}",
                f"Failed to submit attachment {attachmentName} to Aria2: {e}",
            ))
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
        logger.info(i18n("没有附件需要下载。", "No attachments to download."))
        return True

    logger.info(i18n(
        f"开始等待下载任务完成，任务数量: {len(active_tasks)}",
        f"Waiting for download tasks to complete. Task count: {len(active_tasks)}",
    ))

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
                logger.error(i18n(
                    f"查询 GID={gid} (附件 {attachmentName}) 状态失败: {e}",
                    f"Failed to query status for GID={gid} (attachment {attachmentName}): {e}",
                ))
                continue

            if status == "complete":
                logger.info(i18n(
                    f"附件 {attachmentName} 下载完成 (GID={gid})",
                    f"Attachment {attachmentName} download completed (GID={gid})",
                ))
                active_tasks.remove(task)


            elif status in ("error", "removed"):
                logger.warning(
                    i18n(
                        f"附件 {attachmentName} 下载失败 (GID={gid})，当前重试次数: {task.retry_count}",
                        f"Attachment {attachmentName} download failed (GID={gid}); current retry count: {task.retry_count}",
                    )
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
                    logger.info(i18n(
                        f"已从 aria2 中删除任务记录 (GID={gid})",
                        f"Removed download record from aria2 (GID={gid})",
                    ))
                except Exception as e:
                    # 删除失败不影响后续重试，只记录一下
                    logger.warning(i18n(
                        f"从 aria2 删除任务记录失败 (GID={gid}): {e}",
                        f"Failed to remove download record from aria2 (GID={gid}): {e}",
                    ))
                if task.retry_count >= max_retries:
                    logger.error(
                        i18n(
                            f"附件 {attachmentName} 已耗尽最大重试次数 ({max_retries})，放弃下载。",
                            f"Attachment {attachmentName} reached the maximum retry count ({max_retries}); giving up.",
                        )
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
                    i18n(
                        f"附件 {attachmentName} 将在 {backoff} 秒后重试 "
                        f"(当前重试次数: {task.retry_count + 1}/{max_retries})",
                        f"Attachment {attachmentName} will retry in {backoff} seconds "
                        f"(retry {task.retry_count + 1}/{max_retries})",
                    )
                )
                time.sleep(backoff)
                # 重新提交新的下载任务
                try:
                    new_gid = downloadRes(
                        attachment.get("path"),
                        get_attachment_server(attachment, config),
                        attachmentName,
                        task.targetFolder,
                        aria2_rpc_url=config.aria2_rpc_url,
                        aria2_token=None,
                    )
                    logger.info(
                        i18n(
                            f"已重新提交附件 {attachmentName}，新 GID={new_gid} "
                            f"(重试次数: {task.retry_count + 1})",
                            f"Resubmitted attachment {attachmentName}; new GID={new_gid} "
                            f"(retry count: {task.retry_count + 1})",
                        )
                    )
                    new_task = DownloadTask(
                        gid=new_gid,
                        attachment=attachment,
                        targetFolder=task.targetFolder,
                        retry_count=task.retry_count + 1,
                    )
                    active_tasks.append(new_task)
                except Exception as e:
                    logger.error(i18n(
                        f"重试提交附件 {attachmentName} 到 Aria2 失败: {e}",
                        f"Failed to resubmit attachment {attachmentName} to Aria2: {e}",
                    ))
                    all_success = False
            else:
                logger.debug(
                    i18n(
                        f"附件 {attachmentName} 状态: {status} (GID={gid})，继续等待...",
                        f"Attachment {attachmentName} status: {status} (GID={gid}); waiting...",
                    )
                )

        if active_tasks:
            time.sleep(poll_interval)

    logger.info(i18n(
        "全部附件的下载任务已处理完毕。",
        "All attachment download tasks have been processed.",
    ))
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
    raw_name = str(attachment.get("name"))
    attachmentName = sanitizeFilenameAdvanced(raw_name, config.targetOS)
    att_type = attachment.get("type")

    if att_type == "thumbnail":
        if attachment.get("name") == "https://mega.nz/rich-folder.png":
            config.skipPic.insert(0, attachment.get("path"))
        for i in config.skipPic:
            if i == attachment.get("path"):
                return i18n(f"跳过垃圾附件 (path: {i})", f"Skipped junk attachment (path: {i})")
        try:
            downloadRes(
                attachment.get("path"),
                get_attachment_server(attachment, config),
                attachment.get("name"),
                postFolder,
                aria2_rpc_url=config.aria2_rpc_url,
                aria2_token=None,
            )
            return i18n(
                f"成功处理图片附件: {attachmentName}",
                f"Processed image attachment successfully: {attachmentName}",
            )
        except Exception as e:
            return i18n(
                f"处理图片附件 {attachmentName} 时发生错误: {e}",
                f"Error while processing image attachment {attachmentName}: {e}",
            )

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
        return i18n(f"成功处理嵌入附件: {subject}", f"Processed embed attachment successfully: {subject}")

    return i18n(
        f"跳过非图附件: {attachmentName} (类型: {att_type})",
        f"Skipped non-image attachment: {attachmentName} (type: {att_type})",
    )


def getPost(postID: str, userID: str, service: str, config: Config):
    """
    通过 config 提供的参数（baseUrl, proxies, headers, maxRetries, baseBackoffFactor, folder, targetOS, skipPic, embedCount）
    """
    url = config.baseUrl + service + "/user/" + userID + "/post/" + postID
    headers = build_request_headers(
        config,
        referer=build_kemono_referer(config, service, userID, postID),
    )
    data = None

    for attempt in range(config.maxRetries):
        response = None
        data = None
        flag = False
        try:
            response = requests.get(
                url,
                proxies=config.proxies,
                headers=headers,
            )
            response.raise_for_status()
            flag = True

        except requests.exceptions.Timeout:
            logger.warning(i18n(
                f"获取帖子超时 (尝试 {attempt + 1}/{config.maxRetries}): {url}",
                f"Timed out while fetching post (attempt {attempt + 1}/{config.maxRetries}): {url}",
            ))
        except requests.exceptions.HTTPError as e:
            if e.response is not None and 500 <= e.response.status_code < 600:
                logger.warning(
                    i18n(
                        f"获取帖子遭遇服务器错误 (HTTP {e.response.status_code}) "
                        f"(尝试 {attempt + 1}/{config.maxRetries}): {e}",
                        f"Server error while fetching post (HTTP {e.response.status_code}) "
                        f"(attempt {attempt + 1}/{config.maxRetries}): {e}",
                    )
                )
            elif e.response.status_code == 429:
                logger.warning(
                    i18n(
                        f"获取帖子遭遇服务器错误 (HTTP 429) "
                        f"(尝试 {attempt * 5}/{config.maxRetries}): {e}",
                        f"Rate limited while fetching post (HTTP 429) "
                        f"(attempt {attempt * 5}/{config.maxRetries}): {e}",
                    )
                )
            else:
                logger.error(
                    i18n(
                        f"获取帖子失败 (HTTP {e.response.status_code if e.response else 'Unknown'})，不重试: {e}",
                        f"Failed to fetch post (HTTP {e.response.status_code if e.response else 'Unknown'}); not retrying: {e}",
                    )
                )
                return None
        except requests.exceptions.RequestException as e:
            logger.warning(
                i18n(
                    f"获取帖子时发生网络错误 (尝试 {attempt + 1}/{config.maxRetries}): {e}",
                    f"Network error while fetching post (attempt {attempt + 1}/{config.maxRetries}): {e}",
                )
            )
        except Exception as e:
            logger.error(
                i18n(
                    f"获取帖子时发生未知错误 (尝试 {attempt + 1}/{config.maxRetries}): {e}",
                    f"Unexpected error while fetching post (attempt {attempt + 1}/{config.maxRetries}): {e}",
                )
            )

        try:
            data = response.json()
            flag = True
        except json.JSONDecodeError as e:
            logger.warning(
                i18n(
                    f"错误：无效的 JSON 字符串，可能是网络错误 "
                    f"(尝试 {attempt + 1}/{config.maxRetries}): {e}",
                    f"Error: invalid JSON, possibly due to a network issue "
                    f"(attempt {attempt + 1}/{config.maxRetries}): {e}",
                )
            )
        except AttributeError as e:
            logger.warning(
                i18n(
                    f"错误：JSON 对象结构不符合预期，可能是网络错误 "
                    f"(尝试 {attempt + 1}/{config.maxRetries}): {e}",
                    f"Error: unexpected JSON object structure, possibly due to a network issue "
                    f"(attempt {attempt + 1}/{config.maxRetries}): {e}",
                )
            )

        if flag:
            break

        if attempt < config.maxRetries - 1:
            waitTime = config.baseBackoffFactor * (2 ** attempt)
            logger.info(i18n(
                f"将在 {waitTime:.2f} 秒后重试...",
                f"Retrying in {waitTime:.2f} seconds...",
            ))
            time.sleep(waitTime)
        else:
            logger.error(i18n(
                f"所有 {config.maxRetries} 次尝试获取帖子均失败。",
                f"All {config.maxRetries} attempts to fetch the post failed.",
            ))
            return None

    if not data:
        logger.error(i18n(
            "未收到有效数据，终止处理该帖子。",
            "No valid data was received; stopping this post.",
        ))
        return None

    if config.kemonoMode:
        post = data.get("post")
        if not post:
            logger.error(i18n(
                "返回的数据中没有 'post' 字段，跳过。",
                "The returned data does not contain a 'post' field; skipping.",
            ))
            return None
    else:
        post = data

    path = post.get("published")[2:10] + "_" + post.get("title") + "_" + post.get("id")
    path = sanitizeFilenameAdvanced(path, config.targetOS)
    postFolder = os.path.join(config.folder, path)
    logger.info(i18n(f"\n\n正在取帖子 {path}", f"\n\nFetching post {path}"))

    if not os.path.exists(postFolder):
        os.makedirs(postFolder)
        logger.info(i18n(f"已创建文件夹: {postFolder}", f"Created folder: {postFolder}"))

    contentContent = post.get("content")

    if contentContent is not None and contentContent != "":
        site_base_url = get_site_base_url(config.baseUrl)
        content_html = contentContent.replace('src="/', f'src="{site_base_url}')
        content_html = content_html.replace('href="/', f'href="{site_base_url}')
        title = str(post.get("title") or "Untitled")
        escaped_title = html.escape(title)
        contentContent = f"""
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>{escaped_title}</title>
            <style>
                :root {{
                    color-scheme: light;
                    --text: #1f2937;
                    --accent: #238636;
                }}

                * {{
                    box-sizing: border-box;
                }}

                body {{
                    margin: 0;
                    min-height: 100vh;
                    color: var(--text);
                    font-family:
                        "Segoe UI",
                        "Noto Sans CJK SC",
                        "Noto Sans JP",
                        "Microsoft YaHei",
                        sans-serif;
                }}

                .container {{
                    width: min(920px, calc(100% - 32px));
                    margin: 48px auto;
                    padding: 24px 16px 48px;
                }}

                .page-header {{
                    margin-bottom: 28px;
                }}

                h1 {{
                    margin: 0;
                    font-size: clamp(22px, 3vw, 30px);
                    line-height: 1.35;
                    font-weight: 700;
                }}

                .post-content {{
                    white-space: pre-line;
                    overflow-wrap: break-word;
                    font-size: 17px;
                    line-height: 1.9;
                }}

                ul {{
                    padding-left: 20px;
                }}

                ul li {{
                    line-height: 2.1;
                }}

                a {{
                    color: var(--accent);
                    text-decoration-thickness: 0.08em;
                    text-underline-offset: 0.16em;
                }}

                img,
                video {{
                    display: block;
                    max-width: 100%;
                    height: auto;
                    margin: 24px auto;
                    border-radius: 6px;
                }}

                blockquote {{
                    margin: 24px 0;
                    padding: 0;
                    color: #667085;
                }}

                @media (max-width: 700px) {{
                    .container {{
                        width: 100%;
                        margin: 0;
                        padding: 24px 18px 40px;
                    }}

                    .page-header {{
                        margin-bottom: 24px;
                    }}

                    .post-content {{
                        font-size: 16px;
                        line-height: 1.85;
                    }}
                }}
            </style>
        </head>
        <body>
            <article class="container">
                <header class="page-header">
                    <h1>{escaped_title}</h1>
                </header>
                <main class="post-content">{content_html}</main>
            </article>
        </body>
        </html>
        """
        contentPath = os.path.join(postFolder, "!Content.html")
        try:
            with open(contentPath, "w", encoding="utf-8") as file:
                file.write(contentContent)
            logger.info(i18n(
                f"内容已成功写入文件: {contentPath}",
                f"Content written successfully: {contentPath}",
            ))
        except IOError:
            logger.error(i18n(
                f"错误: 无法写入文件 {contentPath}",
                f"Error: unable to write file {contentPath}",
            ))
        except Exception as e:
            logger.error(i18n(
                f"发生了一个预料之外的错误: {e}",
                f"An unexpected error occurred: {e}",
            ))

    logger.info(i18n(f"准备下载 {path}", f"Preparing downloads for {path}"))

    config.embedCount = 0

    for attachment in data.get("previews", []):
        res = process_attachment(attachment, postFolder, config)
        logger.debug(f"process_attachment (preview) result: {res}")

    attachments = data.get("attachments", [])
    if attachments:
        all_success = process_attachments_batch(attachments, postFolder, config)
        if all_success:
            logger.info(i18n(
                "所有一般附件均下载成功，继续执行后续操作",
                "All regular attachments downloaded successfully; continuing.",
            ))
        else:
            logger.error(i18n(
                "存在附件下载失败（已按规则重试），继续执行后续操作时请注意处理失败情况",
                "Some attachments failed after retries; continuing, but please review the failures.",
            ))
    else:
        logger.info(i18n("该帖子没有一般附件。", "This post has no regular attachments."))

    return None


def getPostFromPage(
        userID: str,
        service: str,
        postBegins: int = 0,
        config: Config = None,
):
    if config is None:
        raise ValueError(i18n(
            "config 必须提供给 getPostFromPage",
            "config must be provided to getPostFromPage",
        ))

    if postBegins > 0:
        o = postBegins - 1
    else:
        o = 0
    while not o % 50 == 0:
        o -= 1

    profileUrl = config.baseUrl + service + "/user/" + userID + "/profile"
    user_page_headers = build_request_headers(
        config,
        referer=build_kemono_referer(config, service, userID),
    )

    response = None
    for attempt in range(config.maxRetries):
        response = None
        flag = False
        try:
            response = requests.get(
                profileUrl,
                proxies=config.proxies,
                headers=user_page_headers,
            )
            response.raise_for_status()
            flag = True

        except requests.exceptions.Timeout:
            logger.warning(
                i18n(
                    f"获取页面超时 (尝试 {attempt + 1}/{config.maxRetries}): {profileUrl}",
                    f"Timed out while fetching page (attempt {attempt + 1}/{config.maxRetries}): {profileUrl}",
                )
            )
        except requests.exceptions.HTTPError as e:
            if e.response is not None and 500 <= e.response.status_code < 600:
                logger.warning(
                    i18n(
                        f"获取页面遭遇服务器错误 (HTTP {e.response.status_code}) "
                        f"(尝试 {attempt + 1}/{config.maxRetries}): {e}",
                        f"Server error while fetching page (HTTP {e.response.status_code}) "
                        f"(attempt {attempt + 1}/{config.maxRetries}): {e}",
                    )
                )
            elif e.response.status_code == 429:
                logger.warning(
                    i18n(
                        f"获取帖子遭遇服务器错误 (HTTP 429) "
                        f"(尝试 {attempt * 5}/{config.maxRetries}): {e}",
                        f"Rate limited while fetching posts (HTTP 429) "
                        f"(attempt {attempt * 5}/{config.maxRetries}): {e}",
                    )
                )
            else:
                logger.error(
                    i18n(
                        f"获取页面失败 (HTTP {e.response.status_code if e.response else 'Unknown'})，不重试: {e}",
                        f"Failed to fetch page (HTTP {e.response.status_code if e.response else 'Unknown'}); not retrying: {e}",
                    )
                )
                return None
        except requests.exceptions.RequestException as e:
            logger.warning(
                i18n(
                    f"获取页面时发生网络错误 (尝试 {attempt + 1}/{config.maxRetries}): {e}",
                    f"Network error while fetching page (attempt {attempt + 1}/{config.maxRetries}): {e}",
                )
            )
        except Exception as e:
            logger.error(
                i18n(
                    f"获取页面时发生未知错误 (尝试 {attempt + 1}/{config.maxRetries}): {e}",
                    f"Unexpected error while fetching page (attempt {attempt + 1}/{config.maxRetries}): {e}",
                )
            )

        if flag:
            break

        if attempt < config.maxRetries - 1:
            waitTime = config.baseBackoffFactor * (2 ** attempt)
            logger.info(i18n(
                f"将在 {waitTime:.2f} 秒后重试...",
                f"Retrying in {waitTime:.2f} seconds...",
            ))
            time.sleep(waitTime)
        else:
            logger.error(i18n(
                f"所有 {config.maxRetries} 次尝试获取页面均失败。",
                f"All {config.maxRetries} attempts to fetch the page failed.",
            ))
            return None

    try:
        resp_json = response.json()
    except Exception as e:
        logger.error(i18n(f"解析 profile JSON 失败: {e}", f"Failed to parse profile JSON: {e}"))
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
            logger.info(i18n(
                f"\n\n{config.postCounts}个帖子取完了…",
                f"\n\nFinished fetching {config.postCounts} posts.",
            ))
            return None

        logger.info(i18n(
            f"\n\n正在取{userName}的第{o + 1}到{o + 50}个帖子…",
            f"\n\nFetching posts {o + 1} to {o + 50} for {userName}...",
        ))

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
                    headers=user_page_headers,
                )
                response.raise_for_status()
                flag = True

            except requests.exceptions.Timeout:
                logger.warning(
                    i18n(
                        f"获取页面超时 (尝试 {attempt + 1}/{config.maxRetries}): {url}",
                        f"Timed out while fetching page (attempt {attempt + 1}/{config.maxRetries}): {url}",
                    )
                )
            except requests.exceptions.HTTPError as e:
                if e.response is not None and 500 <= e.response.status_code < 600:
                    logger.warning(
                        i18n(
                            f"获取页面遭遇服务器错误 (HTTP {e.response.status_code}) "
                            f"(尝试 {attempt + 1}/{config.maxRetries}): {e}",
                            f"Server error while fetching page (HTTP {e.response.status_code}) "
                            f"(attempt {attempt + 1}/{config.maxRetries}): {e}",
                        )
                    )
                elif e.response.status_code == 429:
                    logger.warning(
                        i18n(
                            f"获取帖子遭遇服务器错误 (HTTP 429) "
                            f"(尝试 {attempt * 5}/{config.maxRetries}): {e}",
                            f"Rate limited while fetching posts (HTTP 429) "
                            f"(attempt {attempt * 5}/{config.maxRetries}): {e}",
                        )
                    )
                else:
                    logger.error(
                        i18n(
                            f"获取页面失败 (HTTP {e.response.status_code if e.response else 'Unknown'})，不重试: {e}",
                            f"Failed to fetch page (HTTP {e.response.status_code if e.response else 'Unknown'}); not retrying: {e}",
                        )
                    )
                    return None
            except requests.exceptions.RequestException as e:
                logger.warning(
                    i18n(
                        f"获取页面时发生网络错误 (尝试 {attempt + 1}/{config.maxRetries}): {e}",
                        f"Network error while fetching page (attempt {attempt + 1}/{config.maxRetries}): {e}",
                    )
                )
            except Exception as e:
                logger.error(
                    i18n(
                        f"获取页面时发生未知错误 (尝试 {attempt + 1}/{config.maxRetries}): {e}",
                        f"Unexpected error while fetching page (attempt {attempt + 1}/{config.maxRetries}): {e}",
                    )
                )

            if flag:
                break

            if attempt < config.maxRetries - 1:
                waitTime = config.baseBackoffFactor * (2 ** attempt)
                logger.info(i18n(
                    f"将在 {waitTime:.2f} 秒后重试...",
                    f"Retrying in {waitTime:.2f} seconds...",
                ))
                time.sleep(waitTime)
            else:
                logger.error(i18n(
                    f"所有 {config.maxRetries} 次尝试获取页面均失败。",
                    f"All {config.maxRetries} attempts to fetch the page failed.",
                ))
                return None

        if response.text == "[]":
            logger.info(i18n(
                f"\n\n{userName}的帖子取完了…",
                f"\n\nFinished fetching posts for {userName}.",
            ))
            return o

        o += 50

        try:
            data = response.json()
        except json.JSONDecodeError:
            logger.warning(i18n("错误：无效的 JSON 字符串", "Error: invalid JSON string"))
            return None
        except AttributeError:
            logger.warning(i18n(
                "错误：JSON 对象结构不符合预期",
                "Error: unexpected JSON object structure",
            ))
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
                logger.info(i18n(
                    f"\n\n{config.postCounts}个帖子取完了…",
                    f"\n\nFinished fetching {config.postCounts} posts.",
                ))
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
        raise TypeError(i18n("输入文件名必须是字符串。", "filename must be a string."))

    target = targetOS.lower()
    if target not in ("windows", "linux"):
        raise ValueError(i18n(
            "targetOS 必须是 'windows' 或 'linux'。",
            "targetOS must be 'windows' or 'linux'.",
        ))

    if visual_similar_replacements is None:
        visual_similar_replacements = {
            "<": "＜",
            ">": "＞",
            ":": "：",
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

    base = filename
    base = unicodedata.normalize("NFKC", base)

    processed_chars = []
    for ch in base:
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

    clean_base = "".join(processed_chars)
    name_part, ext_part = os.path.splitext(clean_base)

    clean_name = name_part.lstrip(" ")
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
def parse_bool_arg(value):
    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()
    if normalized in ("1", "true", "yes", "y", "on"):
        return True
    if normalized in ("0", "false", "no", "n", "off"):
        return False
    raise argparse.ArgumentTypeError(i18n("需要布尔值: true/false", "Expected a boolean value: true/false"))


def parse_args():
    configure_argparse_language()

    default_baseUrl = "https://pawchive.st/"
    default_fileServer = "https://file.pawchive.st/"
    default_max_retries = 5
    default_base_backoff_factor = 3.0
    default_folder = os.getcwd()

    parser = argparse.ArgumentParser(
        description=i18n("脚本参数配置", "Script parameter configuration")
    )
    parser.add_argument(
        "userid",
        help=i18n("需要下载的用户的ID (必填)", "Target user ID (required)"),
    )
    parser.add_argument(
        "service",
        help=i18n("服务名称，如 fanbox/patreon (必填)", "Service name, such as fanbox/patreon (required)"),
    )
    parser.add_argument(
        "--base_url",
        type=str,
        default=default_baseUrl,
        help=i18n(
            f"API基础URL (默认: {default_baseUrl})",
            f"API base URL (default: {default_baseUrl})",
        ),
    )
    parser.add_argument(
        "--file_server",
        type=str,
        default=default_fileServer,
        help=i18n(
            f"文件服务器 (默认: {default_fileServer})",
            f"File server (default: {default_fileServer})",
        ),
    )
    parser.add_argument(
        "--proxy_url",
        type=str,
        default=None,
        help=i18n(
            "代理URL (例如: http://localhost:7890)。如果提供，将启用代理。",
            "Proxy URL (for example: http://localhost:7890). If provided, proxy mode is enabled.",
        ),
    )
    parser.add_argument(
        "--max_retries",
        type=int,
        default=default_max_retries,
        help=i18n(
            f"页面访问最大工作重试次数 (默认: {default_max_retries})",
            f"Maximum page request retries (default: {default_max_retries})",
        ),
    )
    parser.add_argument(
        "--base_backoff_factor",
        type=float,
        default=default_base_backoff_factor,
        help=i18n(
            f"页面访问基准重试延迟时间 (默认: {default_base_backoff_factor})",
            f"Base retry delay for page requests (default: {default_base_backoff_factor})",
        ),
    )
    parser.add_argument(
        "--folder",
        type=str,
        default=default_folder,
        help=i18n(
            f"目标文件夹 (默认: 当前工作目录，{default_folder})",
            f"Target folder (default: current working directory, {default_folder})",
        ),
    )
    parser.add_argument(
        "--post_begins",
        type=int,
        default=1,
        help=i18n(
            "从该账户的第 N 个 post 开始（默认: 1）",
            "Start from the Nth post for this account (default: 1)",
        ),
    )
    parser.add_argument(
        "--post_counts",
        type=int,
        default=0,
        help=i18n(
            "取 N 个 post，0 或小于等于0 表示无限制（默认: 0）",
            "Fetch N posts; 0 or less means unlimited (default: 0)",
        ),
    )
    parser.add_argument(
        "--kemono_mode",
        type=parse_bool_arg,
        nargs="?",
        const=True,
        default=False,
        help=i18n(
            "启用 Kemono 原始响应结构和附件 server 字段兼容模式（默认: false）",
            "Enable compatibility with Kemono's original response structure and attachment server field (default: false)",
        ),
    )
    parser.add_argument(
        "--aria2-rpc-url",
        dest="aria2_rpc_url",
        type=str,
        default=None,
        help=(
            i18n(
                "Aria2 JSON-RPC 地址，例如: http://localhost:6888/jsonrpc 。"
                "如果未指定，将在脚本开始时运行本地 aria2c.exe (--conf-path=aria2.conf)。",
                "Aria2 JSON-RPC URL, for example: http://localhost:6888/jsonrpc. "
                "If omitted, a local aria2c.exe is started at launch (--conf-path=aria2.conf).",
            )
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
            logger.debug(i18n(
                f"文件日志已初始化: {file_log_path}",
                f"File log initialized at: {file_log_path}",
            ))
        except Exception as e:
            logger.warning(i18n(
                f"无法创建文件日志 {file_log_path}: {e}",
                f"Unable to create file log {file_log_path}: {e}",
            ))


def detect_target_os() -> str:
    current_os = platform.system().lower()
    if "windows" in current_os:
        return "windows"
    if "linux" in current_os:
        return "linux"

    logger.warning(
        i18n(
            f"检测到不支持的操作系统 '{platform.system()}'。将使用 Windows 默认设置。",
            f"Unsupported operating system '{platform.system()}' detected. Using Windows defaults.",
        )
    )
    return "windows"


def stop_aria2_process():
    """关闭本程序自己启动的 aria2c，外部 RPC 实例不会被触碰。"""
    global _local_aria2_cleanup_started

    process = _local_aria2_process
    if _local_aria2_cleanup_started or process is None:
        return

    _local_aria2_cleanup_started = True

    if process.poll() is not None:
        logger.info(i18n("本地 aria2c 进程已退出。", "Local aria2c process has already exited."))
        return

    if _local_aria2_rpc_url:
        try:
            aria2_rpc_call(
                "aria2.shutdown",
                [],
                aria2_rpc_url=_local_aria2_rpc_url,
                aria2_token=None,
                timeout=3,
            )
            logger.info(i18n(
                "已向本地 aria2c 发送关闭请求。",
                "Sent shutdown request to local aria2c.",
            ))
        except Exception as e:
            logger.warning(i18n(
                f"通过 RPC 关闭本地 aria2c 失败: {e}",
                f"Failed to shut down local aria2c via RPC: {e}",
            ))

    try:
        process.wait(timeout=8)
        logger.info(i18n("本地 aria2c 已关闭。", "Local aria2c has shut down."))
        return
    except subprocess.TimeoutExpired:
        logger.warning(i18n(
            "本地 aria2c 未按时退出，尝试终止进程。",
            "Local aria2c did not exit in time; attempting to terminate it.",
        ))

    try:
        process.terminate()
        process.wait(timeout=5)
        logger.info(i18n("已终止本地 aria2c 进程。", "Terminated local aria2c process."))
        return
    except subprocess.TimeoutExpired:
        logger.warning(i18n(
            "terminate 后本地 aria2c 仍未退出，尝试强制结束。",
            "Local aria2c still did not exit after terminate; attempting to kill it.",
        ))
    except Exception as e:
        logger.warning(i18n(
            f"终止本地 aria2c 失败: {e}",
            f"Failed to terminate local aria2c: {e}",
        ))

    try:
        process.kill()
        process.wait(timeout=5)
        logger.info(i18n("已强制结束本地 aria2c 进程。", "Killed local aria2c process."))
    except Exception as e:
        logger.error(i18n(
            f"强制结束本地 aria2c 失败: {e}",
            f"Failed to kill local aria2c: {e}",
        ))


def _signal_name(signum: int) -> str:
    try:
        return signal.Signals(signum).name
    except ValueError:
        return str(signum)


def _handle_aria2_exit_signal(signum, frame):
    logger.info(i18n(
        f"收到退出信号 {_signal_name(signum)}，正在关闭本地 aria2c。",
        f"Received exit signal {_signal_name(signum)}; shutting down local aria2c.",
    ))
    stop_aria2_process()
    raise SystemExit(128 + signum)


def register_aria2_cleanup(process: subprocess.Popen, rpc_url: str):
    global _local_aria2_process, _local_aria2_rpc_url

    _local_aria2_process = process
    _local_aria2_rpc_url = rpc_url

    atexit.register(stop_aria2_process)

    for signal_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        signum = getattr(signal, signal_name, None)
        if signum is None:
            continue
        try:
            signal.signal(signum, _handle_aria2_exit_signal)
        except (OSError, RuntimeError, ValueError):
            logger.debug(i18n(
                f"当前环境无法注册 {signal_name} 退出处理。",
                f"Cannot register {signal_name} exit handler in the current environment.",
            ))


def start_aria2_process(proxy_url: Optional[str]) -> subprocess.Popen:
    """
    如果命令行未提供 RPC 地址，则在最开始启动 aria2c：
    Windows: .\\aria2c.exe --conf-path=aria2.conf --stop-with-process=<PID> [--all-proxy=...]
    其他:   ./aria2c    --conf-path=aria2.conf --stop-with-process=<PID> [--all-proxy=...]
    """
    if os.name == "nt":
        exe_path = ".\\aria2c.exe"
    else:
        exe_path = "./aria2c"

    cmd = [exe_path, "--conf-path=aria2.conf", f"--stop-with-process={os.getpid()}"]

    if proxy_url:
        cmd.append(f"--all-proxy={proxy_url}")

    try:
        process = subprocess.Popen(cmd)
        logger.info(i18n(
            "已尝试启动本地 aria2c 进程: " + " ".join(cmd),
            "Attempted to start local aria2c process: " + " ".join(cmd),
        ))
    except FileNotFoundError:
        logger.error(i18n(
            f"启动 aria2c 失败，未找到可执行文件: {exe_path}",
            f"Failed to start aria2c; executable not found: {exe_path}",
        ))
        raise SystemExit(1)
    except Exception as e:
        logger.error(i18n(f"启动 aria2c 失败: {e}", f"Failed to start aria2c: {e}"))
        raise SystemExit(1)

    ariang_demo_url = build_ariang_rpc_setup_url(LOCAL_ARIA2_RPC_URL)
    logger.info(i18n(
        f"可打开 AriaNg 官方 demo 查看下载进度（按住Ctrl并点击下面的链接）:\n "
        f"{LOCAL_ARIA2_RPC_URL}: {ariang_demo_url}",
        f"Open the official AriaNg demo to view download progress (hold Ctrl and click the link below) :\n "
        f"{LOCAL_ARIA2_RPC_URL}: {ariang_demo_url}",
    ))
    time.sleep(5)

    if process.poll() is not None:
        logger.error(i18n(
            f"aria2c 进程已退出，退出码: {process.returncode}",
            f"aria2c process has exited with code: {process.returncode}",
        ))
        raise SystemExit(1)

    return process


def main():
    args = parse_args()

    userid = args.userid
    service = args.service

    cfg = Config()
    cfg.baseUrl = args.base_url
    cfg.fileServer = args.file_server
    cfg.kemonoMode = args.kemono_mode

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
        cfg.aria2_rpc_url = LOCAL_ARIA2_RPC_URL
        aria2_process = start_aria2_process(currentProxyUrlStr)
        register_aria2_cleanup(aria2_process, cfg.aria2_rpc_url)

    init_file_logger(cfg.folder)

    logger.info(i18n("\n---- 配置来咯 ----", "\n---- Configuration ----"))
    logger.info(i18n(f"用户 ID: {userid}", f"User ID: {userid}"))
    logger.info(i18n(f"服务: {service}", f"Service: {service}"))
    logger.info(i18n(f"基础 URL: {cfg.baseUrl}", f"Base URL: {cfg.baseUrl}"))
    logger.info(i18n(f"文件服务器 URL: {cfg.fileServer}", f"File Server URL: {cfg.fileServer}"))
    logger.info(i18n(f"Kemono 模式: {cfg.kemonoMode}", f"Kemono Mode: {cfg.kemonoMode}"))
    logger.info(i18n(f"最大重试次数: {cfg.maxRetries}", f"MAX_RETRIES: {cfg.maxRetries}"))
    logger.info(i18n(
        f"基础退避系数: {cfg.baseBackoffFactor}",
        f"Base Backoff Factor: {cfg.baseBackoffFactor}",
    ))
    if cfg.proxies:
        logger.info(i18n("代理已启用: True", "Proxy Enabled: True"))
        logger.info(i18n(f"代理 URL: {currentProxyUrlStr}", f"Proxy URL: {currentProxyUrlStr}"))
        logger.info(i18n(f"代理配置: {cfg.proxies}", f"Proxies: {cfg.proxies}"))
    else:
        logger.info(i18n("代理已启用: False", "Proxy Enabled: False"))
    logger.info(i18n(f"Aria2 RPC URL: {cfg.aria2_rpc_url}", f"Aria2 RPC URL: {cfg.aria2_rpc_url}"))
    logger.info(i18n(f"目标系统: {cfg.targetOS}", f"Target OS: {cfg.targetOS}"))
    logger.info(i18n(f"目标文件夹: {cfg.folder}", f"Folder: {cfg.folder}"))
    logger.info(i18n(f"起始帖子序号: {postBegins}", f"Post begins: {postBegins}"))
    logger.info(i18n(f"帖子数量: {cfg.postCounts}", f"Post count: {cfg.postCounts}"))
    logger.info("-------------------\n")

    logger.info(i18n("\n---- 抓取开始咯 ----", "\n---- Fetch started ----"))

    cfg.baseUrl = cfg.baseUrl + "api/v1/"

    try:
        getPostFromPage(userid, service, postBegins, cfg)
    finally:
        stop_aria2_process()


if __name__ == "__main__":
    main()
