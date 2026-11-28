"""一机一码授权：本机灵符（机器码）+ 许可咒文（Ed25519 签名，程序里只放公钥）。

- 许可咒文由作者用私钥签发（modules/license_sign.py，主程序不导入）；
  程序只做验签，源码公开也伪造不出许可咒文。
- 试炼（试用期）记录的签名密钥是**每台机器现生成**的 32 字节 seed，经 DPAPI 保护后
  存在 %APPDATA%\\SpellCardHomework\\trial_seed。旧版本把密钥异或着写死在源码里，
  等于把印泥摆在大门口——现在源码里只剩一段"一次性迁移"用的旧密钥，认过一次就
  换新锁；换完之后旧密钥不再参与签发。
- 试炼记录读不出来（截断 / 损坏 / 权限）一律按"账本被撕"处理，只有各副本都确实
  不存在、也找不到开过试炼的痕迹，才算全新机器。
- 离线试炼终究挡不住以当前用户身份运行的逆向（本机 seed 同一个用户总能解开），
  这里只是把门槛从"翻源码抄常量"抬到"读 seed 并解开 DPAPI"。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import sys
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


# ------------------------------------------------------------------ 机器指纹
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
    """校验许可咒文，返回 (是否有效, 说明, 到期时间戳)。"""
    machine16 = _machine16(machine)
    raw = re.sub(r"\s+", "", code or "").upper()
    parts = raw.split("-")
    if len(parts) != 6:
        return False, "许可咒文的格式不对（要 6 段，用 - 隔开）", 0
    m = "".join(parts[:4])
    try:
        expiry = int(parts[4], 16)
    except ValueError:
        return False, "许可咒文里的有效期写坏了", 0
    sig_b32 = "".join(parts[5:])
    try:
        sig = base64.b32decode(sig_b32 + "=" * ((8 - len(sig_b32) % 8) % 8))
    except Exception:
        return False, "许可咒文校验失败（八成是抄漏了字）", 0
    if m != machine16:
        return False, "这张许可咒文不是本机的（本机灵符对不上）", 0
    if not ed25519.checkvalid(sig, _payload(m, expiry), bytes.fromhex(PUBLIC_KEY_HEX)):
        return False, "许可咒文校验失败（八成是抄漏了字）", 0
    if expiry and expiry < int(time.time()):
        return False, "许可咒文已经过期", 0
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


# ------------------------------------------------------------------ 试炼（试用期）
TRIAL_DAYS = 3
CLOCK_TOLERANCE = 3600  # 允许 1 小时的时钟误差

_TRIAL_SEED_FILENAME = "trial_seed"

# 旧版 HMAC 密钥：**仅为一次性迁移保留**——不要用它签任何新记录。
# 它写在发行源码里，等于公开，只用来认出"上一版留下的合法账本"；
# 认出之后立刻用新 seed 重签，seed 一旦落盘，这段旧密钥就不再参与验签。
_LEGACY_MASK = bytes([215, 160, 159, 242, 208, 45, 125, 89, 152, 104, 209, 203,
                      166, 153, 130, 114, 104, 8, 152, 9, 37, 131, 82, 9, 248,
                      225, 63, 95, 170, 13, 54, 187])
_LEGACY_SECRET_BLOB = "ECbpk8PRws5pFyeUmxZrdPmgPv3kfPQPDX0CX41qesw="

# 试炼 seed 本身也说明"这台机器开过试炼"：清了 trial.json 却把 seed 留下的，
# 不再发放新试炼。想恢复"删记录就当新机器"的旧行为，把这个开关改成 False。
TREAT_SEED_AS_PRIOR_USE = True


def _legacy_secret() -> bytes:
    """还原旧版密钥（只为迁移，别拿它签新账本）。"""
    raw = base64.b64decode(_LEGACY_SECRET_BLOB)
    return bytes(a ^ b for a, b in zip(raw, _LEGACY_MASK))


def _test_config_enabled() -> bool:
    """源码运行 + 显式 --test-config 才承认 SHINICHI_CONFIG_DIR。

    发行版（PyInstaller frozen）一律忽略这个环境变量：否则谁都能建一个空临时目录，
    把试炼账本当成"全新机器"重开。测试脚本请这样跑：
        python tools\\test_expired.py --test-config
    """
    if getattr(sys, "frozen", False):
        return False
    try:
        argv = list(sys.argv or [])
    except Exception:
        return False
    for arg in argv:
        try:
            if str(arg) == "--test-config":
                return True
        except Exception:
            continue
    return False


def _trial_state_dir() -> str:
    """试炼记录所在目录：测试模式用 SHINICHI_CONFIG_DIR，平时用 %APPDATA%。"""
    if _test_config_enabled():
        return settings.config_dir()
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, settings.APP_DIRNAME)


def _trial_seed_path() -> str:
    return os.path.join(_trial_state_dir(), _TRIAL_SEED_FILENAME)


def _load_seed() -> tuple[bytes | None, bool]:
    """返回 (seed, 文件是否存在)。存在但解不开 → (None, True)，按记录损坏处理。"""
    path = _trial_seed_path()
    try:
        if not os.path.exists(path):
            return None, False
    except OSError:
        return None, False
    try:
        with open(path, encoding="ascii") as f:
            raw = f.read().strip()
    except Exception:
        return None, True
    try:
        if raw.startswith("dpapi:"):
            hexed = settings._unprotect(raw)
        elif raw.startswith("raw:"):
            hexed = raw[4:]
        else:
            hexed = raw
        seed = bytes.fromhex(hexed)
    except Exception:
        return None, True
    if len(seed) != 32:
        return None, True
    return seed, True


def _new_seed() -> bytes:
    return os.urandom(32)


def _store_seed(seed: bytes) -> bool:
    """DPAPI 保护后落盘；DPAPI 不可用时退成 raw:十六进制（仍然每机随机）。"""
    path = _trial_seed_path()
    hexed = seed.hex()
    protected = settings._protect(hexed)
    payload = protected if protected.startswith("dpapi:") else "raw:" + hexed
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="ascii") as f:
            f.write(payload)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def _ensure_seed() -> bytes | None:
    seed, present = _load_seed()
    if present:
        return seed  # 文件坏掉时是 None，调用方按"验不了"处理，不重新生成
    seed = _new_seed()
    return seed if _store_seed(seed) else None


def _trial_sig_with(seed: bytes, first: int, last: int, runs: int) -> str:
    msg = f"trial|{int(first)}|{int(last)}|{int(runs)}".encode()
    return base64.b32encode(hmac.new(seed, msg, hashlib.sha256).digest()).decode("ascii")[:16]


def _trial_record(first: int, last: int, runs: int, seed: bytes) -> dict:
    return {"first": int(first), "last": int(last), "runs": int(runs),
            "sig": _trial_sig_with(seed, first, last, runs)}


def _trial_sig(first: int, last: int, runs: int) -> str:
    """旧接口：用**已经存在**的每机 seed 签一条记录（tools/ 里的自检脚本还在用）。

    没有 seed 就返回空串，绝不顺手生成：以前的版本会在这里写文件，工具脚本
    在别处调用它时会把 seed 造到真实 %APPDATA% 里，反而把迁移窗口关掉。
    """
    seed, present = _load_seed()
    if not present or seed is None:
        return ""
    return _trial_sig_with(seed, first, last, runs)


def _record_valid(data: object, seed: bytes | None) -> bool:
    if not isinstance(data, dict) or not seed:
        return False
    try:
        expect = _trial_sig_with(seed, int(data["first"]), int(data["last"]), int(data["runs"]))
    except Exception:
        return False
    return data.get("sig") == expect


def _legacy_record_valid(data: object) -> bool:
    """旧密钥签名（公开）——只在"这台机器还没生成 seed"的迁移窗口里认。"""
    if not isinstance(data, dict):
        return False
    try:
        expect = _trial_sig_with(_legacy_secret(), int(data["first"]),
                                 int(data["last"]), int(data["runs"]))
    except Exception:
        return False
    return data.get("sig") == expect


def _trial_locations() -> list[tuple[str, str]]:
    # 测试环境（源码 + --test-config）只用一个位置，避免污染真实系统
    if _test_config_enabled():
        return [("file", os.path.join(settings.config_dir(), "trial.json"))]
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return [
        ("file", os.path.join(appdata, settings.APP_DIRNAME, "trial.json")),
        ("local", os.path.join(local, settings.APP_DIRNAME, ".spellcard_trial")),
    ]


def _read_json_slot(path: str) -> tuple[dict | None, bool]:
    """返回 (记录, 是否存在)。存在但读不出来时记录为 None —— 上层按 tampered 处理。"""
    try:
        exists = os.path.exists(path)
    except OSError:
        exists = False
    if not exists:
        return None, False
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None, True
    return (data if isinstance(data, dict) else None), True


def _read_registry_slot() -> tuple[dict | None, bool]:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Shinichi\SpellCardHomework") as k:
            raw = winreg.QueryValueEx(k, "trial")[0]
    except FileNotFoundError:
        return None, False
    except PermissionError:
        # 注册表被锁住：宁可当作"有但读不出"，也不让试炼白重开
        return None, True
    except Exception:
        return None, False
    try:
        data = json.loads(base64.b64decode(raw).decode("utf-8"))
    except Exception:
        return None, True
    return (data if isinstance(data, dict) else None), True


def _write_json(path: str, data: dict) -> bool:
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def _write_registry(data: dict) -> bool:
    try:
        import winreg

        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                               r"Software\Shinichi\SpellCardHomework")
        raw = base64.b64encode(json.dumps(data).encode("utf-8")).decode("ascii")
        winreg.SetValueEx(key, "trial", 0, winreg.REG_SZ, raw)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def _write_trial_all(record: dict) -> bool:
    """写全部副本，返回是否**每一处**都写成功。"""
    ok = True
    for _kind, path in _trial_locations():
        ok = _write_json(path, record) and ok
    if not _test_config_enabled():
        ok = _write_registry(record) and ok
    return ok


def _write_trial(first: int, last: int, runs: int) -> bool:
    seed = _ensure_seed()
    if seed is None:
        return False
    return _write_trial_all(_trial_record(first, last, runs, seed))


def _migrate_legacy(first: int, last: int, runs: int) -> bool:
    """把旧密钥签的试炼账本一次性改成每机 seed 的签名（S-3 迁移）。

    要么"全部写成新签名 + seed 落盘"，要么退回旧签名保持"无 seed"状态下次再试；
    不留半新半旧的账本，免得把还在试用期的老用户直接打成 tampered。
    """
    seed = _new_seed()
    if not _write_trial_all(_trial_record(first, last, runs, seed)):
        _write_trial_all(_trial_record(first, last, runs, _legacy_secret()))
        return False
    if not _store_seed(seed):
        _write_trial_all(_trial_record(first, last, runs, _legacy_secret()))
        return False
    return True


def _prior_use_config_paths() -> list[str]:
    """记着"用过本软件"的 config.json：测试目录 +（非测试时）真实 APPDATA。

    SHINICHI_CONFIG_DIR 已经不影响试炼判定了，这里两边都看，免得一个空目录
    就把神社的香火账藏起来。
    """
    paths = [os.path.join(settings.config_dir(), "config.json")]
    if not _test_config_enabled():
        alt = os.path.join(_trial_state_dir(), "config.json")
        if alt not in paths:
            paths.append(alt)
    return paths


def _used_before() -> bool:
    """之前用过这个程序吗（配置里有通行密钥，或者试炼 seed 已经在了）。"""
    for path in _prior_use_config_paths():
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            continue
        if isinstance(raw, dict) and (raw.get("api_key_enc") or raw.get("vision_api_key_enc")):
            return True
    if TREAT_SEED_AS_PRIOR_USE:
        try:
            if os.path.exists(_trial_seed_path()):
                return True
        except OSError:
            pass
    return False


def trial_status(update: bool = True) -> tuple[str, int, str]:
    """返回 (状态, 剩余天数, 文案)；状态: trial / expired / tampered / fresh。"""
    seed, seed_present = _load_seed()

    slots: list[tuple[dict | None, bool]] = []
    for _kind, path in _trial_locations():
        slots.append(_read_json_slot(path))
    if not _test_config_enabled():
        slots.append(_read_registry_slot())

    valid: list[dict] = []
    legacy: list[dict] = []
    present = False
    invalid = False
    for data, exists in slots:
        if exists:
            present = True
        if data is None:
            if exists:
                invalid = True  # 账本在，却读不出字 —— 撕了就是撕了
            continue
        if _record_valid(data, seed):
            valid.append(data)
        elif not seed_present and _legacy_record_valid(data):
            # 迁移窗口：还没生成 seed 的机器，认一次上一版留下的合法账本
            legacy.append(data)
        else:
            invalid = True

    torn = "试炼的账本被撕破了一角，字迹读不出来，境界不认这个"
    if invalid:
        return "tampered", 0, torn

    copies = valid + legacy
    now = int(time.time())

    if not copies:
        if present:
            return "tampered", 0, torn
        # 试炼记录被清空，但神社的香火账上还有痕迹：说明之前用过，不能再领试炼
        if _used_before():
            return "expired", 0, "试炼的记录被抹干净了，可神社的香火账上还留着你的名字"
        # 没有试炼记录、也没有用过的痕迹（新机器）→ 当作全新用户
        return "fresh", 0, "尚未开启试炼"

    first = min(int(c["first"]) for c in copies)
    last = max(int(c["last"]) for c in copies)
    runs = max(int(c.get("runs", 0)) for c in copies) + 1

    if now < last - CLOCK_TOLERANCE:
        return "tampered", 0, "系统时间被往回调过，试炼作废，需要许可咒文"

    elapsed = now - first
    if elapsed > TRIAL_DAYS * 86400:
        return "expired", 0, "三天的试炼已经结束，需要许可咒文"

    if legacy:
        # 旧签名验过了：立刻换新 seed 重签写回，之后不再用旧密钥签发
        _migrate_legacy(first, now, runs)
    elif update:
        _write_trial(first, now, runs)
    days_left = max(0, TRIAL_DAYS - int(elapsed // 86400))
    if days_left <= 0 and elapsed < TRIAL_DAYS * 86400:
        hours = max(1, int((TRIAL_DAYS * 86400 - elapsed) // 3600))
        return "trial", 0, f"试炼最后 {hours} 小时"
    return "trial", days_left, f"试炼还剩 {days_left} 天"


def check_access(update: bool = True) -> tuple[str, str, int]:
    """供界面调用：返回 (状态, 文案, 剩余天数)。状态: licensed / trial / expired / tampered。"""
    ok, msg = status()
    if ok:
        return "licensed", msg, 0
    state, days, msg = trial_status(update=update)
    return state, msg, days


def start_trial() -> tuple[str, int, str]:
    """用户点了「先试用三天」后再真正开始计时。"""
    now = int(time.time())
    _write_trial(now, now, 1)
    return "trial", TRIAL_DAYS, f"试炼开始了，结界还能撑 {TRIAL_DAYS} 天"
