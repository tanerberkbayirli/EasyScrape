# EasyScrape

Paste any supported social video link; **EasyScrape** detects the platform, submits it to a verified download service, prioritizes **1080p / 720p HD** streams, and saves a verified **MP4** video into your chosen folder (Desktop by default).

## Supported Platforms (10)

- **YouTube** (`youtube.com`, `youtu.be`) → `https://vidssave.com/`
- **YouTube Shorts** (`youtube.com/shorts/...`) → `https://vidssave.com/`
- **X / Twitter** (`x.com`, `twitter.com`) → `https://ssstwitter.com/`
- **TikTok** (including `vm.tiktok.com` / `vt.tiktok.com` short links) → `https://ssstik.io/`
- **Instagram** (`instagram.com/p/...`, `/tv/...`) → `https://fastdl.app/en`
- **Instagram Reels** (`instagram.com/reel/...`, `/reels/...`) → `https://fastdl.app/en`
- **Reddit** (including `redd.it` short links) → `https://viddit.io/`
- **Snapchat Spotlight** (`snapchat.com/spotlight/...`, `story.snapchat.com/...`) → `https://getindevice.com/snapchat-downloader/`
- **Pinterest** (including `pin.it` and regional domains) → `https://pindown.io/`
- **Threads** (`threads.net`, `threads.com`) → `https://threadster.app/`

Only these ten platforms/video types and MP4 video downloads are supported. Legacy extractors (`yt-dlp` / `gallery-dl`), Spotify, photo-only posts, audio conversion, batch/file lists, cookie selection, reports, and history features were intentionally removed.

## Installation & Usage

Requires **Python 3.10+** and **Microsoft Edge** or **Google Chrome**.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install .
.venv\Scripts\easyscrape-gui.exe
```

If neither Edge nor Chrome is installed, install Playwright Chromium once:

```powershell
.venv\Scripts\python.exe -m playwright install chromium
```

### Desktop App (`easyscrape-gui`)

1. Paste a video link into the input box (or click **Paste**) and click **Download** (or press `Enter`).
2. Click **Settings** to configure the save folder and global activation shortcut (defaults: **Desktop** and **`Ctrl + Shift + D`**).
3. Click **Save** to apply preferences immediately without restarting. If a shortcut is already registered by another app, the previous shortcut is preserved. Settings are stored on Windows at `%APPDATA%\EasyScrape\settings.json` (or `$XDG_CONFIG_HOME/EasyScrape/settings.json` on Linux/macOS).
4. On Windows, closing the window keeps the app resident in the background so **`Ctrl + Shift + D`** brings it back instantly at the bottom-right corner. Right-click the window and select **Quit completely** to exit. Heavy browser/network libraries are loaded only when a download starts.
5. To launch silently at Windows startup, point a shortcut in the Startup folder to `pythonw.exe -m easyscrape.gui --background`.

### CLI Usage

```powershell
.venv\Scripts\easyscrape.exe "https://x.com/user/status/123456789"
```

The CLI uses the same configured save folder.

## How Downloads Work

During a download, a browser window opens, fills and submits the link to the target service, ranks available video options by resolution (**1080p → 1440p/2K → 2160p/4K → 720p/HD**, skipping lower-resolution 144p–480p options when HD is available), and verifies that the result is a valid MP4 file containing a video track (`ftyp` + `vide` handler) before writing it as `<platform>_YYYYMMDD_HHMMSS.mp4`. Existing files are never overwritten, temporary files are cleaned up, and no metadata or report files are left behind.

If a service prompts for human verification (CAPTCHA), complete it in the opened browser window within 3 minutes. Closing the browser window cancels the download.

Success depends on third-party service availability and public media accessibility; private accounts, deleted posts, and image-only posts cannot be downloaded as videos.

## Development

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy src/easyscrape
.venv\Scripts\python.exe -m build
```

Automated tests verify URL/platform matching, deceptive/unsupported URL rejection, MP4 video track validation, filename collision safety, Windows desktop/hotkey/settings persistence, HD resolution preference over 144p, and end-to-end browser form downloads against a local test HTTP server without depending on external services.
