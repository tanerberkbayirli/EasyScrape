from __future__ import annotations

import sys
import uuid
from unittest.mock import patch

import pytest

from easyscrape.settings import Settings, load_settings, parse_hotkey, save_settings


def test_missing_settings_use_desktop_and_original_shortcut(tmp_path):
    with patch("easyscrape.settings.desktop_directory", return_value=tmp_path / "Desktop"):
        settings = load_settings(tmp_path / "missing.json")
        assert settings.output_directory == tmp_path / "Desktop"
        assert settings.hotkey == "Ctrl+Shift+D"


def test_settings_persist_unicode_destination_and_shortcut(tmp_path):
    path = tmp_path / "config" / "settings.json"
    preferences = Settings(tmp_path / "Görseller ve videolar", "Ctrl+Alt+F8")
    save_settings(preferences, path)
    assert load_settings(path) == preferences
    assert list(path.parent.iterdir()) == [path]


@pytest.mark.parametrize("content", [
    "not json", "[]", '{"hotkey": "Shift+D", "download_directory": "relative"}',
    '{"hotkey": 123, "download_directory": []}',
])
def test_invalid_settings_fall_back(tmp_path, content):
    path = tmp_path / "settings.json"
    path.write_text(content, encoding="utf-8")
    assert load_settings(path) == Settings()


@pytest.mark.parametrize("hotkey", ["D", "Shift+D", "Ctrl+Ctrl+D", "Ctrl+F25", "Ctrl+Delete"])
def test_invalid_shortcuts(hotkey):
    with pytest.raises(ValueError):
        parse_hotkey(hotkey)


def test_shortcut_virtual_keys():
    assert parse_hotkey("Ctrl+Shift+D") == (0x6, 0x44)
    assert parse_hotkey("Alt+F1") == (0x1, 0x70)
    assert parse_hotkey("Win+F24") == (0x8, 0x87)
    assert parse_hotkey("Ctrl+F") == (0x2, 0x46)


def test_failed_save_keeps_previous_settings(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(Settings(), path)
    with patch("pathlib.Path.replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            save_settings(Settings(tmp_path, "Alt+F8"), path)
    assert load_settings(path) == Settings()
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native hotkey")
def test_hotkey_can_change_without_restart_and_conflict_keeps_previous():
    from easyscrape.activation import WindowsActivation

    first = WindowsActivation("Local\\EasyScrape.Test." + uuid.uuid4().hex, key=0x87)
    conflicting = WindowsActivation("Local\\EasyScrape.Test." + uuid.uuid4().hex, key=0x85)
    try:
        assert first.listen()
        assert conflicting.listen()
        assert first.change_hotkey(0x6, 0x86)
        assert first._key == 0x86
        assert not first.change_hotkey(0x6, 0x85)
        assert first._key == 0x86
        assert first.registered
    finally:
        first.close()
        conflicting.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop GUI")
def test_settings_dialog_save_and_reload(tmp_path):
    from easyscrape.gui import App

    path = tmp_path / "config" / "settings.json"
    app = App(background=True, preferences=Settings())
    try:
        # A hidden owner cannot own a grabbed dialog, so show the test window first.
        app._show()
        app._open_settings()
        dialog = app._settings_window
        assert dialog is not None
        assert dialog.key.get() == "D"
        dialog.folder.set(str(tmp_path / "Kaydedilenler"))
        dialog.modifiers["Shift"].set(False)
        dialog.modifiers["Alt"].set(True)
        dialog.key.set("F8")
        with patch(
            "easyscrape.gui.save_settings", side_effect=lambda value: save_settings(value, path),
        ):
            dialog._save()
        assert not dialog.winfo_exists()
        assert app.preferences == load_settings(path)
        assert app.preferences.hotkey == "Ctrl+Alt+F8"
        assert app.preferences.output_directory == tmp_path / "Kaydedilenler"
        app._open_settings()
        dialog = app._settings_window
        dialog._defaults()
        assert dialog.key.get() == "D"
        assert dialog.modifiers["Ctrl"].get()
        assert dialog.modifiers["Shift"].get()
    finally:
        app.destroy()
