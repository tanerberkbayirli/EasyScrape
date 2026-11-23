"""A single-link interface for downloading videos to the Desktop."""

from __future__ import annotations

import ctypes
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

_BG = "#0D111D"
_SURFACE = "#151C2F"
_SURFACE_ALT = "#1E293B"
_SURFACE_HOVER = "#2D3B55"
_INPUT_BG = "#090D18"
_BORDER = "#273556"
_TEXT = "#F8FAFC"
_MUTED = "#94A3B8"
_CYAN = "#22D3EE"
_SKY = "#7DD3FC"
_ACCENT = "#7C3AED"
_ACCENT_HOVER = "#8B5CF6"
_ACCENT_ACTIVE = "#6D28D9"
_SUCCESS = "#34D399"
_SUCCESS_BTN = "#10B981"
_SUCCESS_HOVER = "#059669"
_ERROR = "#FB7185"

_GRADIENT_STOPS = (
    (6, 182, 212),    # Cyan
    (99, 102, 241),   # Indigo
    (236, 72, 153),   # Pink
    (245, 158, 11),   # Amber
)

_PLATFORM_BADGES: tuple[tuple[str, str, str], ...] = (
    ("YouTube", "#FF0033", "#FFFFFF"),
    ("Shorts", "#F43F5E", "#FFFFFF"),
    ("X", "#0EA5E9", "#FFFFFF"),
    ("TikTok", "#00E5D4", "#06131A"),
    ("Instagram", "#E1306C", "#FFFFFF"),
    ("Reels", "#A855F7", "#FFFFFF"),
    ("Reddit", "#FF4500", "#FFFFFF"),
    ("Snapchat", "#FACC15", "#111827"),
    ("Pinterest", "#E60023", "#FFFFFF"),
    ("Threads", "#6366F1", "#FFFFFF"),
)


def _interpolate_gradient(ratio: float) -> str:
    clamped = max(0.0, min(1.0, ratio))
    scaled = clamped * (len(_GRADIENT_STOPS) - 1)
    index = min(int(scaled), len(_GRADIENT_STOPS) - 2)
    local = scaled - index
    r1, g1, b1 = _GRADIENT_STOPS[index]
    r2, g2, b2 = _GRADIENT_STOPS[index + 1]
    r = int(r1 + (r2 - r1) * local)
    g = int(g1 + (g2 - g1) * local)
    b = int(b1 + (b2 - b1) * local)
    return f"#{r:02x}{g:02x}{b:02x}"


def _draw_gradient_bar(canvas: tk.Canvas, width: int, height: int = 4) -> None:
    canvas.delete("all")
    steps = max(1, min(width, 160))
    step_width = width / steps
    for idx in range(steps):
        color = _interpolate_gradient(idx / max(1, steps - 1))
        x0 = int(idx * step_width)
        x1 = int((idx + 1) * step_width) + 1
        canvas.create_rectangle(x0, 0, x1, height, fill=color, outline="")


def _create_app_icon(master: tk.Misc) -> tk.PhotoImage:
    """Create a vibrant gradient square icon with a crisp white download arrow."""
    size = 32
    icon = tk.PhotoImage(master=master, width=size, height=size)
    rows: list[str] = []
    for y in range(size):
        row_pixels: list[str] = []
        for x in range(size):
            # Rounded square mask (radius 7)
            dx = max(0, 7 - x, x - (size - 8))
            dy = max(0, 7 - y, y - (size - 8))
            if dx * dx + dy * dy > 49:
                row_pixels.append(_BG)
                continue
            in_shaft = 13 <= x <= 18 and 7 <= y <= 17
            in_head = 17 <= y <= 24 and abs(x - 15.5) <= (24 - y) * 1.15
            in_base = 25 <= y <= 26 and 9 <= x <= 22
            if in_shaft or in_head or in_base:
                row_pixels.append("#FFFFFF")
            else:
                ratio = (x + y) / (2 * (size - 1))
                r = int(6 + ratio * (236 - 6))
                g = int(182 + ratio * (72 - 182))
                b = int(212 + ratio * (153 - 212))
                row_pixels.append(f"#{r:02x}{g:02x}{b:02x}")
        rows.append("{" + " ".join(row_pixels) + "}")
    icon.put(" ".join(rows))
    return icon


