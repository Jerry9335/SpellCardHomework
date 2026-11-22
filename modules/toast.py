"""Windows 10/11 Toast 通知（PowerShell + WinRT，不引入 Python 依赖）。

用 ToastImageAndText02 模板：左边是「谁在说话」的圆形头像，右边是标题和正文。
头像来自 assets/char/toast/avatar_<角色>.png（已做圆形裁切）。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

AUMID = "符卡作业簿"

_PS_TEMPLATE = r"""
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$templateType = [Windows.UI.Notifications.ToastTemplateType]::__TEMPLATE__
$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($templateType)
$x = $t.GetElementsByTagName('text')
$x.Item(0).AppendChild($t.CreateTextNode($env:SCH_TOAST_TITLE)) > $null
$x.Item(1).AppendChild($t.CreateTextNode($env:SCH_TOAST_BODY)) > $null
if ($env:SCH_TOAST_ICON) {
  $img = $t.GetElementsByTagName('image').Item(0)
  if ($img) { $img.SetAttribute('src', $env:SCH_TOAST_ICON) }
}
$n = [Windows.UI.Notifications.ToastNotification]::new($t)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:SCH_TOAST_AUMID).Show($n)
"""

AVATARS = ("reimu", "marisa", "aya", "sakuya", "keine", "patchouli",
           "remilia", "flandre", "yukari")


def _asset_dirs() -> list[str]:
    out = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        out.append(os.path.join(meipass, "assets"))
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out.append(os.path.join(here, "assets"))
    return out


def avatar_path(name: str) -> str:
    """找某个角色的圆形头像；找不到返回空串。"""
    name = (name or "").strip().lower()
    if not name:
        return ""
    for base in _asset_dirs():
        p = os.path.join(base, "char", "toast", f"avatar_{name}.png")
        if os.path.exists(p):
            return p
    return ""


def icon_path() -> str:
    """兜底图标：程序图标。"""
    for base in _asset_dirs():
        for name in ("toast_icon.png", "icon.png"):
            p = os.path.join(base, name)
            if os.path.exists(p):
                return p
    return ""


def show(title: str, body: str, aumid: str = AUMID,
         icon: str = "", avatar: str = "", timeout: float = 8.0) -> bool:
    """弹一条带角色头像的系统通知；失败返回 False。

    avatar: reimu / marisa / yukari ...；传了就用对应圆形头像。
    """
    image = ""
    if avatar:
        image = avatar_path(avatar)
    if not image:
        image = icon or icon_path()

    template = "ToastText02"
    icon_uri = ""
    if image:
        try:
            icon_uri = Path(image).resolve().as_uri()
            template = "ToastImageAndText02"
        except Exception:
            icon_uri = ""
    ps = _PS_TEMPLATE.replace("__TEMPLATE__", template)

    env = dict(os.environ)
    env["SCH_TOAST_TITLE"] = str(title or "符卡作业簿")[:64]
    env["SCH_TOAST_BODY"] = str(body or "")[:256]
    env["SCH_TOAST_ICON"] = icon_uri
    env["SCH_TOAST_AUMID"] = aumid
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            env=env,
            capture_output=True,
            timeout=timeout,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        return r.returncode == 0
    except Exception:
        return False


def in_quiet(cfg: dict, now=None) -> bool:
    """当前是否处于安静时段（默认 23:00–08:00）。"""
    import datetime as _dt

    now = now or _dt.datetime.now()
    try:
        start = int(cfg.get("toast_quiet_start", 23))
        end = int(cfg.get("toast_quiet_end", 8))
    except Exception:
        return False
    if start == end:
        return False
    h = now.hour
    if start < end:
        return start <= h < end
    return h >= start or h < end
