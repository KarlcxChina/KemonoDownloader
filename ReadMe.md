[简体中文](./ReadMe_ZH_CN.md)

# KemonoDownloader (actually PawchiveDownloader)

A Python tool for batch-downloading creator content from Kemono.

Since Kemono has stopped providing download services, the default download source is now [**Pawchive**](https://pawchive.pw/).

[**Pawchive**](https://pawchive.pw/) is a mirror of Kemono.cr. It preserves all thumbnails and text resources after Kemono stopped its download service.

## First Use: Configure Your Contact Preference

Contact preference configuration was added at the site operator's request ([announcement](https://t.me/pawchivest/17)).

Before downloading, run `python main.py -email`, or `./KemonoDownloader.exe -email` if you use the executable. This setup step is required, but providing an email address is optional. Press Enter to skip. You can run the same command later to change your email address or clear it by skipping.

Preferences are stored in `%APPDATA%\KemonoDownloader\config.json` on Windows and `$XDG_CONFIG_HOME/KemonoDownloader/config.json` on Linux (default: `~/.config/KemonoDownloader/config.json`). If the configuration is missing or the saved preference is invalid, the program exits with an error.

If provided, your email address is included in the User-Agent for API requests and Aria2 downloads, including remote Aria2 tasks, and may be recorded by those servers. If you skip, the User-Agent contains only the tool name and project URL.

### Download Submission Interval and Recommended Limits

Download submission and concurrency limits were added at the site operator's request ([announcement](https://t.me/pawchivest/17)).

`--download-submit-interval` defaults to `1` second. Starts of successive Aria2 download submissions within one program run are spaced at least this far apart. Attachments, thumbnails, and application resubmissions share the limiter; the first submission is immediate. For a longer interval:

```bash
python main.py 12345678 fanbox --download-submit-interval 2
```

The default `aria2.conf` allows up to 5 active downloads, with one connection per file:

```ini
max-concurrent-downloads=5
max-connection-per-server=1
split=1
```

`--not-recommended-override-download-limmit-config` accepts `true` / `false` and defaults to `false` (the spelling `limmit` is intentional). By default, intervals below 1 second, concurrency above 5, or either connection setting above 1 cause an error. Lower concurrency and longer intervals are allowed. Only explicit `true` permits exceeding these recommendations; the switch itself does not increase concurrency or reduce the interval:

```bash
python main.py 12345678 fanbox --download-submit-interval 0.5 --not-recommended-override-download-limmit-config true
```

Overrides are not recommended; respect the file server's rules. Invalid numeric values remain rejected. Local configuration is checked before starting Aria2, and effective global options are checked after connecting. External `--aria2-rpc-url` instances must also pass validation before submissions begin. The program does not modify external global settings; configure that instance yourself. New tasks explicitly receive the checked per-file connection settings. Rename-only modes skip Aria2 validation.

This limits application submissions, not every HTTP request made internally by Aria2. Internal retries, redirects, existing/resumed jobs, and tasks from other programs are outside this interval limiter. Runtime changes to external settings are not continuously monitored. This does not guarantee a strict file-server request rate.

## Featuresf

- Batch-download all posts and attachments from a specified creator.
- Uses Aria2 instead of curl / requests for efficient downloads, with progress viewable through the AriaNg web UI.
- Optional support for downloading through a remote Aria2 server.
- Automatic retry mechanism for unstable network / Kemono / proxy conditions.
- HTTP/HTTPS proxy support.
- Automatically creates a folder structure organized by post.
- Compared with older versions, supports downloading previews, various attachment files, and embedded links.
- Saves full post content as HTML files.
- Cross-platform support (Windows / Linux).

## Dependencies

- Python 3.10+
- [requests](https://pypi.org/project/requests/)
- [Aria2](https://github.com/aria2/aria2/releases/tag/release-1.37.0) (use either a specified download server or a local `aria2c` executable)

## Usage

### Download the Tool and Configuration Files

Download the latest Release, or download the following three files:

> aria2.conf
>
> aria2.session
>
> main.py

Then download the appropriate version for your system from the [Aria2 release page](https://github.com/aria2/aria2/releases/tag/release-1.37.0), and place it in the same directory as the three files above.

Install dependencies:

```bash
pip install requests
```

Alternatively, download `requirements.txt` and run:

```bash
pip install -r requirements.txt
```

### Download Server Configuration

If you have your own Aria2 download server, or if an Aria2 server is already running locally, you can configure the Aria2 download service with the command-line arguments below.

If you do not know what Aria2 is, or if you do not want to add download records to an existing server, you can skip server configuration and use the Aria2 download server started by the program. The server started by the program uses port `6888`, so it will not conflict with an existing local server, if one exists.

### Basic Usage

This program currently only supports command-line usage and does not support direct launching.

```bash
python main.py <user ID> <service name>
```

or

```cmd
KemonoDownloader.exe <user ID> <service name>
```

**Example:**

If the artist page URL is:

```text
https://pawchive.pw/fanbox/user/12345678
```

Then the command is:

```bash
python main.py 12345678 fanbox
```

or

```cmd
KemonoDownloader.exe 12345678 fanbox
```

### Posts Whose Attachments Were Not Crawled by Pawchive

If the attachments of a crawled post have not been archived by Pawchive, the program will only

### Command-Line Arguments

| Argument                | Description                                                  | Default                         |
| ----------------------- | ------------------------------------------------------------ | ------------------------------- |
| `userid`                | Target user ID (required)                                    | -                               |
| `service`               | Service name, such as `fanbox`, `patreon`, etc. (required)   | -                               |
| `--base_url`            | Kemono base URL. Currently points to Pawchive by default.    | `https://pawchive.pw/`          |
| `--file_server`         | Pawchive download server URL                                 | `https://file.pawchive.pw/`     |
| `--proxy_url`           | HTTP/HTTPS proxy address                                     | `None`                          |
| `--max_retries`         | Maximum number of retries for page requests                  | `5`                             |
| `--base_backoff_factor` | Base factor for page request retry delay (seconds)           | `3.0`                           |
| `--folder`              | Target download folder                                       | Current working directory       |
| `--post_begins`         | Start downloading from the Nth post                          | `1`                             |
| `--post_counts`         | Number of posts to download (`0` means all posts)            | `0`                             |
| `--aria2-rpc-url`       | Aria2 JSON-RPC address                                       | `http://localhost:6888/jsonrpc` |
| `--kemono_mode`         | Compatibility option for use if Kemono comes back online     | `false`                         |
| `--number_attachments`  | Attachment numbering mode: `off`/`on`/`image`/`rename`/`image_rename` | `off`                           |
| `--download-submit-interval` | Minimum interval between successive Aria2 download submissions within one program run (seconds) | `1` |
| `--not-recommended-override-download-limmit-config` | Allow download settings above the site operator's recommended limits (not recommended; accepts `true`/`false`) | `false` |

### Language Configuration

The program chooses its display language automatically:

- Chinese system locale: Chinese output.
- Any other locale: English output.

You can override the detected language with the `KEMONO_DOWNLOADER_LANG` environment variable. Values starting with `zh` use Chinese; other values such as `en` use English. This affects console logs, error messages, and `--help` text.

PowerShell:

```powershell
$env:KEMONO_DOWNLOADER_LANG = "en"
python main.py 12345678 fanbox
```

Command Prompt:

```cmd
set KEMONO_DOWNLOADER_LANG=en
KemonoDownloader.exe 12345678 fanbox
```

Bash:

```bash
KEMONO_DOWNLOADER_LANG=en python main.py 12345678 fanbox
```

### Kemono Mode

Corresponds to the command-line argument `--kemono_mode`.

Pawchive's server behavior differs somewhat from Kemono's. If Kemono provides file downloads again, or if you need to download files from another server that behaves the same way as Kemono, point `--base_url` to Kemono and set this parameter to `true`.

### Using a Proxy

```bash
python main.py 12345678 fanbox --proxy_url http://127.0.0.1:7897
```

### Specify a Download Range

```bash
# Start from the 10th post and download 20 posts
python main.py 12345678 fanbox --post_begins 10 --post_counts 20
```

### Attachment Numbering

`--number_attachments` is disabled by default. Available modes:

- `on`: prefix all attachment filenames by attachment order.
- `image`: prefix only image attachment filenames.
- `rename`: do not download; fetch post metadata and number already downloaded attachment files.
- `image_rename`: do not download; number only already downloaded image attachment files.

Numbering starts at `00_` and uses two digits by default. If the attachment count needs more digits, the count width is used instead, such as `000_`.

```bash
python main.py 12345678 fanbox --number_attachments on
python main.py 12345678 fanbox --number_attachments image_rename
```

## Output Structure

Downloaded content is organized as follows:

```text
<download directory>/
└── <service name>_<username>/
    ├── <publish date>_<post title>_<post ID>/
    │   ├── ! Content.html       # Post content
    │   ├── attachment files...
    │   └── em0_xxx.url          # Embedded link
    └── ...
```

## Logs

- Real-time INFO-level logs are printed to the console.
- A `kemono_downloader.log` file is generated in the download directory, recording detailed DEBUG-level logs.

## Aria2 Configuration

If `--aria2-rpc-url` is not specified, the program automatically starts `aria2c` from the same directory. Make sure that:

1. The `aria2c` / `aria2c.exe` executable exists in the program directory.
2. The `aria2.conf` configuration file exists in the program directory.
3. Open the [official AriaNg demo](<https://ariang.mayswind.net/latest/#!/settings/rpc/set?protocol=http&host=localhost&port=6888&interface=jsonrpc>) to view download progress. The link sets RPC to the local aria2 URL `http://localhost:6888/jsonrpc`, so a local `AriaNg.html` is no longer needed.

## License

MIT License
