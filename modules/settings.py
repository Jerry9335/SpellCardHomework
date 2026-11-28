"""配置读写：%APPDATA%\\SpellCardHomework\\config.json，API Key 用 Windows DPAPI 加密。"""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wt
import json
import math
import os
import shutil
import time

APP_DIRNAME = "SpellCardHomework"
APP_TITLE = "符卡作业簿"
APP_VERSION = "1.1.7-hotfix"


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
    # 魔理沙：DeepSeek 家请得来的式神就这两位，别把名字写岔了。
    "model": "deepseek-chat",
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
    "web_autostart": False,
    "web_start_url": "https://kysu.edu",
    "web_continue_on_wrong": True,
    "clipboard_on": True,
    "auto_browser_only": True,
    # 更新
    "update_enabled": True,
    "update_channel": "auto",
    "update_interval_hours": 1,
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
    # 首次安装 / 新手引导
    "onboarding_state": "",
    "onboarding_version": "",
    "onboarding_done_at": "",
    "onboarding_api_skipped": False,
    "onboarding_tour_skipped": False,
    "onboarding_reinstall": False,
    "onboarding_resume_step": 1,
    # 更新说明已读版本；不持久化会导致每次启动都重弹。
    "whats_new_seen_version": "",
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


# ------------------------------------------------------------------ 契约的校对
# 帕秋莉：契约上每一行都有定式。数字抄成字、坐标少一笔，施术时都会炸开，
# 所以翻开来先校对一遍；读不懂的行，一律照书上的定式重抄。
_FLOAT_KEYS = frozenset({
    "temperature", "auto_interval", "auto_settle", "auto_threshold", "auto_cooldown",
})
_INT_KEYS = {
    # 键: (最小值, 最大值)；越界当成墨迹涂坏，回退默认值。
    "web_port": (1024, 65535),
    "update_interval_hours": (1, 8760),
    "update_last_check": (0, 10 ** 12),
    "update_snooze_until": (0, 10 ** 12),
    "update_max_threads": (1, 32),
    "toast_quiet_start": (0, 23),
    "toast_quiet_end": (0, 23),
    "onboarding_resume_step": (1, 9),
}
_BOOL_KEYS = frozenset({
    "translate", "auto_enabled", "minimize_on_capture", "save_key",
    "web_autostart", "web_continue_on_wrong", "clipboard_on",
    "auto_browser_only", "update_enabled", "toast_enabled", "toast_update",
    "toast_trial", "toast_balance", "toast_auto", "theme_unlocked",
    "onboarding_api_skipped", "onboarding_tour_skipped", "onboarding_reinstall",
})
_STR_KEYS = frozenset({
    "base_url", "api_key_enc", "model", "vision_model", "vision_base_url",
    "vision_api_key_enc", "effort", "ocr_mode", "extra_json", "capture_method",
    "window_title", "geometry", "web_start_url", "update_channel",
    "update_repo", "update_gitee_repo", "update_last_version", "theme",
    "onboarding_state", "onboarding_version", "onboarding_done_at",
    "whats_new_seen_version",
})
_TRUE_WORDS = frozenset({"1", "true", "yes", "on", "y", "t", "是", "真"})
_FALSE_WORDS = frozenset({"0", "false", "no", "off", "n", "f", "否", "假", ""})


def _as_float(value, default: float) -> float:
    """咲夜：时间、温度这类数，宁可重抄，也不能带一个读不懂的字进阵。"""
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _as_int(value, default: int, limits: tuple | None = None) -> int:
    """咲夜：整数要落在钟点允许的范围里，越界就按默认的时辰重写。"""
    if isinstance(value, bool) or value is None:
        return default
    try:
        if isinstance(value, float):
            if not math.isfinite(value) or value != int(value):
                return default
            number = int(value)
        elif isinstance(value, int):
            number = value
        elif isinstance(value, str):
            number = int(value.strip())
        else:
            return default
    except (TypeError, ValueError):
        return default
    if limits is not None:
        low, high = limits
        if (low is not None and number < low) or (high is not None and number > high):
            return default
    return number


