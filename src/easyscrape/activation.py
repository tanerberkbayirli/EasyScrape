"""Windows single-instance activation and a native global keyboard shortcut."""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes


def position_bottom_right(window_id: int, margin: int = 12) -> None:
    """Place the full window frame inside the primary monitor's usable area."""
    library = getattr(ctypes, "WinDLL", None)
    if library is None:
        return
    user = library("user32", use_last_error=True)
    user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetAncestor.restype = wintypes.HWND
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.SystemParametersInfoW.argtypes = [
        wintypes.UINT, wintypes.UINT, wintypes.LPVOID, wintypes.UINT,
    ]
    user.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    window = user.GetAncestor(window_id, 2)  # GA_ROOT includes the title bar and borders.
    work, frame = wintypes.RECT(), wintypes.RECT()
    if not user.SystemParametersInfoW(0x0030, 0, ctypes.byref(work), 0):
        return
    if not user.GetWindowRect(window, ctypes.byref(frame)):
        return
    x = max(work.left, work.right - (frame.right - frame.left) - margin)
    y = max(work.top, work.bottom - (frame.bottom - frame.top) - margin)
    user.SetWindowPos(window, None, x, y, 0, 0, 0x0015)  # NOSIZE | NOZORDER | NOACTIVATE


class WindowsActivation:
    def __init__(
        self, name: str = "Local\\EasyScrape.Desktop.v2", key: int = 0x44, modifiers: int = 0x6,
    ) -> None:
        library = getattr(ctypes, "WinDLL", None)
        self._get_error = getattr(ctypes, "get_last_error", None)
        self._win_error = getattr(ctypes, "WinError", None)
        if library is None or self._get_error is None or self._win_error is None:
            raise OSError("Global keyboard activation requires Windows.")
        self._key = key
        self._modifiers = modifiers
        self.kernel = library("kernel32", use_last_error=True)
        self.user = library("user32", use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel.CreateMutexW.restype = wintypes.HANDLE
        self.kernel.CreateEventW.argtypes = [
            wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR,
        ]
        self.kernel.CreateEventW.restype = wintypes.HANDLE
        self.kernel.SetEvent.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel.GetCurrentThreadId.restype = wintypes.DWORD
        self.user.RegisterHotKey.argtypes = [
            wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT,
        ]
        self.user.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
        ]
        self.user.PeekMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG), wintypes.HWND,
            wintypes.UINT, wintypes.UINT, wintypes.UINT,
        ]
        self.user.PostThreadMessageW.argtypes = [
            wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        ]
        self.mutex = self.kernel.CreateMutexW(None, False, name)
        if not self.mutex:
            raise self._win_error(self._get_error())
        self.already_running = self._get_error() == 183
        self.event = self.kernel.CreateEventW(None, False, False, name + ".Show")
        if not self.event:
            self.kernel.CloseHandle(self.mutex)
            raise self._win_error(self._get_error())
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self.registered = False
        self._ready = threading.Event()
        self._change_ready = threading.Event()
        self._change_success = False
        self._change_lock = threading.Lock()

    def change_hotkey(self, modifiers: int, key: int) -> bool:
        """Register the replacement first, retaining the old shortcut on a conflict."""
        with self._change_lock:
            if self.registered and (modifiers, key) == (self._modifiers, self._key):
                return True
            if self._thread is None or not self._thread.is_alive():
                previous = self._modifiers, self._key
                self._modifiers, self._key = modifiers, key
                if self.listen():
                    return True
                self._modifiers, self._key = previous
                return False
            self._change_ready.clear()
            self._change_success = False
            if not self.user.PostThreadMessageW(self._thread_id, 0x8001, modifiers, key):
                return False
            return self._change_ready.wait(timeout=2) and self._change_success

    def show(self) -> None:
        self.kernel.SetEvent(self.event)

    def consume_show(self) -> bool:
        return bool(self.kernel.WaitForSingleObject(self.event, 0) == 0)

    def listen(self) -> bool:
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2)
        return self.registered

    def _listen(self) -> None:
        self._thread_id = self.kernel.GetCurrentThreadId()
        message = wintypes.MSG()
        self.user.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        active_id = 1
        self.registered = bool(
            self.user.RegisterHotKey(None, active_id, self._modifiers | 0x4000, self._key)
        )
        self._ready.set()
        if not self.registered:
            return
        try:
            while self.user.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == 0x0312:  # WM_HOTKEY
                    self.show()
                elif message.message == 0x8001:
                    modifiers, key = int(message.wParam), int(message.lParam)
                    replacement = 2 if active_id == 1 else 1
                    self._change_success = bool(
                        self.user.RegisterHotKey(None, replacement, modifiers | 0x4000, key)
                    )
                    if self._change_success:
                        self.user.UnregisterHotKey(None, active_id)
                        active_id = replacement
                        self._modifiers, self._key = modifiers, key
                    self._change_ready.set()
        finally:
            self.user.UnregisterHotKey(None, active_id)

    def close(self) -> None:
        if self._thread and self._thread.is_alive():
            self.user.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT
            self._thread.join(timeout=2)
        self.kernel.CloseHandle(self.event)
        self.kernel.CloseHandle(self.mutex)
