"""把 Pictures/ 里 AI 生成的图处理成程序素材。

- 启动图.jpg      -> assets/splash.png (1280x720)
- 顶部横幅.jpg    -> assets/banner.png (1920x320，取中间横带)
- 8 张角色图      -> assets/char/fan/avatar_<key>.png (192x192 圆形)
- 程序图标.png    -> assets/icon.png / assets/icon.ico
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "Pictures")
ASSETS = os.path.join(ROOT, "assets")
FAN = os.path.join(ASSETS, "char", "fan")
os.makedirs(FAN, exist_ok=True)

AVATARS = {
    "reimu": "灵梦.jpg",
    "marisa": "魔理沙.jpg",
    "sakuya": "咲夜.jpg",
    "keine": "慧音.jpg",
    "patchouli": "帕秋莉.jpg",
    "remilia": "蕾米莉亚.jpg",
    "flandre": "芙兰.jpg",
    "yukari": "紫.jpg",
}


def circular(path: str, size: int = 192) -> Image.Image:
    im = Image.open(path).convert("RGB")
    side = min(im.width, im.height)
    left = (im.width - side) // 2
    top = (im.height - side) // 2
    im = im.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out.paste(im, (0, 0), mask)
    return out


def main() -> None:
    # 启动图
    splash = Image.open(os.path.join(SRC, "启动图.jpg")).convert("RGB")
    splash.resize((1280, 720), Image.LANCZOS).save(os.path.join(ASSETS, "splash.png"))
    print("splash 1280x720")

    # 横幅：取中间 6:1 横带
    banner = Image.open(os.path.join(SRC, "顶部横幅.jpg")).convert("RGB")
    band_h = banner.width // 6
    top = max(0, (banner.height - band_h) // 2)
    band = banner.crop((0, top, banner.width, top + band_h)).resize((1920, 320), Image.LANCZOS)
    band.save(os.path.join(ASSETS, "banner.png"))
    print("banner 1920x320  (band y=", top, ")")

    # 头像
    for key, name in AVATARS.items():
        p = os.path.join(SRC, name)
        if not os.path.exists(p):
            print("missing", name)
            continue
        circular(p, 192).save(os.path.join(FAN, f"avatar_{key}.png"))
        print("avatar", key, "192x192")

    # 图标
    icon = Image.open(os.path.join(SRC, "程序图标.png")).convert("RGBA")
    side = min(icon.width, icon.height)
    left = (icon.width - side) // 2
    top = (icon.height - side) // 2
    icon = icon.crop((left, top, left + side, top + side)).resize((1024, 1024), Image.LANCZOS)
    icon.save(os.path.join(ASSETS, "icon.png"))
    icon.save(os.path.join(ASSETS, "icon.ico"),
              sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icon 1024 + ico")


if __name__ == "__main__":
    main()
