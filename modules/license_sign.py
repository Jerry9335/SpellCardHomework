"""作者专用：用私钥签发激活码。

⚠️ 主程序不导入本模块；私钥文件（license_private.key）不进仓库、不外传。
"""
from __future__ import annotations

import base64
import os
import re
import time

from modules import ed25519

KEY_FILENAME = "license_private.key"


def key_path(path: str | None = None) -> str:
    if path:
        return path
    env = os.environ.get("SCH_LICENSE_KEY")
    if env:
        return env
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), KEY_FILENAME)


def load_seed(path: str | None = None) -> bytes:
    with open(key_path(path), encoding="ascii") as f:
        raw = f.read().strip()
    seed = bytes.fromhex(raw)
    if len(seed) != 32:
        raise ValueError("私钥格式不对（应为 64 位十六进制）")
    return seed


def public_key_hex(path: str | None = None) -> str:
    seed = load_seed(path)
    return ed25519.publickey(seed).hex()


def make_code(machine: str, days: int = 0, key_file: str | None = None) -> str:
    """生成激活码。days <= 0 表示永久。"""
    m = re.sub(r"[^0-9A-Fa-f]", "", machine or "").upper()[:16]
    m = (m + "0" * 16)[:16]
    expiry = 0 if days <= 0 else int(time.time()) + int(days) * 86400
    seed = load_seed(key_file)
    pk = ed25519.publickey(seed)
    sig = ed25519.signature(f"{m}|{expiry:08X}".encode(), seed, pk)
    sig_b32 = base64.b32encode(sig).decode("ascii").rstrip("=")
    return f"{m[:4]}-{m[4:8]}-{m[8:12]}-{m[12:16]}-{expiry:08X}-{sig_b32}"
