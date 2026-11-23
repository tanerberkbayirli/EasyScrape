# Contributing Guide

See [README.md](README.md) for installation, usage, and verification commands.

Platform-to-service mapping and the browser download pipeline live in `src/easyscrape/downloader.py`. The supported scope covers **YouTube**, **YouTube Shorts**, **X**, **TikTok**, **Instagram**, **Instagram Reels**, **Reddit**, **Snapchat Spotlight**, **Pinterest**, and **Threads** MP4 video downloads.

When a service form or download link structure changes, update the browser integration tests in `tests/test_downloader.py` using local HTML fixtures. Automated tests must not depend on live third-party services, user accounts, or external media. Failed or partial files must never be written to the destination folder, and existing files must never be overwritten.

Do not add code that bypasses CAPTCHAs or anti-bot protections. Any human verification must remain interactive for the user in the opened browser window.
