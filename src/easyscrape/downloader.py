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
from playwright.sync_api import Browser, Download, Locator, Page, Playwright, sync_playwright
from playwright.sync_api import Error as BrowserError

from .settings import load_settings


class DownloadError(Exception):
    """An unsupported link or an unsuccessful service download."""


@dataclass(frozen=True)
class Service:
    platform: str
    url: str
    domains: tuple[str, ...]
    path_prefixes: tuple[str, ...] = ()


SERVICES = (
    Service("YouTube Shorts", "https://vidssave.com/", ("youtube.com", "youtu.be"), ("/shorts/",)),
    Service("YouTube", "https://vidssave.com/", ("youtube.com", "youtu.be")),
    Service("X", "https://ssstwitter.com/", ("x.com", "twitter.com")),
    Service("TikTok", "https://ssstik.io/", ("tiktok.com",)),
    Service(
        "Instagram Reels", "https://fastdl.app/en", ("instagram.com",), ("/reel/", "/reels/"),
    ),
    Service("Instagram", "https://fastdl.app/en", ("instagram.com",)),
    Service("Reddit", "https://viddit.io/", ("reddit.com", "redd.it")),
    Service("Snapchat Spotlight", "https://getindevice.com/snapchat-downloader/", (
        "snapchat.com",
    )),
    Service("Pinterest", "https://pindown.io/", (
        "pinterest.com", "pin.it", "pinterest.com.tr", "pinterest.co.uk", "pinterest.de",
        "pinterest.fr", "pinterest.es", "pinterest.it", "pinterest.ca", "pinterest.com.au",
        "pinterest.jp", "pinterest.co.kr", "pinterest.pt", "pinterest.com.mx",
        "pinterest.com.br", "pinterest.ch", "pinterest.at", "pinterest.se",
    )),
    Service("Threads", "https://threadster.app/", ("threads.net", "threads.com")),
)


