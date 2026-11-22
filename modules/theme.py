"""「晨午宵绘卷」主题：时段资源、配色、背景合成与解锁序列。"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageOps

THEME_CLASSIC = "classic"
THEME_NEW = "chenwuxiao"
THEME_LABEL = "晨午宵绘卷"

MAIN_FILES = {
    "day": "main_morning.png",
    "afternoon": "main_afternoon.png",
    "night": "main_night.png",
}
SPLASH_FILES = {
    "day": "splash_morning.png",
    "afternoon": "splash_afternoon.png",
    "night": "splash_night.png",
}

NEW_COLORS = {
    "bg": "#0c0912",
    "panel": "#15111d",
    "panel2": "#211a2b",
    "input": "#1d1727",
    "text": "#fffaf6",
    "muted": "#d6c8df",
    "accent": "#b33844",
    "accent_dark": "#7f2331",
    "gold": "#f1c75b",
    "ok": "#8fd3a8",
    "warn": "#e7b96a",
    "err": "#e77a86",
    "border": "#3a2d47",
}

TARGET_KEYS = (
    "Up", "Up", "Down", "Down", "Left", "Right", "Left", "Right",
    "b", "a", "Return",
)


class KeySequence:
    """顺序键检测，支持前缀重试。"""

    def __init__(self, target=TARGET_KEYS):
        self.target = tuple(target)
        self.buf: list[str] = []

    def feed(self, keysym: str) -> bool:
        key = _normalize(keysym)
        if not key:
            return False
        self.buf.append(key)
        if tuple(self.buf) == self.target:
            self.buf = []
            return True
        while self.buf and tuple(self.buf) != self.target[:len(self.buf)]:
            self.buf.pop(0)
        return False


def _normalize(keysym: str) -> str:
    k = keysym or ""
    if k in ("Up", "Down", "Left", "Right"):
        return k
    if k in ("Return", "KP_Enter"):
        return "Return"
    if k in ("b", "B"):
        return "b"
    if k in ("a", "A"):
        return "a"
    return ""


def _path(assets_dir: str, files: dict, phase: str) -> str:
    if phase not in files:
        phase = "afternoon"
    return os.path.join(assets_dir, "theme_new", files[phase])


def main_path(assets_dir: str, phase: str) -> str:
    return _path(assets_dir, MAIN_FILES, phase)


def splash_path(assets_dir: str, phase: str) -> str:
    return _path(assets_dir, SPLASH_FILES, phase)


def assets_available(assets_dir: str) -> bool:
    return all(os.path.exists(main_path(assets_dir, p)) for p in MAIN_FILES)


def _cover(path: str, size: tuple[int, int]) -> Image.Image:
    src = Image.open(path).convert("RGB")
    return ImageOps.fit(src, size, method=Image.LANCZOS, centering=(0.5, 0.48))


_MAIN_ALPHA = {"day": 0.18, "afternoon": 0.16, "night": 0.10}
_HEADER_LEFT = {"day": 0.86, "afternoon": 0.82, "night": 0.62}
_BOTTOM = {"day": 0.28, "afternoon": 0.26, "night": 0.24}


def compose_background(assets_dir: str, phase: str, size: tuple[int, int]) -> Image.Image:
    """主内容背景：cover 裁切 + 按时段压暗 + 底部渐变。"""
    w, h = max(1, size[0]), max(1, size[1])
    im = _cover(main_path(assets_dir, phase), (w, h))
    alpha = _MAIN_ALPHA.get(phase, 0.48)
    im = Image.blend(im, Image.new("RGB", (w, h), (5, 4, 10)), alpha)

    overlay = Image.new("RGBA", (w, h), (5, 4, 10, 0))
    od = ImageDraw.Draw(overlay)
    bottom = _BOTTOM.get(phase, 0.4)
    for y in range(h):
        t = y / max(1, h - 1)
        a = int(255 * bottom * (max(0.0, (t - 0.52) / 0.48) ** 1.6))
        if a:
            od.line([(0, y), (w, y)], fill=(5, 4, 10, a))
    return Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")


def compose_header(assets_dir: str, phase: str, size: tuple[int, int]) -> Image.Image:
    """顶栏图：同一场景的宽幅裁切 + 左侧标题渐变。"""
    w, h = max(1, size[0]), max(1, size[1])
    im = _cover(main_path(assets_dir, phase), (w, h))
    im = Image.blend(im, Image.new("RGB", (w, h), (5, 4, 10)),
                     _MAIN_ALPHA.get(phase, 0.48) * 0.38)

    overlay = Image.new("RGBA", (w, h), (5, 4, 10, 0))
    od = ImageDraw.Draw(overlay)
    # 不再压大面积黑色标题底；只保留最底边一条极淡的衔接
    for y in range(max(0, h - 18), h):
        a = int(55 * (y - (h - 18)) / 18)
        od.line([(0, y), (w, y)], fill=(5, 4, 10, a))
    return Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")


def compose_splash(assets_dir: str, phase: str) -> Image.Image:
    """启动画面：1280x720 + 顶部/底部渐变，标题由程序叠加。"""
    w, h = 1280, 720
    im = _cover(splash_path(assets_dir, phase), (w, h))
    overlay = Image.new("RGBA", (w, h), (5, 4, 10, 0))
    od = ImageDraw.Draw(overlay)
    top_alpha = {"day": 0.70, "afternoon": 0.58, "night": 0.36}.get(phase, 0.6)
    bot_alpha = {"day": 0.55, "afternoon": 0.46, "night": 0.32}.get(phase, 0.45)
    top_h = 230
    bot_h = 95
    for y in range(top_h):
        a = int(255 * top_alpha * (1 - y / top_h) ** 1.4)
        od.line([(0, y), (w, y)], fill=(5, 4, 10, a))
    for y in range(bot_h):
        a = int(255 * bot_alpha * (y / bot_h) ** 1.4)
        od.line([(0, h - bot_h + y), (w, h - bot_h + y)], fill=(5, 4, 10, a))
    return Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")
