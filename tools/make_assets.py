"""生成东方 Project 风格素材：启动画面、顶部横幅、图标。

背景用程序化绘制（夜空/月亮/神社鸟居/弹幕/樱花），
角色立绘使用 assets/char 下从 THBWiki 下载的官方立绘。
"""
from __future__ import annotations

import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(ROOT, "assets")
CHAR = os.path.join(ASSETS, "char")
os.makedirs(ASSETS, exist_ok=True)

FONT_TITLE = r"C:\Windows\Fonts\STXINGKA.TTF"   # 华文行楷
FONT_JP = r"C:\Windows\Fonts\YuGothB.ttc"
FONT_UI = r"C:\Windows\Fonts\msyh.ttc"

NIGHT_TOP = (10, 8, 22)
NIGHT_BOTTOM = (28, 18, 48)
MOON = (246, 238, 210)
TORII = (196, 58, 70)
TORII_DARK = (140, 34, 44)
PETAL_COLORS = [(255, 190, 212), (255, 160, 192), (255, 214, 228)]


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    for p in (path, FONT_UI):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def gradient(w: int, h: int, top, bottom) -> Image.Image:
    col = Image.new("RGB", (1, h))
    px = col.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return col.resize((w, h), Image.BILINEAR)


def draw_stars(d: ImageDraw.ImageDraw, w: int, h: int, n: int, rng: random.Random) -> None:
    for _ in range(n):
        x, y = rng.uniform(0, w), rng.uniform(0, h * 0.8)
        a = rng.randint(70, 210)
        r = rng.choice([1, 1, 1, 2])
        d.ellipse([x, y, x + r, y + r], fill=(230, 232, 255, a))


def draw_moon(base: Image.Image, cx: float, cy: float, r: float) -> None:
    glow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for k, alpha in ((3.2, 16), (2.2, 28), (1.5, 50)):
        gd.ellipse([cx - r * k, cy - r * k, cx + r * k, cy + r * k], fill=(255, 246, 214, alpha))
    base.alpha_composite(glow.filter(ImageFilter.GaussianBlur(r * 0.35)))
    d = ImageDraw.Draw(base)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=MOON + (255,))
    for dx, dy, rr in ((-0.28, -0.18, 0.20), (0.22, 0.12, 0.14), (-0.05, 0.32, 0.11)):
        d.ellipse([cx + dx * r - rr * r, cy + dy * r - rr * r,
                   cx + dx * r + rr * r, cy + dy * r + rr * r], fill=(236, 226, 196, 70))


def draw_torii(d: ImageDraw.ImageDraw, cx: float, base_y: float, h: float,
               color=TORII, dark=TORII_DARK) -> None:
    w = h * 0.92
    pw = h * 0.055
    top_y = base_y - h
    half = w / 2

    for sign in (-1, 1):
        x = cx + sign * half * 0.72
        d.polygon([(x - pw * 0.9, base_y), (x - pw * 0.62, top_y + h * 0.06),
                   (x + pw * 0.62, top_y + h * 0.06), (x + pw * 0.9, base_y)], fill=color)
        d.polygon([(x - pw * 0.9, base_y), (x - pw * 0.9, base_y - h * 0.06),
                   (x + pw * 0.9, base_y - h * 0.06), (x + pw * 0.9, base_y)], fill=dark)

    beam_top, beam_bot = top_y, top_y + h * 0.07
    pts_top, pts_bot = [], []
    n = 24
    for i in range(n + 1):
        t = i / n
        x = cx - half + 2 * half * t
        curve = -math.sin(math.pi * t) * h * 0.07
        pts_top.append((x, beam_top + curve))
        pts_bot.append((x, beam_bot + curve))
    d.polygon(pts_top + list(reversed(pts_bot)), fill=color)
    d.polygon(pts_bot + [(p[0], p[1] + h * 0.02) for p in reversed(pts_bot)], fill=dark)

    nuki_y = top_y + h * 0.25
    d.rectangle([cx - half * 0.84, nuki_y, cx + half * 0.84, nuki_y + h * 0.05], fill=color)
    d.rectangle([cx - half * 0.84, nuki_y + h * 0.036, cx + half * 0.84, nuki_y + h * 0.05], fill=dark)
    d.rectangle([cx - h * 0.028, top_y + h * 0.07, cx + h * 0.028, nuki_y], fill=color)

    rope_y = top_y + h * 0.185
    d.line([(cx - half * 0.8, rope_y), (cx + half * 0.8, rope_y)], fill=(228, 208, 150, 255),
           width=max(2, int(h * 0.016)))
    for i in range(5):
        x = cx - half * 0.7 + half * 1.4 * i / 4
        d.line([(x, rope_y), (x, rope_y + h * 0.045)], fill=(228, 208, 150, 255),
               width=max(1, int(h * 0.007)))


