# Development Status

Version **1.0.0** routes video links from ten supported platforms/variants to live-verified download services, prioritizes HD (**1080p / 720p**) MP4 streams, and provides a modern dark-themed desktop interface:

- **YouTube & YouTube Shorts** → `https://vidssave.com/`
- **X / Twitter** → `https://ssstwitter.com/`
- **TikTok** → `https://ssstik.io/`
- **Instagram & Instagram Reels** → `https://fastdl.app/en`
- **Reddit** → `https://viddit.io/`
- **Snapchat Spotlight** → `https://getindevice.com/snapchat-downloader/`
- **Pinterest** → `https://pindown.io/`
- **Threads** → `https://threadster.app/`

The CLI accepts a single URL, and the Tkinter desktop UI provides a single URL input with one-click paste, colorful platform badges, a neon download progress indicator, and a Settings dialog for customizing the save folder and global activation hotkey (defaults: **Desktop** and **`Ctrl+Shift+D`**). Preferences persist across restarts, and hotkey changes apply immediately without restarting. On Windows, the app remains resident in the background and positions itself at the bottom-right corner whenever activated.

Runtime dependencies are `playwright` and `httpx`. Microsoft Edge, Google Chrome, or Playwright Chromium is used for browser automation. Legacy extractors and their associated tests have been removed.
