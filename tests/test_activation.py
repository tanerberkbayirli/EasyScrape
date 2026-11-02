from __future__ import annotations

import subprocess
import sys
import time
import uuid

import pytest


def test_gui_import_does_not_load_download_libraries():
    result = subprocess.run(
        [sys.executable, "-c", "import sys; import easyscrape.gui; "
         "assert 'easyscrape.downloader' not in sys.modules; "
         "assert 'playwright.sync_api' not in sys.modules; "
         "assert 'httpx' not in sys.modules"],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native activation")
def test_single_instance_event_and_hotkey_dispatch():
    from easyscrape.activation import WindowsActivation

    name = "Local\\EasyScrape.Test." + uuid.uuid4().hex
    first = WindowsActivation(name, key=0x87)  # F24 avoids the user's real shortcut.
    second = WindowsActivation(name, key=0x87)
    try:
        assert not first.already_running
        assert second.already_running
        second.show()
        assert first.consume_show()
        assert not first.consume_show()
        assert first.listen()
        assert first.user.PostThreadMessageW(first._thread_id, 0x0312, 1, 0)
        deadline = time.monotonic() + 2
        while not first.consume_show():
            assert time.monotonic() < deadline
            time.sleep(0.005)
    finally:
        second.close()
        first.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop GUI")
def test_resident_window_show_hide_and_reactivate():
    from easyscrape.activation import WindowsActivation
    from easyscrape.gui import App

    activation = WindowsActivation("Local\\EasyScrape.Test." + uuid.uuid4().hex)
    app = App(activation=activation, background=True)
    try:
        app.update()
        assert app.state() == "withdrawn"
        for _ in range(3):
            activation.show()
            deadline = time.monotonic() + 2
            while app.state() == "withdrawn":
                app.update()
                assert time.monotonic() < deadline
                time.sleep(0.001)
            app._close()
            assert app.state() == "withdrawn"
        assert not app._busy
        assert not activation.already_running
    finally:
        app.destroy()
        activation.close()
