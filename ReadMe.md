# KemonoDownloader

一个用于从 Kemono Party 批量下载创作者内容的 Python 工具。



## 功能特性

-  批量下载指定创作者的所有帖子及附件
-  使用 Aria2 而不是 curl / request 进行高效下载，可通过 AriaNg 可视化查看进度
- 可选使用远程 Aria2 服务器进行下载
-  自动重试机制，应对 网络 / Kemono / 代理 不稳定情况
-  支持 HTTP/HTTPS 代理
-  自动创建按帖子组织的文件夹结构
-  相比旧版本，支持下载预览图、各类附件文件和嵌入链接
-  完整保存帖子内容为 HTML 文件
-  跨平台支持（Windows / Linux）
- 

## 依赖

- Python 3.10+

- [requests](https://pypi.org/project/requests/)

- [Aria2](https://github.com/aria2/aria2/releases/tag/release-1.37.0)（指定下载服务器或使用本地 aria2c 可执行文件）

  

## 使用方法



### 下载工具和配置文件

下载最新的 Release 或者下载

> aria2.conf
>
> aria2.session
>
> main.py

三个文件，并从 [Aria2 release](https://github.com/aria2/aria2/releases/tag/release-1.37.0)  页面下载合适您系统的版本，放在和以上三个文件相同的目录下

安装依赖：

```
pip install requests
```

或者下载 requirements.txt 并执行
```
pip install -r requirements.txt
```



### 下载服务器配置（必须步骤）

如果你拥有自己的 Aria2 下载服务器，或者本地已经运行了Aria2服务器，可以通过下面的命令行参数配置 Aria2 下载服务

如果你不知道什么是 Aria2 ，或者不想将在已有服务器中添加下载记录，可以不配置服务器，使用程序拉起的 Aria2 下载服务器进行下载。程序拉起的服务器使用6888端口，不会和本地已有服务器（如果有）冲突。



### 基本用法

```bash
python main.py <用户ID> <服务名称>
```

**示例：**

如果Artist的页面链接为：

```
https://kemono.cr/fanbox/user/12345678
```

那么使用命令为：
```bash
python main.py 12345678 fanbox
```



### 命令行参数

| 参数                    | 说明                                                         | 默认值                          |
| ----------------------- | ------------------------------------------------------------ | ------------------------------- |
| `userid`                | 目标用户的 ID（必填）                                        | -                               |
| `service`               | 服务名称，如 `fanbox`、`patreon` 等（必填）                  | -                               |
| `--base_url`            | Kemono 基础 URL，应对Kemono更换域名，可能也可以用于同架构网站下载（未测试）。 | `https://kemono.cr/`            |
| `--proxy_url`           | HTTP/HTTPS 代理地址                                          | `None`                          |
| `--max_retries`         | 页面请求最大重试次数                                         | `5`                             |
| `--base_backoff_factor` | 页面请求重试延迟基准因子（秒）                               | `3. 0`                          |
| `--folder`              | 下载目标文件夹                                               | 当前工作目录                    |
| `--post_begins`         | 从第 N 个帖子开始下载                                        | `1`                             |
| `--post_counts`         | 下载帖子数量（0 表示全部）                                   | `0`                             |
| `--aria2-rpc-url`       | Aria2 JSON-RPC 地址                                          | `http://localhost:6888/jsonrpc` |



### 使用代理

```bash
python main.py 12345678 fanbox --proxy_url http://127.0.0.1:7897
```



### 指定下载范围

```bash
# 从第 10 个帖子开始，下载 20 个帖子
python main.py 12345678 fanbox --post_begins 10 --post_counts 20
```



## 输出结构

下载的内容会按以下结构组织：

```
<下载目录>/
└── <服务名>_<用户名>/
    ├── <发布日期>_<帖子标题>_<帖子ID>/
    │   ├── ! Content.html       # 帖子内容
    │   ├── 附件文件... 
    │   └── em0_xxx. url         # 嵌入链接
    └── ... 
```



## 日志

- 控制台实时输出 INFO 级别日志
- 下载目录下生成 `kemono_downloader. log` 文件，记录 DEBUG 级别详细日志



## Aria2 配置

如果未指定 `--aria2-rpc-url`，程序会自动在同目录下启动 `aria2c`，需要确保：

1. `aria2c` / `aria2c.exe` 可执行文件存在于程序目录
2. `aria2.conf` 配置文件存在于程序目录
3. 可通过浏览器打开 `AriaNg.html` 查看下载进度



## 许可证

MIT License