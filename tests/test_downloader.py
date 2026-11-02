from __future__ import annotations

import struct
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import pytest
from playwright.sync_api import Error, sync_playwright

from easyscrape import downloader
from easyscrape.cli import main
from easyscrape.downloader import (
    SERVICES,
    DownloadError,
    _run_service,
    _video_links,
    is_mp4_video,
    resolve_service,
    save_video,
)
from easyscrape.settings import desktop_directory


def box(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", 8 + len(data)) + kind + data


VIDEO = box(b"ftyp", b"isom\0\0\0\0isommp42") + box(
    b"moov", box(b"trak", box(b"mdia", box(b"hdlr", b"\0" * 8 + b"vide" + b"\0" * 12)))
)


@pytest.mark.parametrize(("url", "platform"), [
    ("https://x.com/a/status/1", "X"),
    ("https://mobile.twitter.com/a/status/1", "X"),
    ("https://www.tiktok.com/@a/video/1", "TikTok"),
    ("https://vm.tiktok.com/abc/", "TikTok"),
    ("https://vt.tiktok.com/abc/", "TikTok"),
    ("https://www.instagram.com/reel/abc/", "Instagram"),
    ("https://www.reddit.com/r/test/comments/abc/title", "Reddit"),
    ("https://redd.it/abc", "Reddit"),
    ("https://www.pinterest.com/pin/123/", "Pinterest"),
    ("https://pin.it/abc", "Pinterest"),
    ("https://tr.pinterest.com/pin/1/", "Pinterest"),
    ("https://www.pinterest.com.tr/pin/1/", "Pinterest"),
    (" HTTPS://X.COM/a/status/1 ", "X"),
])
def test_platform_detection(url, platform):
    assert resolve_service(url).platform == platform


@pytest.mark.parametrize("url", [
    "https://youtube.com/watch?v=abc", "https://spotify.com/track/abc", "links.txt", "",
    "https://x.com.evil.test/video", "https://evilx.com/video", "https://x.com@evil.test/",
    "https://me:password@x.com/video", "file:///x.com/video", "https://x.com:123/video",
    "https://x.com:bad/video", "http://[broken", "https://instagram.com.evil.test/reel/1",
])
def test_unsupported_or_deceptive_links(url):
    with pytest.raises(DownloadError):
        resolve_service(url)


@pytest.mark.parametrize("payload", [
    b"<html>Download failed</html>" * 10,
    VIDEO.replace(b"vide", b"soun"), b"", b"\0\0\0\0ftyp",
])
def test_reject_non_video(tmp_path, payload):
    source = tmp_path / "source"
    source.write_bytes(payload)
    assert not is_mp4_video(source)
    with pytest.raises(DownloadError):
        save_video(source, tmp_path / "Desktop", "X")
    assert not (tmp_path / "Desktop").exists()


def test_unique_delivery_and_no_extra_files(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(VIDEO)
    desktop = tmp_path / "Desktop"
    with patch.object(downloader.time, "strftime", return_value="20261102_213000"):
        first = save_video(source, desktop, "X")
        second = save_video(source, desktop, "X")
    assert first != second
    assert first.read_bytes() == second.read_bytes() == VIDEO
    assert first.name == "x_20261102_213000.mp4"
    assert second.name == "x_20261102_213000_2.mp4"
    assert set(desktop.iterdir()) == {first, second}


def test_copy_failure_removes_partial_file(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(VIDEO)
    with patch.object(downloader.shutil, "copyfileobj", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            save_video(source, tmp_path / "Desktop", "X")
    assert list((tmp_path / "Desktop").iterdir()) == []


def test_cli_rejects_old_features():
    with pytest.raises(SystemExit) as exc:
        main(["https://x.com/a/status/1", "--audio-only"])
    assert exc.value.code == 2


def test_cli_download_error(capsys):
    assert main(["https://youtube.com/watch?v=abc"]) == 1
    assert "destekleniyor" in capsys.readouterr().err


def test_cli_success(tmp_path, capsys):
    target = tmp_path / "Desktop" / "x.mp4"
    with patch("easyscrape.cli.download_video", return_value=target) as download:
        assert main(["https://x.com/a/status/1"]) == 0
    assert download.call_args.args == ("https://x.com/a/status/1",)
    assert str(target) in capsys.readouterr().out


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        instance = None
        for channel in (None, "msedge", "chrome"):
            try:
                instance = playwright.chromium.launch(headless=True, channel=channel)
                break
            except Error:
                continue
        if instance is None:
            pytest.fail("Tarayıcı testleri için: python -m playwright install chromium")
        yield instance
        instance.close()


@pytest.fixture
def video_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(VIDEO)))
            self.end_headers()
            self.wfile.write(VIDEO)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/video.mp4"
    server.shutdown()
    thread.join()
    server.server_close()


@pytest.mark.parametrize("service", SERVICES, ids=lambda service: service.platform)
@pytest.mark.parametrize("form_kind", ["form", "standalone"])
def test_browser_form_to_desktop(browser, video_server, tmp_path, service, form_kind):
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()
    wrapper = "form" if form_kind == "form" else "div"
    action = "onsubmit='prepare(); return false'" if wrapper == "form" else ""
    button_action = "" if wrapper == "form" else "onclick='prepare()'"
    html = f"""<html><body>
        <a href='/pinterest-downloader'>Pinterest downloader</a>
        <{wrapper} {action}>
          <input id='main_page_text' type='text'>
          <button type='submit' {button_action}>Download</button>
        </{wrapper}>
        <div id='result'></div>
        <script>function prepare() {{
          window.submitted = document.querySelector('input').value;
          document.querySelector('#result').innerHTML =
            '<a href="{video_server}">Download Video with Audio 1080p</a>';
        }}</script>
        </body></html>"""
    context.route("**/*", lambda route: route.fulfill(content_type="text/html", body=html))
    url = f"https://{service.domains[0]}/test-video"
    try:
        video = _run_service(page, service, url, tmp_path, lambda message: None)
        assert page.evaluate("window.submitted") == url
        assert page.url == service.url
        target = save_video(video, tmp_path / "Desktop", service.platform)
        assert target.read_bytes() == VIDEO
        assert list((tmp_path / "Desktop").iterdir()) == [target]
    finally:
        context.close()


def test_result_filter_preserves_video_with_audio(browser):
    page = browser.new_page()
    try:
        page.set_content("""
          <a href='https://test.invalid/nav'>Video Downloader</a>
          <a href='https://test.invalid/music.mp3'>Download MP3</a>
          <a href='https://test.invalid/photo.jpg'>Download Photo</a>
          <a href='https://test.invalid/file.mp4'>Download Video with Audio 1080p</a>
        """)
        assert _video_links(page, {"https://test.invalid/nav"}) == [
            "https://test.invalid/file.mp4"
        ]
    finally:
        page.close()


def test_browser_native_blob_download(browser, tmp_path):
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()
    html = """<form onsubmit='prepare(); return false'>
        <input id='main_page_text' type='text'><button type='submit'>Download</button>
        </form><script>function prepare() {
          const blob = new Blob([new Uint8Array(VIDEO_BYTES)], {type: 'video/mp4'});
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob); a.download = 'clip.mp4';
          document.body.appendChild(a); a.click();
        }</script>""".replace("VIDEO_BYTES", str(list(VIDEO)))
    context.route("**/*", lambda route: route.fulfill(content_type="text/html", body=html))
    try:
        result = _run_service(
            page, SERVICES[0], "https://x.com/a/status/1", tmp_path, lambda message: None
        )
        assert result.read_bytes() == VIDEO
    finally:
        context.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Desktop registry")
def test_redirected_windows_desktop(tmp_path):
    import winreg

    redirected = tmp_path / "OneDrive" / "Masaüstü"
    with patch.object(winreg, "QueryValueEx", return_value=(str(redirected), winreg.REG_SZ)):
        assert desktop_directory() == redirected
