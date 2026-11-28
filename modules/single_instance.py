"""博麗神社只开一扇门：Windows 单实例 + 把已有主窗口提到前台。

不碰自动答题；只在启动入口使用。
开发/自动化测试可设 SHINICHI_ALLOW_MULTI=1 允许多开。
"""
from __future__ import annotations

import atexit
import ctypes
import os
import time
from ctypes import wintypes

ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = "Local\\SpellCardHomework.SingleInstance"
TITLE = "符卡作业簿"

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_mutex = None

# 64 位 Windows 的 HWND/HANDLE 不能用 ctypes 默认的 c_int 接，否则会截断。
_kernel32.CreateMutexW.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_user32.GetAncestor.restype = wintypes.HWND
_user32.FindWindowW.restype = wintypes.HWND
_user32.IsWindow.argtypes = [wintypes.HWND]
_user32.ShowWindow.argtypes = [wintypes.HWND, wintypes.INT]
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]


def _hwnd_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "SpellCardHomework", "instance.hwnd")


def _multi_allowed() -> bool:
    return os.environ.get("SHINICHI_ALLOW_MULTI") == "1"


def begin() -> bool:
    """True=第一个实例；False=已有实例（调用方可 focus_existing 后退出）。"""
    global _mutex
    if _multi_allowed():
        return True
    try:
        handle = _kernel32.CreateMutexW(None, False, MUTEX_NAME)
        if not handle:
            return True
        if _kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            _kernel32.CloseHandle(handle)
            return False
        _mutex = handle
        atexit.register(release)
        return True
    except Exception:
        # 单实例不是启动的硬依赖；API 异常时宁可放行，也不要打不开程序。
        return True


def release() -> None:
    global _mutex
    try:
        if _mutex:
            _kernel32.CloseHandle(_mutex)
            _mutex = None
    except Exception:
        pass
    try:
        os.remove(_hwnd_path())
    except Exception:
        pass


def record_window(root) -> None:
    """主窗口建好后记下 HWND，供第二个实例聚焦。"""
    if _multi_allowed():
        return
    try:
        root.update_idletasks()
        hwnd = int(_user32.GetAncestor(int(root.winfo_id()), 2))  # GA_ROOT
        if not hwnd:
            return
        path = _hwnd_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="ascii") as f:
            f.write(str(hwnd))
    except Exception:
        pass


def focus_existing(timeout: float = 2.0) -> bool:
    """把已有主窗口提到前台；找不到就返回 False。"""
    end = time.time() + max(0.0, timeout)
    while time.time() < end:
        hwnd = 0
        try:
            with open(_hwnd_path(), encoding="ascii") as f:
                hwnd = int((f.read() or "0").strip() or 0)
        except Exception:
            hwnd = 0
        if hwnd and _user32.IsWindow(hwnd):
            try:
                _user32.ShowWindow(hwnd, 9)          # SW_RESTORE
                _user32.SetForegroundWindow(hwnd)
                return True
            except Exception:
                pass
        try:
            hwnd = int(_user32.FindWindowW(None, TITLE) or 0)
            if hwnd:
                _user32.ShowWindow(hwnd, 9)
                _user32.SetForegroundWindow(hwnd)
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False
