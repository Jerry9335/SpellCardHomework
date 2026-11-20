"""剪贴板截图监听：配合 Win+Shift+S（截图进剪贴板）自动取图。

用 GetClipboardSequenceNumber 判断剪贴板变化，比轮询内容轻得多。
任何图片都会被当成题目，所以调用方要能随时关掉。
"""
from __future__ import annotations

import ctypes
import hashlib
import threading
import time
from dataclasses import dataclass

from PIL import Image, ImageGrab

user32 = ctypes.windll.user32

MIN_W, MIN_H = 90, 40       # 小于这个尺寸当误触


@dataclass
class Shot:
    image: Image.Image
    digest: str


def grab_clipboard_image() -> Image.Image | None:
    """从剪贴板取图：既支持位图，也支持复制的图片文件。"""
    data = None
    for _ in range(3):
        try:
            data = ImageGrab.grabclipboard()
            break
        except Exception:
            time.sleep(0.12)
    if data is None:
        return None
    if isinstance(data, Image.Image):
        return data
    if isinstance(data, list) and data:
        for p in data:
            if str(p).lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
                try:
                    return Image.open(p)
                except Exception:
                    continue
    return None


class ClipboardWatcher(threading.Thread):
    """后台线程：剪贴板出现新图片就回调 on_image(PIL.Image)。"""

    def __init__(self, on_image, enabled=lambda: True, poll: float = 0.25) -> None:
        super().__init__(daemon=True, name="clipboard")
        self.on_image = on_image
        self.enabled = enabled
        self.poll = poll
        self._stop = threading.Event()
        self._last_seq = user32.GetClipboardSequenceNumber()
        self._last_digest = ""

    def run(self) -> None:
        while not self._stop.is_set():
            time.sleep(self.poll)
            if not self.enabled():
                continue
            try:
                seq = user32.GetClipboardSequenceNumber()
            except Exception:
                continue
            if seq == self._last_seq:
                continue
            self._last_seq = seq
            img = grab_clipboard_image()
            if img is None or img.width < MIN_W or img.height < MIN_H:
                continue
            try:
                digest = hashlib.md5(img.convert("RGB").resize((64, 64)).tobytes()).hexdigest()
            except Exception:
                continue
            if digest == self._last_digest:
                continue
            self._last_digest = digest
            try:
                self.on_image(img)
            except Exception:
                pass

    def stop(self) -> None:
        self._stop.set()


def copy_text(text: str) -> bool:
    """把文本放进 Windows 剪贴板（不依赖 tkinter）。"""
    import ctypes
    from ctypes import wintypes

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.restype = wintypes.BOOL

    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL

    data = str(text)
    buf = ctypes.create_unicode_buffer(data)
    size = ctypes.sizeof(buf)

    for _ in range(20):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return False

    try:
        user32.EmptyClipboard()
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not h:
            return False
        ptr = kernel32.GlobalLock(h)
        if not ptr:
            kernel32.GlobalFree(h)
            return False
        ctypes.memmove(ptr, ctypes.addressof(buf), size)
        kernel32.GlobalUnlock(h)
        if not user32.SetClipboardData(CF_UNICODETEXT, h):
            kernel32.GlobalFree(h)
            return False
        return True
    finally:
        user32.CloseClipboard()