def _apply_windows_dark_titlebar(window: tk.Wm, window_id: int) -> None:
    if sys.platform != "win32":
        return
    library = getattr(ctypes, "WinDLL", None)
    if library is None:
        return
    try:
        dwm = library("dwmapi")
        user = library("user32")
        hwnd = user.GetAncestor(window_id, 2) or window_id
        dark = ctypes.c_int(1)
        # DWMWA_USE_IMMERSIVE_DARK_MODE (20) and DWMWA_CAPTION_COLOR (35, BGR for #0D111D)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))
        caption_bgr = ctypes.c_int(0x001D110D)
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption_bgr), ctypes.sizeof(caption_bgr))
    except OSError:
        pass


def _bind_hover(widget: tk.Button, normal_bg: str, hover_bg: str) -> None:
    def _on_enter(_event: tk.Event[tk.Button]) -> None:
        if str(widget.cget("state")) != "disabled":
            widget.configure(bg=hover_bg)

    def _on_leave(_event: tk.Event[tk.Button]) -> None:
        if str(widget.cget("state")) != "disabled":
            widget.configure(bg=normal_bg)

    widget.bind("<Enter>", _on_enter)
    widget.bind("<Leave>", _on_leave)


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
        self.geometry("650x316")
        self.minsize(580, 300)
        self.configure(bg=_BG)
        self._icon = _create_app_icon(self)
        self.iconphoto(True, self._icon)

        self._messages: queue.Queue[str | None] = queue.Queue()
        self._busy = False
        self._anim_pos = 0.0

        # Top vibrant neon gradient accent bar
        self._top_bar = tk.Canvas(self, height=4, bg=_BG, highlightthickness=0, bd=0)
        self._top_bar.pack(fill="x", side="top")
        self._top_bar.bind(
            "<Configure>",
            lambda event: _draw_gradient_bar(self._top_bar, max(1, event.width), 4),
        )

        body = tk.Frame(self, bg=_BG, padx=20, pady=16)
        body.pack(fill="both", expand=True)

        # Header row: Brand title + HD badge on left, Settings button on right
        header = tk.Frame(body, bg=_BG)
        header.pack(fill="x")
        brand = tk.Frame(header, bg=_BG)
        brand.pack(side="left")
        tk.Label(
            brand, text="EasyScrape", bg=_BG, fg=_TEXT, font=("Segoe UI", 15, "bold"),
        ).pack(side="left")
        tk.Label(
            brand, text="HD MP4", bg=_ACCENT, fg="#FFFFFF",
            font=("Segoe UI", 8, "bold"), padx=7, pady=2,
        ).pack(side="left", padx=(10, 0), pady=(2, 0))

        self._settings_btn = tk.Button(
            header, text="⚙  Ayarlar", command=self._open_settings,
            bg=_SURFACE_ALT, fg=_TEXT, activebackground=_SURFACE_HOVER, activeforeground=_TEXT,
            relief="flat", bd=0, padx=12, pady=5, font=("Segoe UI", 9, "bold"), cursor="hand2",
        )
        self._settings_btn.pack(side="right")
        _bind_hover(self._settings_btn, _SURFACE_ALT, _SURFACE_HOVER)

        # Colorful platform pills (2 balanced rows of 5)
        pills_box = tk.Frame(body, bg=_BG)
        pills_box.pack(fill="x", pady=(10, 12))
        row_one = tk.Frame(pills_box, bg=_BG)
        row_one.pack(fill="x", pady=(0, 5))
        row_two = tk.Frame(pills_box, bg=_BG)
        row_two.pack(fill="x")
        for idx, (label, badge_bg, badge_fg) in enumerate(_PLATFORM_BADGES):
            target_row = row_one if idx < 5 else row_two
            tk.Label(
                target_row, text=label, bg=badge_bg, fg=badge_fg,
                font=("Segoe UI", 8, "bold"), padx=8, pady=2,
            ).pack(side="left", padx=(0, 6))

        # Destination card with vibrant cyan left bar
        dest_card = tk.Frame(body, bg=_SURFACE, highlightbackground=_BORDER, highlightthickness=1)
        dest_card.pack(fill="x", pady=(0, 12))
        tk.Frame(dest_card, bg=_CYAN, width=4).pack(side="left", fill="y")
        self._destination_text = tk.StringVar()
        self._refresh_destination()
        tk.Label(
            dest_card, textvariable=self._destination_text, bg=_SURFACE, fg=_SKY,
            font=("Segoe UI", 9), anchor="w", padx=10, pady=7,
        ).pack(side="left", fill="x", expand=True)
        self._hotkey_label = tk.Label(
            dest_card, text=self.preferences.hotkey, bg=_SURFACE_ALT, fg=_MUTED,
            font=("Segoe UI", 8, "bold"), padx=8, pady=2,
        )
        self._hotkey_label.pack(side="right", padx=10, pady=5)

        # URL input & action row
        action_row = tk.Frame(body, bg=_BG)
        action_row.pack(fill="x", pady=(0, 10))
        self._entry_frame = tk.Frame(
            action_row, bg=_INPUT_BG, highlightbackground=_BORDER,
            highlightcolor=_CYAN, highlightthickness=2,
        )
        self._entry_frame.pack(side="left", fill="x", expand=True, ipady=4)

        self.url = tk.StringVar()
        self.entry = tk.Entry(
            self._entry_frame, textvariable=self.url, bg=_INPUT_BG, fg=_TEXT,
            insertbackground=_CYAN, disabledbackground=_SURFACE, disabledforeground=_MUTED,
            relief="flat", bd=0, font=("Segoe UI", 10),
        )
        self.entry.pack(fill="both", expand=True, padx=10, pady=3)
        self.entry.bind(
            "<FocusIn>", lambda _e: self._entry_frame.configure(highlightbackground=_CYAN),
        )
        self.entry.bind(
            "<FocusOut>", lambda _e: self._entry_frame.configure(highlightbackground=_BORDER),
        )
        self.entry.focus_set()

        self._paste_btn = tk.Button(
            action_row, text="Yapıştır", command=self._paste_url,
            bg=_SURFACE_ALT, fg=_CYAN, activebackground=_SURFACE_HOVER, activeforeground=_TEXT,
            relief="flat", bd=0, padx=12, pady=8, font=("Segoe UI", 9, "bold"), cursor="hand2",
        )
        self._paste_btn.pack(side="left", padx=(8, 0))
        _bind_hover(self._paste_btn, _SURFACE_ALT, _SURFACE_HOVER)

        self.button = tk.Button(
            action_row, text="İndir", command=self._start,
            bg=_ACCENT, fg="#FFFFFF", activebackground=_ACCENT_ACTIVE, activeforeground="#FFFFFF",
            disabledforeground="#94A3B8", relief="flat", bd=0, padx=20, pady=8,
            font=("Segoe UI", 10, "bold"), cursor="hand2",
        )
        self.button.pack(side="left", padx=(8, 0))
        _bind_hover(self.button, _ACCENT, _ACCENT_HOVER)

        # Thin neon activity bar + status bar
        self._progress = tk.Canvas(body, height=3, bg=_SURFACE_ALT, highlightthickness=0, bd=0)
        self._progress.pack(fill="x", pady=(2, 8))

        self.status = tk.StringVar(value="Hazır. Video bağlantısını yapıştırıp İndir'e basın.")
        self._status_label = tk.Label(
            body, textvariable=self.status, bg=_BG, fg=_MUTED,
            font=("Segoe UI", 9), anchor="w", justify="left", wraplength=600,
        )
        self._status_label.pack(fill="x", anchor="w")
        self.status.trace_add("write", lambda *_args: self._tint_status())

        self.bind("<Return>", lambda _event: self._start())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._menu = tk.Menu(
            self, tearoff=False, bg=_SURFACE, fg=_TEXT,
            activebackground=_ACCENT, activeforeground="#FFFFFF", bd=0,
        )
        self._menu.add_command(label="Ayarlar", command=self._open_settings)
        self._menu.add_separator()
        self._menu.add_command(label="Tamamen çık", command=self._exit)
        self.bind("<Button-3>", lambda event: self._menu.tk_popup(event.x_root, event.y_root))
        self.after(100, self._drain)
        if activation is not None:
            self.after(25, self._check_activation)
        if not background:
            self._show()

    def _tint_status(self) -> None:
        text = self.status.get()
        if text.startswith("Kaydedildi:"):
            self._status_label.configure(fg=_SUCCESS)
        elif text.startswith("İndirilemedi:") or "girin" in text or "kullanılıyor" in text:
            self._status_label.configure(fg=_ERROR)
        elif self._busy:
            self._status_label.configure(fg=_CYAN)
        elif text.startswith("Ayarlar kaydedildi"):
            self._status_label.configure(fg=_SUCCESS)
        else:
            self._status_label.configure(fg=_MUTED)

    def _paste_url(self) -> None:
        if self._busy:
            return
        try:
            clip = self.clipboard_get().strip()
        except tk.TclError:
            return
        if clip:
            self.url.set(clip)
            self.entry.icursor("end")
            self.entry.focus_set()

    def _animate_progress(self) -> None:
        self._progress.delete("all")
        if not self._busy:
            return
        width = max(1, self._progress.winfo_width())
        bar_w = max(40, int(width * 0.28))
        self._anim_pos = (self._anim_pos + 0.045) % 1.4
        start_x = int((self._anim_pos - 0.28) * width)
        segments = 16
        seg_w = bar_w / segments
        for i in range(segments):
            color = _interpolate_gradient(i / max(1, segments - 1))
            x0 = int(start_x + i * seg_w)
            x1 = int(start_x + (i + 1) * seg_w) + 1
            self._progress.create_rectangle(x0, 0, x1, 3, fill=color, outline="")
        self.after(30, self._animate_progress)

    def _show(self) -> None:
        self.update_idletasks()
        _apply_windows_dark_titlebar(self, self.winfo_id())
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
        self._hotkey_label.configure(text=preferences.hotkey)
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
        self._anim_pos = 0.0
        self.button.configure(state="disabled", bg=_SURFACE_ALT)
        self._paste_btn.configure(state="disabled")
        self.entry.configure(state="disabled")
        self.status.set("Servis açılıyor...")
        self._animate_progress()
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
                    self._progress.delete("all")
                    self.button.configure(state="normal", bg=_ACCENT)
                    self._paste_btn.configure(state="normal")
                    self.entry.configure(state="normal")
                    self._tint_status()
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
        self.configure(bg=_BG)

        top_bar = tk.Canvas(self, height=4, bg=_BG, highlightthickness=0, bd=0)
        top_bar.pack(fill="x", side="top")
        top_bar.bind(
            "<Configure>",
            lambda event: _draw_gradient_bar(top_bar, max(1, event.width), 4),
        )

        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(
            "Dark.TCombobox",
            fieldbackground=_INPUT_BG, background=_SURFACE_ALT, foreground=_TEXT,
            arrowcolor=_CYAN, bordercolor=_BORDER, lightcolor=_BORDER, darkcolor=_BORDER,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", _INPUT_BG)],
            foreground=[("readonly", _TEXT)],
            selectbackground=[("readonly", _INPUT_BG)],
            selectforeground=[("readonly", _TEXT)],
        )

        body = tk.Frame(self, bg=_BG, padx=20, pady=18)
        body.pack(fill="both", expand=True)

        tk.Label(
            body, text="Kayıt klasörü", bg=_BG, fg=_TEXT, font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        folder_row = tk.Frame(body, bg=_BG)
        folder_row.pack(fill="x", pady=(6, 16))
        self.folder = tk.StringVar(value=str(owner.preferences.output_directory))
        folder_frame = tk.Frame(
            folder_row, bg=_INPUT_BG, highlightbackground=_BORDER,
            highlightcolor=_CYAN, highlightthickness=1,
        )
        folder_frame.pack(side="left", fill="x", expand=True, ipady=3)
        tk.Entry(
            folder_frame, textvariable=self.folder, width=44, bg=_INPUT_BG, fg=_TEXT,
            insertbackground=_CYAN, relief="flat", bd=0, font=("Segoe UI", 9),
        ).pack(fill="both", expand=True, padx=8, pady=2)
        browse_btn = tk.Button(
            folder_row, text="Seç…", command=self._browse,
            bg="#0EA5E9", fg="#FFFFFF", activebackground="#0284C7", activeforeground="#FFFFFF",
            relief="flat", bd=0, padx=12, pady=5, font=("Segoe UI", 9, "bold"), cursor="hand2",
        )
        browse_btn.pack(side="left", padx=(8, 0))
        _bind_hover(browse_btn, "#0EA5E9", "#38BDF8")

        tk.Label(
            body, text="Uygulamayı açma kısayolu", bg=_BG, fg=_TEXT, font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        shortcut_row = tk.Frame(body, bg=_SURFACE, padx=10, pady=8)
        shortcut_row.pack(fill="x", pady=(6, 12))
        parts = owner.preferences.hotkey.split("+")
        self.modifiers = {name: tk.BooleanVar(value=name in parts[:-1]) for name in MODIFIERS}
        for name, variable in self.modifiers.items():
            tk.Checkbutton(
                shortcut_row, text=name, variable=variable,
                bg=_SURFACE, fg=_TEXT, selectcolor=_ACCENT,
                activebackground=_SURFACE, activeforeground=_TEXT,
                highlightthickness=0, bd=0, font=("Segoe UI", 9), cursor="hand2",
            ).pack(side="left", padx=(0, 10))
        self.key = tk.StringVar(value=parts[-1])
        ttk.Combobox(
            shortcut_row, textvariable=self.key, values=KEYS, width=6,
            state="readonly", style="Dark.TCombobox",
        ).pack(side="left", padx=(4, 0))

        self.error = tk.StringVar()
        tk.Label(
            body, textvariable=self.error, bg=_BG, fg=_ERROR,
            font=("Segoe UI", 9), wraplength=470, justify="left",
        ).pack(anchor="w", pady=(0, 10))

        buttons = tk.Frame(body, bg=_BG)
        buttons.pack(fill="x")
        defaults_btn = tk.Button(
            buttons, text="Varsayılanlara dön", command=self._defaults,
            bg=_SURFACE_ALT, fg=_MUTED, activebackground=_SURFACE_HOVER, activeforeground=_TEXT,
            relief="flat", bd=0, padx=12, pady=6, font=("Segoe UI", 9, "bold"), cursor="hand2",
        )
        defaults_btn.pack(side="left")
        _bind_hover(defaults_btn, _SURFACE_ALT, _SURFACE_HOVER)

        save_btn = tk.Button(
            buttons, text="Kaydet", command=self._save,
            bg=_SUCCESS_BTN, fg="#FFFFFF", activebackground=_SUCCESS_HOVER,
            activeforeground="#FFFFFF", relief="flat", bd=0, padx=16, pady=6,
            font=("Segoe UI", 9, "bold"), cursor="hand2",
        )
        save_btn.pack(side="right")
        _bind_hover(save_btn, _SUCCESS_BTN, _SUCCESS_HOVER)

        cancel_btn = tk.Button(
            buttons, text="İptal", command=self.destroy,
            bg=_SURFACE_ALT, fg=_TEXT, activebackground=_SURFACE_HOVER, activeforeground=_TEXT,
            relief="flat", bd=0, padx=12, pady=6, font=("Segoe UI", 9, "bold"), cursor="hand2",
        )
        cancel_btn.pack(side="right", padx=(0, 8))
        _bind_hover(cancel_btn, _SURFACE_ALT, _SURFACE_HOVER)

        self.bind("<Return>", lambda _event: self._save())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.update_idletasks()
        _apply_windows_dark_titlebar(self, self.winfo_id())
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
