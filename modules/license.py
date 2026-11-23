"""一机一码授权：机器码 + 激活码（Ed25519 签名，程序里只放公钥）。

- 激活码由作者用私钥签发（modules/license_sign.py，主程序不导入）
- 程序只做验签，即使源码公开也无法伪造激活码
- 试用记录用 HMAC 签名，只防随手改本地文件，防不住逆向
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid

from modules import ed25519, settings

APP_NAME = "符卡作业簿"
EMAILS = [
    ("Shinichi", "1651452812@qq.com"),
    ("Fastrof", "3530209532@qq.com"),
]

# 验签公钥（私钥只在作者手里，见 license_private.key）
PUBLIC_KEY_HEX = "e34745657d86a72a2adceb97ef9a710a937a71cb960a4d446f73c4aebbfef4fd"

# 试用记录用的本地签名密钥（只防随手改文件，防止不了逆向）
_MASK = bytes([215, 160, 159, 242, 208, 45, 125, 89, 152, 104, 209, 203, 166, 153, 130, 114, 104, 8, 152, 9, 37, 131, 82, 9, 248, 225, 63, 95, 170, 13, 54, 187])
_SECRET_BLOB = "ECbpk8PRws5pFyeUmxZrdPmgPv3kfPQPDX0CX41qesw="


def _secret() -> bytes:
    raw = base64.b64decode(_SECRET_BLOB)
    return bytes(a ^ b for a, b in zip(raw, _MASK))


def _machine_raw() -> str:
    """机器指纹：系统 MachineGuid + C 盘卷序列号 + MAC（取不到的项自动跳过）。"""
    parts: list[str] = []
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k:
            parts.append(str(winreg.QueryValueEx(k, "MachineGuid")[0]))
    except Exception:
        pass
    try:
        import ctypes

        vol = ctypes.c_ulong(0)
        ctypes.windll.kernel32.GetVolumeInformationW(
            "C:\\", None, 0, ctypes.byref(vol), None, None, None, 0)
        parts.append(str(vol.value))
    except Exception:
        pass
    try:
        parts.append(str(uuid.getnode()))
    except Exception:
        pass
    if not parts:
        parts.append(os.environ.get("COMPUTERNAME", "UNKNOWN"))
    return "|".join(parts)


def machine_code() -> str:
    h = hashlib.sha256(_machine_raw().encode("utf-8")).hexdigest().upper()[:16]
    return "-".join(h[i:i + 4] for i in range(0, 16, 4))


def _machine16(machine: str | None = None) -> str:
    m = re.sub(r"[^0-9A-Fa-f]", "", machine or machine_code()).upper()[:16]
    return (m + "0" * 16)[:16]


def _payload(machine16: str, expiry: int) -> bytes:
    return f"{machine16}|{expiry:08X}".encode()


def verify_code(code: str, machine: str | None = None) -> tuple[bool, str, int]:
    """校验激活码，返回 (是否有效, 说明, 到期时间戳)。"""
    machine16 = _machine16(machine)
    raw = re.sub(r"\s+", "", code or "").upper()
    parts = raw.split("-")
    if len(parts) != 6:
        return False, "激活码格式不对（应为 6 段，用 - 分隔）", 0
    m = "".join(parts[:4])
    try:
        expiry = int(parts[4], 16)
    except ValueError:
        return False, "激活码里的有效期格式不对", 0
    sig_b32 = "".join(parts[5:])
    try:
        sig = base64.b32decode(sig_b32 + "=" * ((8 - len(sig_b32) % 8) % 8))
    except Exception:
        return False, "激活码校验失败（可能抄错了）", 0
    if m != machine16:
        return False, "这个激活码不是本机的（机器码不匹配）", 0
    if not ed25519.checkvalid(sig, _payload(m, expiry), bytes.fromhex(PUBLIC_KEY_HEX)):
        return False, "激活码校验失败（可能抄错了）", 0
    if expiry and expiry < int(time.time()):
        return False, "激活码已过期", 0
    if expiry == 0:
        return True, "已激活（永久）", 0
    days = int((expiry - time.time()) // 86400)
    return True, f"已激活（剩余 {days} 天）", expiry


def license_path() -> str:
    return os.path.join(settings.config_dir(), "license.json")


def save_license(code: str) -> None:
    path = license_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"code": (code or "").strip(), "machine": machine_code()},
                  f, ensure_ascii=False)


def load_license() -> str:
    try:
        with open(license_path(), encoding="utf-8") as f:
            return str(json.load(f).get("code") or "")
    except Exception:
        return ""


def status() -> tuple[bool, str]:
    code = load_license()
    if not code:
        return False, "未激活"
    ok, msg, _ = verify_code(code)
    return ok, msg


# ------------------------------------------------------------------ 试用
TRIAL_DAYS = 5
CLOCK_TOLERANCE = 3600  # 允许 1 小时的时钟误差


def _trial_sig(first: int, last: int, runs: int) -> str:
    msg = f"trial|{first}|{last}|{runs}".encode()
    return base64.b32encode(hmac.new(_secret(), msg, hashlib.sha256).digest()).decode("ascii")[:16]


def _trial_locations() -> list[tuple[str, str]]:
    # 测试环境（SHINICHI_CONFIG_DIR）只用一个位置，避免污染真实系统
    if os.environ.get("SHINICHI_CONFIG_DIR"):
        return [("file", os.path.join(settings.config_dir(), "trial.json"))]
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return [
        ("file", os.path.join(appdata, "SpellCardHomework", "trial.json")),
        ("local", os.path.join(local, "SpellCardHomework", ".spellcard_trial")),
    ]


def _read_json(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _read_registry() -> dict | None:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\\Shinichi\\SpellCardHomework") as k:
            raw = winreg.QueryValueEx(k, "trial")[0]
        return json.loads(base64.b64decode(raw).decode("utf-8"))
    except Exception:
        return None


def _write_registry(data: dict) -> None:
    try:
        import winreg

        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\\Shinichi\\SpellCardHomework")
        raw = base64.b64encode(json.dumps(data).encode("utf-8")).decode("ascii")
        winreg.SetValueEx(key, "trial", 0, winreg.REG_SZ, raw)
        winreg.CloseKey(key)
    except Exception:
        pass


def _write_trial(first: int, last: int, runs: int) -> None:
    data = {"first": int(first), "last": int(last), "runs": int(runs),
            "sig": _trial_sig(int(first), int(last), int(runs))}
    for _kind, path in _trial_locations():
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            pass
    if not os.environ.get("SHINICHI_CONFIG_DIR"):
        _write_registry(data)


def _trial_valid(data: dict | None) -> bool:
    if not isinstance(data, dict):
        return False
    try:
        return data.get("sig") == _trial_sig(int(data["first"]), int(data["last"]), int(data["runs"]))
    except Exception:
        return False


def _used_before() -> bool:
    """之前用过这个程序吗（配置里有 API Key 就说明用过）。"""
    try:
        path = os.path.join(settings.config_dir(), "config.json")
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return bool(raw.get("api_key_enc")) or bool(raw.get("vision_api_key_enc"))
    except Exception:
        return False


def trial_status(update: bool = True) -> tuple[str, int, str]:
    """返回 (状态, 剩余天数, 文案)；状态: trial / expired / tampered。"""
    copies: list[dict] = []
    invalid = False
    present = False
    for _kind, path in _trial_locations():
        data = _read_json(path)
        if data is not None:
            present = True
        if _trial_valid(data):
            copies.append(data)
        elif data is not None:
            invalid = True
    reg = None if os.environ.get("SHINICHI_CONFIG_DIR") else _read_registry()
    if reg is not None:
        present = True
    if _trial_valid(reg):
        copies.append(reg)
    elif reg is not None:
        invalid = True

    now = int(time.time())

    if invalid:
        return "tampered", 0, "试用记录被改动过，需要重新激活"

    if not copies:
        if present:
            return "tampered", 0, "试用记录被改动过，需要重新激活"
        # 试用记录被清空，但本机配置里已经有 API Key：说明之前用过，不能再领试用
        if _used_before():
            return "expired", 0, "试用记录已被清除，需要激活码"
        # 没有试用记录、也没有用过的痕迹（新机器）→ 当作全新用户
        return "fresh", 0, "尚未开启试用"

    first = min(int(c["first"]) for c in copies)
    last = max(int(c["last"]) for c in copies)
    runs = max(int(c.get("runs", 0)) for c in copies) + 1

    if now < last - CLOCK_TOLERANCE:
        return "tampered", 0, "系统时间被往回调过，试用作废，需要激活"

    elapsed = now - first
    if elapsed > TRIAL_DAYS * 86400:
        return "expired", 0, "五天试用已经结束，需要激活码"

    if update:
        _write_trial(first, now, runs)
    days_left = max(0, TRIAL_DAYS - int(elapsed // 86400))
    if days_left <= 0 and elapsed < TRIAL_DAYS * 86400:
        hours = max(1, int((TRIAL_DAYS * 86400 - elapsed) // 3600))
        return "trial", 0, f"试用最后 {hours} 小时"
    return "trial", days_left, f"试用还剩 {days_left} 天"


def check_access(update: bool = True) -> tuple[str, str, int]:
    """供界面调用：返回 (状态, 文案, 剩余天数)。状态: licensed / trial / expired / tampered。"""
    ok, msg = status()
    if ok:
        return "licensed", msg, 0
    state, days, msg = trial_status(update=update)
    return state, msg, days


def start_trial() -> tuple[str, int, str]:
    """用户点了「试用 5 天」后再真正开始计时。"""
    now = int(time.time())
    _write_trial(now, now, 1)
    return "trial", TRIAL_DAYS, f"试用开始，还剩 {TRIAL_DAYS} 天"