def resolve_service(url: str) -> Service:
    try:
        parsed = urlsplit(url.strip())
        host = (parsed.hostname or "").lower().rstrip(".")
        path = (parsed.path or "/").lower()
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            raise ValueError
        if parsed.port not in {None, 80, 443}:
            raise ValueError
    except ValueError as exc:
        raise DownloadError("Geçerli bir HTTP(S) video bağlantısı girin.") from exc
    for service in SERVICES:
        if any(host == domain or host.endswith("." + domain) for domain in service.domains):
            if not service.path_prefixes or any(
                path.startswith(prefix) for prefix in service.path_prefixes
            ):
                return service
    raise DownloadError(
        "Yalnızca YouTube, YouTube Shorts, X, TikTok, Instagram, Instagram Reels, "
        "Reddit, Snapchat Spotlight, Pinterest ve Threads destekleniyor."
    )


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
    slug = re.sub(r"[^a-z0-9]+", "_", platform.lower()).strip("_")
    stem = f"{slug}_{time.strftime('%Y%m%d_%H%M%S')}"
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
  .map(a => {
    const parent = a.parentElement && a.parentElement.parentElement;
    const container = a.closest('tr, li') || (
      parent && !['BODY', 'HTML', 'FORM'].includes(parent.tagName) ? parent : null
    );
    const row = container ? (container.innerText || container.textContent || '') : '';
    const extra = row && row.length <= 160 ? ' ' + row : '';
    return {url: a.href, text: ((a.innerText || a.textContent || '') + ' '
      + a.getAttribute('download') + ' ' + a.className + extra).replace(/\\s+/g, ' ').trim()};
  })"""


def _quality_score(text: str) -> int:
    lowered = text.lower()
    for pattern, score in (
        (r"1080p|(?<!\d)1080(?!\d)", 1080),
        (r"1440p|\b2k\b|(?<!\d)1440(?!\d)", 1050),
        (r"2160p|\b4k\b|(?<!\d)2160(?!\d)", 1020),
        (r"720p|\bhd\b|(?<!\d)720(?!\d)", 720),
        (r"480p|(?<!\d)480(?!\d)", 480),
        (r"360p|(?<!\d)360(?!\d)", 360),
        (r"240p|(?<!\d)240(?!\d)", 240),
        (r"144p|(?<!\d)144(?!\d)", 144),
    ):
        if re.search(pattern, lowered):
            return score + (5 if "fast" in lowered else 0)
    return 500


def _video_links(page: Page, initial: set[str]) -> list[str]:
    results: list[tuple[int, str]] = []
    for link in page.evaluate(_LINKS):
        url, text = link["url"], link["text"].lower()
        if url in initial or urlsplit(url).scheme not in {"https", "http"}:
            continue
        hint = text + " " + url.lower()
        if re.search(r"mp3|\.jpe?g|\.png|\.webp|\.gif", urlsplit(url).path.lower()):
            continue
        if re.search(r"audio|music|photo|image|mp3|kbps", text) and not re.search(
            r"video|mp4", text
        ):
            continue
        if not re.search(r"download|indir|mp4|watermark|video|720|1080|hd", hint):
            continue
        results.append((_quality_score(text), url))
    if any(score >= 720 for score, _ in results):
        results = [(score, url) for score, url in results if score >= 720]
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


def _click_submit(page: Page, field: Locator) -> None:
    form = field.locator("xpath=ancestor::form")
    submit = form.locator(
        'button[type="submit"], input[type="submit"], #submit'
    ).filter(visible=True).first
    if submit.count():
        submit.click(timeout=180000)
    else:
        # Some services put their download action outside a form.
        page.get_by_role(
            "button",
            name=re.compile(r"(Download|İndir|Convert|Dönüştür|Get|Search|Start|Submit)", re.I),
        ).first.click(timeout=180000)


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
        '#main_page_text, input[type="url"], input[placeholder*="Paste" i], '
        'input[placeholder*="URL" i], input[placeholder*="link" i], '
        'input[name="url"], input[name="id"], input[type="text"], input[type="search"], '
        'input:not([type])'
    ).filter(visible=True).first
    field.fill(url, timeout=180000)
    # Snapshot after a possible challenge page has been completed and replaced.
    initial = {link["url"] for link in page.evaluate(_LINKS)}
    page.locator("button:visible").evaluate_all(
        "buttons => buttons.forEach(button => button.dataset.easyscrapeInitial = 'true')"
    )
    _click_submit(page, field)
    started = time.monotonic()
    deadline = started + 180
    resubmitted = False
    attempted: set[str] = set()
    local = staging / "video.mp4"
    next_button_click = 0.0
    while time.monotonic() < deadline:
        if page.is_closed():
            raise DownloadError("İndirme tamamlanmadan tarayıcı kapatıldı.")
        while downloads:
            download = downloads.pop(0)
            if download.failure() is None:
                download.save_as(local)
                if is_mp4_video(local):
                    return local
        candidates = _video_links(page, initial)
        for candidate in candidates:
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
        buttons = page.locator(
            "button:visible:not([data-easyscrape-initial]):not([data-easyscrape-clicked])"
        )
        if not resubmitted and not candidates and not buttons.count() and (
            time.monotonic() - started >= 5.0
        ):
            resubmitted = True
            try:
                if field.is_visible():
                    field.fill(url, timeout=5000)
                    _click_submit(page, field)
            except BrowserError:
                pass
        if time.monotonic() >= next_button_click:
            ranked_buttons: list[tuple[int, int, Locator]] = []
            has_hd_option = page.locator(
                "button:visible:not([data-easyscrape-initial])"
            ).evaluate_all(
                """buttons => buttons.some(b => {
                    const parent = b.parentElement && b.parentElement.parentElement;
                    const container = b.closest('tr, li') || (
                      parent && !['BODY', 'HTML', 'FORM'].includes(parent.tagName) ? parent : null
                    );
                    const row = container
                      ? (container.innerText || container.textContent || '')
                      : (b.innerText || b.textContent || '');
                    return /(720p|1080p|1440p|2160p|\\b(720|1080|1440|2160|2k|4k|hd)\\b)/i.test(row)
                      && !/(mp3|kbps|audio)/i.test(row);
                })"""
            )
            for index in range(buttons.count()):
                button = buttons.nth(index)
                context_text = str(
                    button.evaluate(
                        """b => {
                            const parent = b.parentElement && b.parentElement.parentElement;
                            const container = b.closest('tr, li') || (
                              parent && !['BODY', 'HTML', 'FORM'].includes(parent.tagName)
                                ? parent : null
                            );
                            const row = container
                              ? (container.innerText || container.textContent || '') : '';
                            const extra = row && row.length <= 160 ? ' ' + row : '';
                            return ((b.innerText || b.textContent || '') + extra)
                              .replace(/\\s+/g, ' ').trim();
                        }"""
                    )
                )
                if re.search(r"mp3|photo|image|audio|kbps", context_text, re.I) and not re.search(
                    r"video|mp4", context_text, re.I
                ):
                    continue
                if re.search(r"download|mp4|video|1080|720|hd|save", context_text, re.I):
                    score = _quality_score(context_text)
                    if has_hd_option and score < 720:
                        continue
                    ranked_buttons.append((score, -index, button))
            if ranked_buttons:
                _, _, best_button = max(ranked_buttons, key=lambda item: (item[0], item[1]))
                element = best_button.element_handle()
                if element is not None:
                    element.evaluate("button => button.dataset.easyscrapeClicked = 'true'")
                    try:
                        element.click(timeout=5000, no_wait_after=True)
                        next_button_click = time.monotonic() + 8.0
                    except BrowserError:
                        pass
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