def draw_hills(d: ImageDraw.ImageDraw, w: int, h: int, color=(14, 11, 26, 255)) -> None:
    pts = [(0, h)]
    x = 0
    while x <= w:
        y = h * 0.87 - 26 * math.sin(x / w * math.pi * 2.2 + 1.1) - 12 * math.sin(x / w * 21)
        pts.append((x, y))
        x += w / 40
    pts.append((w, h))
    d.polygon(pts, fill=color)


def draw_petals(base: Image.Image, n: int, rng: random.Random, area=None) -> None:
    w, h = base.size
    x0, y0, x1, y1 = area or (0, 0, w, h)
    for _ in range(n):
        x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
        size = rng.randint(4, 11)
        color = rng.choice(PETAL_COLORS)
        sprite = Image.new("RGBA", (size * 4, size * 4), (0, 0, 0, 0))
        ImageDraw.Draw(sprite).ellipse([size, size * 1.3, size * 3, size * 2.7], fill=color + (235,))
        sprite = sprite.rotate(rng.uniform(0, 360), resample=Image.BICUBIC)
        base.alpha_composite(sprite, (int(x), int(y)))


def draw_bullets(base: Image.Image, n: int, rng: random.Random,
                 center: tuple[float, float] | None = None) -> None:
    w, h = base.size
    cx, cy = center or (w * 0.5, h * 0.5)
    palette = [(255, 96, 120), (110, 168, 255), (196, 140, 255), (255, 209, 102), (126, 240, 192)]
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i in range(n):
        if center is not None:
            ring = 1 + (i % 3)
            ang = (i / n) * math.tau * (1 + ring * 0.35) + ring * 0.4
            dist = (0.16 + 0.12 * ring) * min(w, h) * 0.55
            x, y = cx + math.cos(ang) * dist, cy + math.sin(ang) * dist
        else:
            x, y = rng.uniform(0, w), rng.uniform(0, h)
        col = rng.choice(palette)
        r = rng.randint(2, 5)
        d.ellipse([x - r * 2.1, y - r * 2.1, x + r * 2.1, y + r * 2.1], fill=col + (46,))
        d.ellipse([x - r, y - r, x + r, y + r], fill=col + (235,))
        d.ellipse([x - r * 0.42, y - r * 0.42, x + r * 0.42, y + r * 0.42], fill=(255, 255, 255, 210))
    base.alpha_composite(layer.filter(ImageFilter.GaussianBlur(3)))
    base.alpha_composite(layer)


def vignette(img: Image.Image, strength: float = 1.0) -> Image.Image:
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([-w * 0.35, -h * 0.55, w * 1.35, h * 1.55], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(min(w, h) * 0.18))
    dark = Image.new("RGBA", (w, h), (0, 0, 0, int(150 * strength)))
    dark.putalpha(Image.eval(mask, lambda v: int((255 - v) * 0.72 * strength)))
    img.alpha_composite(dark)
    return img


def paste_character(base: Image.Image, key: str, height: int, x: int | None, bottom: int,
                    flip: bool = False) -> None:
    """把角色立绘贴到画面里，带柔和投影。x=None 表示靠右对齐。"""
    path = os.path.join(CHAR, f"{key}.png")
    if not os.path.exists(path):
        return
    im = Image.open(path).convert("RGBA")
    scale = height / im.height
    im = im.resize((max(1, int(im.width * scale)), height), Image.LANCZOS)
    if flip:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    if x is None:
        x = base.width - im.width - 12
    pos = (x, bottom - height)

    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    alpha = im.split()[-1]
    sh = Image.new("RGBA", im.size, (0, 0, 0, 190))
    sh.putalpha(alpha)
    shadow.paste(sh, (pos[0] + 10, pos[1] + 8), sh)
    base.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(9)))
    base.alpha_composite(im, pos)


