"""把根目录的官网同步到 docs/。

GitHub Pages 当前从 `main` 的 `/docs` 发布，所以改完根目录的 index.html / assets
之后，跑一下这个脚本，让 docs/ 里的发布副本保持一致。

用法：
    python tools/sync_site_to_docs.py
"""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

PAGES = ("index.html", "features.html", "download.html")
ASSET_DIRS = ("css", "js", "img", "audio")


def main() -> None:
    for name in PAGES:
        src = ROOT / name
        if not src.exists():
            raise SystemExit(f"缺少 {name}")
        shutil.copy2(src, DOCS / name)

    for name in ASSET_DIRS:
        src = ROOT / "assets" / name
        if not src.exists():
            raise SystemExit(f"缺少 assets/{name}")
        shutil.copytree(src, DOCS / "assets" / name, dirs_exist_ok=True)

    print("已同步到 docs/：")
    for name in PAGES:
        print("  docs/" + name)
    for name in ASSET_DIRS:
        print(f"  docs/assets/{name}/")


if __name__ == "__main__":
    main()
