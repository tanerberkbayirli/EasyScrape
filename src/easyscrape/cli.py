"""Download a social video to the Desktop."""

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
        description="YouTube, X, TikTok, Instagram, Reddit ve Pinterest videosunu indir."
    )
    parser.add_argument("url", help="İndirilecek videonun bağlantısı")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        path = download_video(args.url, log=lambda message: print(message, flush=True))
        print(f"Kaydedildi: {path}", flush=True)
        return 0
    except (DownloadError, OSError) as exc:
        print(f"İndirilemedi: {exc}", file=sys.stderr, flush=True)
        return 1
    except KeyboardInterrupt:
        return 130
