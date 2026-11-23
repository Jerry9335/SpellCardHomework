"""打包后同步官网校验和。

用法（在项目根目录）：
    python tools/sync_site_hash.py installer/Output/SpellCardHomework-Setup-1.0.5.exe

它会：
1. 计算安装包 SHA256 / 大小
2. 更新 docs/download.html 里的 SHA256、复制按钮、大小
3. 写入同名 .sha256 文件

不运行它，官网就还可能继续指向旧包；最终发布前必须运行一次。
"""
from __future__ import annotations

import hashlib
import os
import re
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python tools/sync_site_hash.py <安装包路径>")
        return 2
    exe = os.path.abspath(sys.argv[1])
    if not os.path.isfile(exe):
        print(f"找不到安装包: {exe}")
        return 2
    h = hashlib.sha256()
    with open(exe, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    sha = h.hexdigest()
    size = os.path.getsize(exe)
    size_mb = f"{size / 1e6:.1f}"

    html = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "docs", "download.html")
    s = open(html, encoding="utf-8-sig").read()
    s = re.sub(r"SHA256 [a-f0-9]{64}", "SHA256 " + sha, s)
    s = re.sub(r'data-copy="[a-f0-9]{64}"', 'data-copy="' + sha + '"', s)
    s = re.sub(r"约 \d+(?:\.\d+)? MB", "约 " + size_mb + " MB", s)
    open(html, "w", encoding="utf-8-sig").write(s)

    side = exe + ".sha256"
    with open(side, "w", encoding="ascii") as f:
        f.write(sha + "  " + os.path.basename(exe))
    print(f"已同步: {os.path.basename(exe)}")
    print(f"  sha256 = {sha}")
    print(f"  size   = {size} bytes ({size_mb} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