def make_splash(w: int = 1000, h: int = 640) -> Image.Image:
    rng = random.Random(7)
    base = gradient(w, h, NIGHT_TOP, (22, 13, 40)).convert("RGBA")
    d = ImageDraw.Draw(base)
    draw_stars(d, w, h, 240, rng)
    draw_moon(base, w * 0.80, h * 0.20, h * 0.115)
    draw_torii(d, w * 0.50, h * 0.88, h * 0.46)
    draw_bullets(base, 44, rng, center=(w * 0.5, h * 0.36))

    paste_character(base, "reimu", int(h * 0.50), int(w * 0.02), int(h * 0.95))
    paste_character(base, "marisa", int(h * 0.52), None, int(h * 0.95))

    d = ImageDraw.Draw(base)
    draw_hills(d, w, h)
    draw_petals(base, 46, rng)

    f_title = font(FONT_TITLE, 76)
    f_sub = font(FONT_JP, 25)
    f_small = font(FONT_UI, 17)
    f_tiny = font(FONT_UI, 14)
    dd = ImageDraw.Draw(base)

    title = "符卡作业簿"
    tw = dd.textlength(title, font=f_title)
    dd.text(((w - tw) / 2, 46), title, font=f_title, fill=(255, 244, 240, 255),
            stroke_width=3, stroke_fill=(120, 26, 38, 235))

    sub = "～ 抽符 · 退治 · 収卡 ～"
    sw = dd.textlength(sub, font=f_sub)
    dd.text(((w - sw) / 2, 136), sub, font=f_sub, fill=(232, 196, 106, 245))

    line = "博麗神社 · 夜間補習所"
    lw = dd.textlength(line, font=f_small)
    dd.text(((w - lw) / 2, h - 62), line, font=f_small, fill=(214, 205, 235, 210))

    tip = "版权归属 Shinichi & Fastrof 所有"
    tp = dd.textlength(tip, font=f_tiny)
    dd.text(((w - tp) / 2, h - 34), tip, font=f_tiny, fill=(150, 142, 175, 215))

    return vignette(base, 0.85)


def make_banner(w: int = 1600, h: int = 100) -> Image.Image:
    rng = random.Random(20241118)
    base = gradient(w, h, NIGHT_TOP, NIGHT_BOTTOM).convert("RGBA")
    d = ImageDraw.Draw(base)
    draw_stars(d, w, h, 150, rng)
    draw_moon(base, w * 0.90, h * 0.42, h * 0.30)
    draw_torii(d, w * 0.74, h * 1.05, h * 0.88)
    draw_bullets(base, 30, rng)
    paste_character(base, "reimu", int(h * 1.02), int(w * 0.012), int(h * 1.02))
    d = ImageDraw.Draw(base)
    draw_hills(d, w, h)
    draw_petals(base, 24, rng, (w * 0.30, 0, w, h))

    shade = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for x in range(int(w * 0.10), int(w * 0.56)):
        a = int(130 * (1 - (x - w * 0.10) / (w * 0.46)))
        sd.line([(x, 0), (x, h)], fill=(8, 6, 16, a))
    base.alpha_composite(shade)
    return vignette(base, 0.6)


def make_icon(size: int = 256) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = size * 0.46
    cx = cy = size / 2
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(28, 22, 44, 255),
              outline=(232, 196, 106, 255), width=max(2, size // 32))
    rr = r * 0.86
    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(214, 60, 74, 255))
    d.pieslice([cx - rr, cy - rr, cx + rr, cy + rr], start=90, end=270, fill=(248, 244, 238, 255))
    d.ellipse([cx - rr * 0.5, cy - rr, cx + rr * 0.5, cy], fill=(214, 60, 74, 255))
    d.ellipse([cx - rr * 0.5, cy, cx + rr * 0.5, cy + rr], fill=(248, 244, 238, 255))
    d.ellipse([cx - rr * 0.16, cy - rr * 0.84, cx + rr * 0.16, cy - rr * 0.52], fill=(248, 244, 238, 255))
    d.ellipse([cx - rr * 0.16, cy + rr * 0.52, cx + rr * 0.16, cy + rr * 0.84], fill=(214, 60, 74, 255))
    return img


def main() -> None:
    make_banner().save(os.path.join(ASSETS, "banner.png"))
    make_splash().save(os.path.join(ASSETS, "splash.png"))
    icon = make_icon()
    icon.save(os.path.join(ASSETS, "icon.ico"),
              sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icon.save(os.path.join(ASSETS, "icon.png"))
    print("assets ->", ASSETS)
    for f in ("banner.png", "splash.png", "icon.ico"):
        p = os.path.join(ASSETS, f)
        print(f"  {f}: {os.path.getsize(p) // 1024} KB")


if __name__ == "__main__":
    main()




