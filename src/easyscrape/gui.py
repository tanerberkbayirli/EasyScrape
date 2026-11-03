"""A single-link interface for downloading videos to the Desktop."""

from __future__ import annotations

import queue
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import TYPE_CHECKING

from .settings import (
    DEFAULT_HOTKEY,
    KEYS,
    MODIFIERS,
    Settings,
    desktop_directory,
    load_settings,
    parse_hotkey,
    save_settings,
)

if TYPE_CHECKING:
    from .activation import WindowsActivation


class App(tk.Tk):
    def __init__(
        self, activation: WindowsActivation | None = None, background: bool = False,
        preferences: Settings | None = None,
    ) -> None:
        super().__init__()
        self._activation = activation
        self.preferences = preferences if preferences is not None else load_settings()
        self._settings_window: SettingsDialog | None = None
        self.withdraw()
        self.title("EasyScrape")
        self.geometry("600x240")
        self._messages: queue.Queue[str | None] = queue.Queue()
        self._busy = False
        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        header = ttk.Frame(body)
        header.pack(fill="x")
        ttk.Label(header, text="YouTube · X · TikTok · Instagram · Reddit · Pinterest").pack(
            side="left")
        ttk.Button(header, text="Ayarlar", command=self._open_settings).pack(side="right")
        self._destination_text = tk.StringVar()
        self._refresh_destination()
        ttk.Label(body, textvariable=self._destination_text, wraplength=560).pack(
            anchor="w", pady=(4, 12))
        self.url = tk.StringVar()
        self.entry = ttk.Entry(body, textvariable=self.url)
        self.entry.pack(fill="x")
        self.entry.focus_set()
        self.button = ttk.Button(body, text="İndir", command=self._start)
        self.button.pack(anchor="e", pady=10)
        self.status = tk.StringVar(value="Hazır.")
        ttk.Label(body, textvariable=self.status, wraplength=560).pack(anchor="w")
        self.bind("<Return>", lambda _event: self._start())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._menu = tk.Menu(self, tearoff=False)
        self._menu.add_command(label="Ayarlar", command=self._open_settings)
        self._menu.add_separator()
        self._menu.add_command(label="Tamamen çık", command=self._exit)
        self.bind("<Button-3>", lambda event: self._menu.tk_popup(event.x_root, event.y_root))
        self.after(100, self._drain)
        if activation is not None:
            self.after(25, self._check_activation)
        if not background:
            self._show()

    def _show(self) -> None:
        self.update_idletasks()
        if sys.platform == "win32":
            from .activation import position_bottom_right

            position_bottom_right(self.winfo_id())
        else:
            x = max(0, self.winfo_screenwidth() - self.winfo_width() - 12)
            y = max(0, self.winfo_screenheight() - self.winfo_height() - 60)
            self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after_idle(lambda: self.attributes("-topmost", False))
        self.entry.focus_force()
        if self._settings_window is not None and self._settings_window.winfo_exists():
            self._settings_window.lift()

    def _refresh_destination(self) -> None:
        self._destination_text.set(f"Kayıt yeri: {self.preferences.output_directory}")

    def _open_settings(self) -> None:
        if self._settings_window is not None and self._settings_window.winfo_exists():
            self._settings_window.lift()
            return
        self._settings_window = SettingsDialog(self)

    def _apply_settings(self, preferences: Settings) -> None:
        directory = preferences.output_directory
        if not directory.is_absolute():
            raise ValueError("Tam bir klasör yolu seçin.")
        directory.mkdir(parents=True, exist_ok=True)
        # Detect unwritable folders before persisting them or changing the hotkey.
        with tempfile.TemporaryFile(dir=directory):
            pass
        modifiers, key = parse_hotkey(preferences.hotkey)
        previous = self.preferences
        if self._activation is not None and not self._activation.change_hotkey(modifiers, key):
            raise ValueError("Bu kısayol başka bir uygulamada kullanılıyor. Başka bir tuş seçin.")
        try:
            save_settings(preferences)
        except OSError:
            if self._activation is not None:
                self._activation.change_hotkey(*parse_hotkey(previous.hotkey))
            raise
        self.preferences = preferences
        self._refresh_destination()
        self.status.set(f"Ayarlar kaydedildi. Kısayol: {preferences.hotkey}")

    def _check_activation(self) -> None:
        if self._activation is not None and self._activation.consume_show():
            self._show()
        self.after(25, self._check_activation)

    def _start(self) -> None:
        if self._busy:
            return
        url = self.url.get().strip()
        if not url:
            self.status.set("Bir video bağlantısı girin.")
            return
        self._busy = True
        self.button.configure(state="disabled")
        self.entry.configure(state="disabled")
        self.status.set("Servis açılıyor...")
        threading.Thread(
            target=self._download, args=(url, self.preferences.output_directory), daemon=True,
        ).start()

    def _download(self, url: str, directory: Path) -> None:
        try:
            # Heavy browser/network libraries are needed only after clicking Download.
            from .downloader import DownloadError, download_video

            try:
                path = download_video(url, log=self._messages.put, output_directory=directory)
                self._messages.put(f"Kaydedildi: {path}")
            except DownloadError as exc:
                self._messages.put(f"İndirilemedi: {exc}")
        except (ImportError, OSError) as exc:
            self._messages.put(f"İndirilemedi: {exc}")
        finally:
            self._messages.put(None)

    def _drain(self) -> None:
        try:
            while True:
                message = self._messages.get_nowait()
                if message is None:
                    self._busy = False
                    self.button.configure(state="normal")
                    self.entry.configure(state="normal")
                else:
                    self.status.set(message)
        except queue.Empty:
            pass
        self.after(100, self._drain)

    def _close(self) -> None:
        if self._busy:
            self.status.set("İndirmeyi durdurmak için açılan tarayıcıyı kapatın.")
        else:
            if self._activation is not None:
                self.withdraw()
            else:
                self.destroy()

    def _exit(self) -> None:
        if self._busy:
            self.status.set("İndirmeyi durdurmak için açılan tarayıcıyı kapatın.")
        else:
            self.destroy()


