"""Download a social video to the configured output directory."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .downloader import DownloadError, download_video


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")
    parser = argparse.ArgumentParser(
        prog="easyscrape",
        description=(
            "Download videos from YouTube, YouTube Shorts, X, TikTok, Instagram, "
            "Instagram Reels, Reddit, Snapchat Spotlight, Pinterest, and Threads."
        ),
    )
    parser.add_argument("url", help="Video URL to download")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        path = download_video(args.url, log=lambda message: print(message, flush=True))
        print(f"Saved: {path}", flush=True)
        return 0
    except (DownloadError, OSError) as exc:
        print(f"Download failed: {exc}", file=sys.stderr, flush=True)
        return 1
    except KeyboardInterrupt:
        return 130
