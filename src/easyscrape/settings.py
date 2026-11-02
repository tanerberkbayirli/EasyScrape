"""Lightweight, persistent user preferences shared by the GUI and downloader."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOTKEY = "Ctrl+Shift+D"
KEYS = tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") + tuple(f"F{i}" for i in range(1, 25))
MODIFIERS = {"Ctrl": 0x2, "Shift": 0x4, "Alt": 0x1, "Win": 0x8}


def parse_hotkey(value: str) -> tuple[int, int]:
    parts = [part.strip() for part in value.split("+")]
    if len(parts) < 2 or len(set(parts)) != len(parts):
        raise ValueError("Bir tuş ve en az Ctrl, Alt veya Win seçin.")
    if parts[-1] not in KEYS or any(part not in MODIFIERS for part in parts[:-1]):
        raise ValueError("Geçersiz kısayol. Harf, rakam veya F1–F24 seçin.")
    modifiers = sum(MODIFIERS[part] for part in parts[:-1])
    if not modifiers & (0x1 | 0x2 | 0x8):
        raise ValueError("Kısayolda Ctrl, Alt veya Win bulunmalı.")
    key = parts[-1]
    return modifiers, 0x70 + int(key[1:]) - 1 if key.startswith("F") and len(key) > 1 else ord(key)


def desktop_directory() -> Path:
    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "Desktop")
                if isinstance(value, str) and value:
                    return Path(os.path.expandvars(value))
        except OSError:
            pass
    for directory in (Path.home() / "Desktop", Path.home() / "OneDrive" / "Desktop"):
        if directory.is_dir():
            return directory
    return Path.home() / "Desktop"


def settings_path() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return root / "EasyScrape" / "settings.json"


@dataclass(frozen=True)
class Settings:
    download_directory: Path | None = None
    hotkey: str = DEFAULT_HOTKEY

    @property
    def output_directory(self) -> Path:
        if self.download_directory is not None:
            return self.download_directory
        return desktop_directory()


def load_settings(path: Path | None = None) -> Settings:
    try:
        data = json.loads((path or settings_path()).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return Settings()
        directory = data.get("download_directory")
        destination = (
            Path(directory).expanduser() if isinstance(directory, str) and directory else None
        )
        if destination is not None and not destination.is_absolute():
            destination = None
        hotkey = data.get("hotkey", DEFAULT_HOTKEY)
        try:
            if not isinstance(hotkey, str):
                raise ValueError
            parse_hotkey(hotkey)
        except ValueError:
            hotkey = DEFAULT_HOTKEY
        return Settings(destination, hotkey)
    except (OSError, ValueError):
        return Settings()


def save_settings(settings: Settings, path: Path | None = None) -> None:
    parse_hotkey(settings.hotkey)
    target = path or settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent, delete=False,
        ) as output:
            temporary = Path(output.name)
            json.dump({
                "download_directory": str(settings.download_directory)
                if settings.download_directory is not None else None,
                "hotkey": settings.hotkey,
            }, output, ensure_ascii=False, indent=2)
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
