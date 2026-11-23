"""给 AI 启动图加上软件名、版本号、版权信息。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "Pictures", "启动图.jpg")
DST = os.path.join(ROOT, "assets", "splash.png")

W, H = 1280, 720
TITLE = "符卡作业簿"
SUB = "～ 幻想郷 · 宿題退治 ～"
from modules import settings as _settings
VER = f"v{_settings.APP_VERSION}"
COPY = "© 2025 Shinichi · Fastrof · 会哈气の祥  ·  MIT License  ·  东方 Project 二次创作"

FONT_TITLE = r"C:\Windows\Fonts\STXINGKA.TTF"
FONT_UI = r"C:\Windows\Fonts\msyh.ttc"
FONT_UI_B = r"C:\Windows\Fonts\msyhbd.ttc"


def main() -> None:
    im = Image.open(SRC).convert("RGB").resize((W, H), Image.LANCZOS)

    # 顶部与底部压暗，保证文字可读
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for y in range(180):
        alpha = int(150 * (1 - y / 180))
        od.line([(0, y), (W, y)], fill=(12, 10, 24, alpha))
    for y in range(H - 120, H):
        alpha = int(170 * (1 - (H - y) / 120))
        od.line([(0, y), (W, y)], fill=(12, 10, 24, alpha))
    im = Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")

    d = ImageDraw.Draw(im)

    # 中间留白处放标题
    f_title = ImageFont.truetype(FONT_TITLE, 74)
    f_sub = ImageFont.truetype(FONT_UI, 22)
    f_ver = ImageFont.truetype(FONT_UI_B, 18)
    f_copy = ImageFont.truetype(FONT_UI, 15)

    tw = d.textlength(TITLE, font=f_title)
    tx, ty = (W - tw) / 2, 28
    # 先画描边和阴影，最后盖上主色
    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, 2)):
        d.text((tx + dx, ty + dy), TITLE, font=f_title, fill=(120, 30, 40))
    d.text((tx + 4, ty + 4), TITLE, font=f_title, fill=(15, 6, 10))
    d.text((tx, ty), TITLE, font=f_title, fill=(255, 236, 180))

    sw = d.textlength(SUB, font=f_sub)
    d.text(((W - sw) / 2, ty + 96), SUB, font=f_sub, fill=(232, 196, 106))

    # 版本 + 版权
    vw = d.textlength(VER, font=f_ver)
    d.text(((W - vw) / 2, H - 74), VER, font=f_ver, fill=(240, 235, 250))
    cw = d.textlength(COPY, font=f_copy)
    d.text(((W - cw) / 2, H - 46), COPY, font=f_copy, fill=(200, 192, 220))

    im.save(DST)
    print("splash with text ->", DST, im.size)


if __name__ == "__main__":
    main()