class SettingsDialog(tk.Toplevel):
    def __init__(self, owner: App) -> None:
        super().__init__(owner)
        self.owner = owner
        self.title("Ayarlar")
        self.transient(owner)
        self.resizable(False, False)
        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Kayıt klasörü").pack(anchor="w")
        folder_row = ttk.Frame(body)
        folder_row.pack(fill="x", pady=(4, 16))
        self.folder = tk.StringVar(value=str(owner.preferences.output_directory))
        ttk.Entry(folder_row, textvariable=self.folder, width=48).pack(side="left", fill="x")
        ttk.Button(folder_row, text="Seç…", command=self._browse).pack(side="left", padx=(6, 0))
        ttk.Label(body, text="Uygulamayı açma kısayolu").pack(anchor="w")
        shortcut_row = ttk.Frame(body)
        shortcut_row.pack(fill="x", pady=(4, 12))
        parts = owner.preferences.hotkey.split("+")
        self.modifiers = {name: tk.BooleanVar(value=name in parts[:-1]) for name in MODIFIERS}
        for name, variable in self.modifiers.items():
            ttk.Checkbutton(shortcut_row, text=name, variable=variable).pack(
                side="left", padx=(0, 8))
        self.key = tk.StringVar(value=parts[-1])
        ttk.Combobox(
            shortcut_row, textvariable=self.key, values=KEYS, width=5, state="readonly",
        ).pack(side="left")
        self.error = tk.StringVar()
        ttk.Label(body, textvariable=self.error, foreground="#b42318", wraplength=470).pack(
            anchor="w", pady=(0, 8))
        buttons = ttk.Frame(body)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Varsayılanlara dön", command=self._defaults).pack(side="left")
        ttk.Button(buttons, text="Kaydet", command=self._save).pack(side="right")
        ttk.Button(buttons, text="İptal", command=self.destroy).pack(side="right", padx=6)
        self.bind("<Return>", lambda _event: self._save())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.update_idletasks()
        x = max(0, owner.winfo_rootx() + (owner.winfo_width() - self.winfo_width()) // 2)
        y = max(0, owner.winfo_rooty() + (owner.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{x}+{y}")
        self.grab_set()

    def _browse(self) -> None:
        selected = filedialog.askdirectory(
            parent=self, title="Kayıt klasörünü seçin", initialdir=self.folder.get(),
        )
        if selected:
            self.folder.set(selected)

    def _defaults(self) -> None:
        self.folder.set(str(desktop_directory()))
        for name, variable in self.modifiers.items():
            variable.set(name in DEFAULT_HOTKEY.split("+")[:-1])
        self.key.set("D")
        self.error.set("")

    def _save(self) -> None:
        try:
            if not self.folder.get().strip():
                raise ValueError("Bir kayıt klasörü seçin.")
            directory = Path(self.folder.get().strip()).expanduser()
            shortcut = "+".join(
                [name for name, variable in self.modifiers.items() if variable.get()]
                + [self.key.get()]
            )
            parse_hotkey(shortcut)
            self.owner._apply_settings(Settings(
                None if directory == desktop_directory() else directory, shortcut,
            ))
        except (ValueError, OSError) as exc:
            self.error.set(str(exc))
            return
        self.destroy()


def main() -> int:
    preferences = load_settings()
    activation = None
    if sys.platform == "win32":
        from .activation import WindowsActivation

        modifiers, key = parse_hotkey(preferences.hotkey)
        activation = WindowsActivation(key=key, modifiers=modifiers)
        if activation.already_running:
            if "--background" not in sys.argv:
                activation.show()
            activation.close()
            return 0
    try:
        app = App(
            activation=activation, background="--background" in sys.argv, preferences=preferences,
        )
        if activation is not None and not activation.listen():
            app.status.set(f"{preferences.hotkey} başka bir uygulama tarafından kullanılıyor.")
        app.mainloop()
    finally:
        if activation is not None:
            activation.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
