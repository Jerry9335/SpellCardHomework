"""全局热键（RegisterHotKey），在独立线程里跑消息循环，窗口不在前台也能触发。"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading
from typing import Callable

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_NOREPEAT = 0x4000


class HotkeyManager(threading.Thread):
    """bindings: {虚拟键码: 名称}，例如 {0x77: 'capture'}。"""

    def __init__(
        self,
        bindings: dict[int, str],
        on_hotkey: Callable[[str], None],
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(daemon=True, name="hotkeys")
        self.bindings = bindings
        self.on_hotkey = on_hotkey
        self.on_error = on_error
        self._thread_id: int | None = None
        self.registered: list[int] = []

    def run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        id_to_name: dict[int, str] = {}
        try:
            for idx, (vk, name) in enumerate(self.bindings.items(), start=1):
                if user32.RegisterHotKey(None, idx, MOD_NOREPEAT, vk):
                    self.registered.append(idx)
                    id_to_name[idx] = name
                elif self.on_error:
                    self.on_error(f"热键 {name} 注册失败（可能被其他程序占用）")
            msg = wt.MSG()
            while True:
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == 0 or ret == -1:
                    break
                if msg.message == WM_HOTKEY:
                    name = id_to_name.get(int(msg.wParam))
                    if name:
                        try:
                            self.on_hotkey(name)
                        except Exception:
                            pass
        finally:
            for idx in self.registered:
                user32.UnregisterHotKey(None, idx)
            self.registered.clear()

    def stop(self) -> None:
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