def _as_bool(value, default: bool) -> bool:
    """灵梦：开关就写“开/关”。写成“也许”的，一律按原来的样子算。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, float) and value in (0.0, 1.0):
        return bool(int(value))
    if isinstance(value, str):
        word = value.strip().lower()
        if word in _TRUE_WORDS:
            return True
        if word in _FALSE_WORDS:
            return False
    return default


def _as_str(value, default: str) -> str:
    return value if isinstance(value, str) else default


def _as_region(value):
    """紫：结界边缘的坐标，四项缺一不可；凑不齐就当作没有框过。"""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        x, y, w, h = (int(item) for item in value)
    except (TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    return [x, y, w, h]


def _as_dict(value, default: dict) -> dict:
    return dict(value) if isinstance(value, dict) else dict(default)


def _sanitize_value(key: str, raw):
    """按键的定式把值收敛回合法形态；读不懂就给默认值。"""
    default = DEFAULTS[key]
    if key == "region":
        return _as_region(raw)
    if key == "toast_seen":
        return _as_dict(raw, default)
    if key in _FLOAT_KEYS:
        return _as_float(raw, float(default))
    if key in _INT_KEYS:
        return _as_int(raw, int(default), _INT_KEYS[key])
    if key in _BOOL_KEYS:
        return _as_bool(raw, bool(default))
    if key in _STR_KEYS:
        return _as_str(raw, str(default))
    return raw


def _boot_log(message: str) -> None:
    """文文：把这次翻车记在号外边角，下次取材好翻旧账。"""
    try:
        log_dir = os.path.dirname(CONFIG_PATH) or config_dir()
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "boot.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " " + str(message)[:800] + "\n")
    except Exception:
        pass


def _backup_broken_config() -> bool:
    """紫：把糊掉的契约卷进境界的缝隙里，给日后留个原样。"""
    bad = CONFIG_PATH + ".bad"
    try:
        shutil.copy2(CONFIG_PATH, bad)
        return True
    except Exception:
        return False


def load() -> dict:
    cfg = dict(DEFAULTS)
    data = None
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = None
    except OSError as exc:
        _boot_log(
            f"紫：config.json 卡在境界的缝隙里读不出来（{str(exc)[:200]}）；"
            "这一回先照书上的旧例来。")
    except Exception:
        if _backup_broken_config():
            _boot_log(
                "紫：config.json 的墨迹糊成一团，我把它卷进境界的缝隙"
                "（config.json.bad）；这一回先照书上的旧例来。")
        else:
            _boot_log(
                "紫：config.json 糊得连缝隙都塞不进去；这一回先照书上的旧例来。")
    if data is not None and not isinstance(data, dict):
        if _backup_broken_config():
            _boot_log(
                "紫：这卷「契约」摊开不是一册名录（不是 JSON 对象），"
                "我把它收进 config.json.bad；先照旧例来。")
        else:
            _boot_log("紫：这卷「契约」摊开不是一册名录，又塞不进缝隙；先照旧例来。")
        data = None
    if isinstance(data, dict):
        repaired: list[str] = []
        for key in DEFAULTS:
            if key not in data:
                continue
            raw = data[key]
            fixed = _sanitize_value(key, raw)
            cfg[key] = fixed
            if fixed != raw:
                repaired.append(key)
        if repaired:
            shown = "、".join(repaired[:8]) + ("等" if len(repaired) > 8 else "")
            _boot_log(
                f"帕秋莉：契约上有几行墨迹读不懂（{shown}），"
                "我照书上的定式重抄了一遍。")
    cfg["api_key"] = _unprotect(cfg.get("api_key_enc", ""))
    cfg["vision_api_key"] = _unprotect(cfg.get("vision_api_key_enc", ""))
    return cfg


def save(cfg: dict) -> bool:
    """保存配置；返回是否真的写盘成功，供设置中心给出可见反馈。

    旧调用方可以继续忽略返回值，行为不变；但设置中心不再把「写失败」
    伪装成「已保存」。
    """
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
        return True
    except Exception:
        return False

