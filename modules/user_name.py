"""当前 Windows 账户的显示名。

优先使用 secur32.GetUserNameExW(NameDisplay)：
- 微软账户：返回微软账户显示名
- 本地账户：有全名时返回全名，否则通常等于用户名

再用 IdentityCRL 注册表判断是否登录过微软账户：
- 微软账户 → 用显示名
- 本地账户 → 用本地用户名（USERNAME）
- 都取不到 → 「旅人」
"""
from __future__ import annotations

import ctypes
import getpass
import os

try:
    import winreg
except Exception:  # pragma: no cover - 非 Windows
    winreg = None

NAME_DISPLAY = 3


def _clean(name: str) -> str:
    name = " ".join(str(name or "").split())
    if "\\" in name:
        name = name.split("\\")[-1]
    if "@" in name:
        name = name.split("@")[0]
    return name[:32]


def _local_user() -> str:
    name = _clean(os.environ.get("USERNAME") or "")
    if name:
        return name
    try:
        return _clean(getpass.getuser())
    except Exception:
        return ""


def _display_name() -> str:
    try:
        secur32 = ctypes.windll.secur32
        buf = ctypes.create_unicode_buffer(512)
        size = ctypes.c_ulong(512)
        if secur32.GetUserNameExW(NAME_DISPLAY, buf, ctypes.byref(size)):
            return _clean(buf.value)
    except Exception:
        pass
    try:
        return _clean(getpass.getuser())
    except Exception:
        return ""


def _has_ms_account() -> bool:
    """当前用户配置里是否存在微软账户身份记录。"""
    if winreg is None:
        return False
    paths = (
        r"Software\Microsoft\IdentityCRL\StoredIdentities",
        r"Software\Microsoft\IdentityCRL\UserExtendedProperties",
    )
    for path in paths:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                if winreg.QueryInfoKey(key)[0] > 0:
                    return True
        except OSError:
            continue
    return False


def current_display_name() -> str:
    local = _local_user()
    display = _display_name()
    if _has_ms_account():
        return display or local or "旅人"
    return local or display or "旅人"
