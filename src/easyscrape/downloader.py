"""Submit social links to the selected service and save only verified MP4 videos."""

from __future__ import annotations

import mmap
import re
import shutil
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from playwright.sync_api import Browser, Download, Page, Playwright, sync_playwright
from playwright.sync_api import Error as BrowserError

from .settings import load_settings


class DownloadError(Exception):
    """An unsupported link or an unsuccessful service download."""


@dataclass(frozen=True)
class Service:
    platform: str
    url: str
    domains: tuple[str, ...]


SERVICES = (
    Service("X", "https://ssstwitter.com/", ("x.com", "twitter.com")),
    Service("TikTok", "https://ssstik.io/", ("tiktok.com",)),
    Service("Instagram", "https://reelsvideo.io/en-4", ("instagram.com",)),
    Service("Reddit", "https://redvid.io/", ("reddit.com", "redd.it")),
    Service("Pinterest", "https://redvid.io/pinterest-downloader", (
        "pinterest.com", "pin.it", "pinterest.com.tr", "pinterest.co.uk", "pinterest.de",
        "pinterest.fr", "pinterest.es", "pinterest.it", "pinterest.ca", "pinterest.com.au",
        "pinterest.jp", "pinterest.co.kr", "pinterest.pt", "pinterest.com.mx",
        "pinterest.com.br", "pinterest.ch", "pinterest.at", "pinterest.se",
    )),
)


def resolve_service(url: str) -> Service:
    try:
        parsed = urlsplit(url.strip())
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            raise ValueError
        if parsed.port not in {None, 80, 443}:
            raise ValueError
    except ValueError as exc:
        raise DownloadError("Geçerli bir HTTP(S) video bağlantısı girin.") from exc
    for service in SERVICES:
        if any(host == domain or host.endswith("." + domain) for domain in service.domains):
            return service
    raise DownloadError("Yalnızca X, TikTok, Instagram, Reddit ve Pinterest destekleniyor.")


def is_mp4_video(path: Path) -> bool:
    """Require an ISO media container with a video track, including moov-at-end files."""
    if path.stat().st_size < 32:
        return False
    with path.open("rb") as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as data:
        if data[4:8] != b"ftyp":
            return False
        offset = data.find(b"hdlr")
        while offset >= 0:
            if data[offset + 12:offset + 16] == b"vide":
                return True
            offset = data.find(b"hdlr", offset + 4)
    return False


def save_video(source: Path, directory: Path, platform: str) -> Path:
    if not is_mp4_video(source):
        raise DownloadError("Servis geçerli bir MP4 video döndürmedi.")
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{platform.lower()}_{time.strftime('%Y%m%d_%H%M%S')}"
    for number in range(1, 10000):
        target = directory / f"{stem}{'' if number == 1 else f'_{number}'}.mp4"
        try:
            destination = target.open("xb")
        except FileExistsError:
            continue
        try:
            with destination, source.open("rb") as video:
                shutil.copyfileobj(video, destination)
            return target
        except BaseException:
            target.unlink(missing_ok=True)
            raise
    raise DownloadError("Masaüstünde benzersiz bir dosya adı oluşturulamadı.")


def _launch(playwright: Playwright) -> Browser:
    for channel in ("msedge", "chrome", None):
        try:
            return playwright.chromium.launch(channel=channel, headless=False)
        except BrowserError:
            continue
    raise DownloadError(
        "Tarayıcı açılamadı. Edge/Chrome kurun veya "
        "'python -m playwright install chromium' çalıştırın."
    )


# Only new result links are considered; navigation and audio/photo actions are excluded.
_LINKS = """() => Array.from(document.querySelectorAll('a[href]'))
  .filter(a => a.getClientRects().length)
  .map(a => ({url: a.href, text: (a.textContent + ' ' + a.getAttribute('download')
      + ' ' + a.className).trim()}))"""


def _video_links(page: Page, initial: set[str]) -> list[str]:
    results: list[tuple[int, str]] = []
    for link in page.evaluate(_LINKS):
        url, text = link["url"], link["text"].lower()
        if url in initial or urlsplit(url).scheme not in {"https", "http"}:
            continue
        hint = text + " " + url.lower()
        if re.search(r"mp3|\.jpe?g|\.png|\.webp|\.gif", urlsplit(url).path.lower()):
            continue
        if re.search(r"audio|music|photo|image|mp3", text) and not re.search(r"video|mp4", text):
            continue
        if not re.search(r"download|indir|mp4|watermark|video|720|1080|hd", hint):
            continue
        score = 3 if re.search(r"1080|hd", text) else 2 if "720" in text else 1
        results.append((score, url))
    return list(dict.fromkeys(url for _, url in sorted(results, key=lambda row: -row[0])))


