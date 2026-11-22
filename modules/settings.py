"""配置读写：%APPDATA%\\SpellCardHomework\\config.json，API Key 用 Windows DPAPI 加密。"""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wt
import json
import os

APP_DIRNAME = "SpellCardHomework"
APP_TITLE = "符卡作业簿"
APP_VERSION = "1.0.5"


def config_dir() -> str:
    env = os.environ.get("SHINICHI_CONFIG_DIR")
    if env:
        d = env
    else:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = os.path.join(base, APP_DIRNAME)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        import tempfile

        d = os.path.join(tempfile.gettempdir(), APP_DIRNAME)
        os.makedirs(d, exist_ok=True)
    return d


CONFIG_PATH = os.path.join(config_dir(), "config.json")

DEFAULTS: dict = {
    "base_url": "https://api.deepseek.com/v1",
    "api_key_enc": "",
    "model": "deepseek-flash",
    "vision_model": "",
    "vision_base_url": "",
    "vision_api_key_enc": "",
    "effort": "自动（默认）",
    "ocr_mode": "自动",
    "translate": True,
    "temperature": 0.2,
    "extra_json": "",
    "capture_method": "screen",
    "region": None,
    "window_title": "",
    "auto_enabled": False,
    "auto_interval": 1.5,
    "auto_settle": 0.8,
    "auto_threshold": 1.5,
    "auto_cooldown": 4.0,
    "geometry": "",
    "minimize_on_capture": False,
    "save_key": True,
    "web_port": 9222,
    "clipboard_on": True,
    "auto_browser_only": True,
    # 更新
    "update_enabled": True,
    "update_channel": "auto",
    "update_interval_hours": 5,
    "update_last_check": 0,
    "update_snooze_until": 0,
    "update_repo": "Jerry9335/SpellCardHomework",
    "update_gitee_repo": "jerry6663/SpellCardHomework",
    "update_last_version": "",
    "update_max_threads": 8,
    # 通知
    "toast_enabled": True,
    "toast_update": True,
    "toast_trial": True,
    "toast_balance": True,
    "toast_auto": True,
    "toast_quiet_start": 23,
    "toast_quiet_end": 8,
    "toast_seen": {},
    # 主题
    "theme": "classic",
    "theme_unlocked": False,
}


class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


CRYPTPROTECT_UI_FORBIDDEN = 0x1


def _protect(text: str) -> str:
    if not text:
        return ""
    try:
        raw = text.encode("utf-8")
        buf_in = ctypes.create_string_buffer(raw, len(raw))
        blob_in = _BLOB(len(raw), ctypes.cast(buf_in, ctypes.POINTER(ctypes.c_char)))
        blob_out = _BLOB()
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in), "SpellCardHomework", None, None, None,
            CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out),
        )
        if not ok:
            return ""
        try:
            data = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return "dpapi:" + base64.b64encode(data).decode("ascii")
    except Exception:
        return ""


def _unprotect(stored: str) -> str:
    if not stored:
        return ""
    if not stored.startswith("dpapi:"):
        return stored  # 旧版本明文
    try:
        raw = base64.b64decode(stored[6:])
        buf_in = ctypes.create_string_buffer(raw, len(raw))
        blob_in = _BLOB(len(raw), ctypes.cast(buf_in, ctypes.POINTER(ctypes.c_char)))
        blob_out = _BLOB()
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None,
            CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out),
        )
        if not ok:
            return ""
        try:
            data = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
        return data.decode("utf-8", "replace")
    except Exception:
        return ""


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
    except FileNotFoundError:
        pass
    except Exception:
        pass
    cfg["api_key"] = _unprotect(cfg.get("api_key_enc", ""))
    cfg["vision_api_key"] = _unprotect(cfg.get("vision_api_key_enc", ""))
    return cfg


def save(cfg: dict) -> None:
    data = dict(cfg)
    data.pop("api_key", None)
    key = cfg.get("api_key", "")
    data["api_key_enc"] = _protect(key) if cfg.get("save_key", True) else ""
    vkey = cfg.get("vision_api_key", "")
    data["vision_api_key_enc"] = _protect(vkey) if cfg.get("save_key", True) else ""
    data.pop("vision_api_key", None)
    tmp = CONFIG_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_PATH)
    except Exception:
        pass