def _fetch_video(page: Page, url: str, destination: Path) -> bool:
    cookies = httpx.Cookies()
    for cookie in page.context.cookies([url]):
        cookies.set(cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie["path"])
    headers = {"User-Agent": page.evaluate("navigator.userAgent"), "Referer": page.url}
    try:
        with httpx.Client(
            follow_redirects=True, timeout=30, cookies=cookies, headers=headers
        ) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if "text/" in content_type or "json" in content_type or "image/" in content_type:
                    return False
                with destination.open("wb") as output:
                    first = True
                    for chunk in response.iter_bytes(64 * 1024):
                        if first:
                            if len(chunk) < 8 or chunk[4:8] != b"ftyp":
                                return False
                            first = False
                        output.write(chunk)
        return is_mp4_video(destination)
    except httpx.HTTPError:
        return False


def _run_service(page: Page, service: Service, url: str, staging: Path,
                 log: Callable[[str], None]) -> Path:
    downloads: list[Download] = []
    page.on("download", lambda download: downloads.append(download))
    page.context.on(
        "page", lambda opened: opened.on("download", lambda download: downloads.append(download))
    )
    page.goto(service.url, wait_until="domcontentloaded", timeout=60000)
    log("Gerekirse açılan tarayıcıdaki insan doğrulamasını tamamlayın (3 dakika).")
    field = page.locator(
        '#main_page_text, input[type="url"], input[placeholder="Paste here"], '
        'input[name="url"], input[name="id"], input[type="text"]'
    ).filter(visible=True).first
    field.fill(url, timeout=180000)
    # Snapshot after a possible challenge page has been completed and replaced.
    initial = {link["url"] for link in page.evaluate(_LINKS)}
    initial_buttons = set(page.locator("button:visible").all_text_contents())
    form = field.locator("xpath=ancestor::form")
    submit = form.locator('button[type="submit"], input[type="submit"], #submit').first
    if submit.count():
        submit.click(timeout=180000)
    else:
        # Some services put their download action outside a form.
        page.get_by_role("button", name=re.compile(r"^\s*(Download|İndir)\s*$", re.I)).first.click(
            timeout=180000
        )
    deadline = time.monotonic() + 180
    attempted: set[str] = set()
    clicked: set[str] = set()
    local = staging / "video.mp4"
    while time.monotonic() < deadline:
        if page.is_closed():
            raise DownloadError("İndirme tamamlanmadan tarayıcı kapatıldı.")
        while downloads:
            download = downloads.pop(0)
            if download.failure() is None:
                download.save_as(local)
                if is_mp4_video(local):
                    return local
        for candidate in _video_links(page, initial):
            if candidate in attempted:
                continue
            attempted.add(candidate)
            log("Servisin hazırladığı video indiriliyor...")
            if _fetch_video(page, candidate, local):
                return local
            # Let the service's own click handler/cookies handle attachment endpoints.
            anchor = page.locator("a[href]").filter(visible=True)
            for index in range(anchor.count()):
                item = anchor.nth(index)
                if item.evaluate("a => a.href") == candidate:
                    try:
                        item.click(timeout=3000, no_wait_after=True)
                    except BrowserError:
                        pass
                    break
        buttons = page.locator("button:visible")
        for index in range(buttons.count()):
            button = buttons.nth(index)
            label = button.text_content() or ""
            if label in initial_buttons or label in clicked:
                continue
            if re.search(r"mp3|photo|image", label, re.I):
                continue
            if re.search(r"download|mp4|video|1080|720", label, re.I):
                clicked.add(label)
                button.click(timeout=5000, no_wait_after=True)
                break
        # Playwright pumps browser events during this wait (including manual downloads).
        page.wait_for_timeout(500)
    raise DownloadError(
        f"{service.url} video döndürmedi. Bağlantıyı ve tarayıcıdaki hata/doğrulamayı kontrol edin."
    )


def download_video(
    url: str, log: Callable[[str], None] = print, *, output_directory: Path | None = None,
) -> Path:
    url = url.strip()
    service = resolve_service(url)
    directory = (
        output_directory if output_directory is not None else load_settings().output_directory
    )
    log(f"{service.platform} tanındı → {service.url}")
    try:
        with tempfile.TemporaryDirectory(prefix="easyscrape-") as temporary, \
                sync_playwright() as playwright:
            browser = _launch(playwright)
            try:
                context = browser.new_context(accept_downloads=True)
                page = context.new_page()
                video = _run_service(page, service, url, Path(temporary), log)
                return save_video(video, directory, service.platform)
            finally:
                browser.close()
    except BrowserError as exc:
        raise DownloadError(f"İndirme servisine erişilemedi: {exc.message}") from exc
