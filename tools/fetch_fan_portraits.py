"""导入「现代画风」角色头像（128x128 立绘集）。

来源：GitHub 发布包 igkewg/Touhou-Portraits（东方 Project 衍生同人立绘集，作者 dairi）。
流程：下载 → 只解压 portraits 目录 → 只接受图片 → Pillow 校验 → 生成圆形头像 → Defender 扫描 → 清理临时文件。
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CHAR = os.path.join(ROOT, "assets", "char")
FAN = os.path.join(CHAR, "fan")
os.makedirs(FAN, exist_ok=True)

RAR_URL = "https://github.com/igkewg/Touhou-Portraits/releases/download/v0.2/Touhou.Portrait.rar"
MAX_BYTES = 30 * 1024 * 1024

# 本地文件名 -> 压缩包里的立绘名
MAPPING = {
    "reimu": "Reimu",
    "marisa": "Marisa",
    "sakuya": "Sakuya",
    "remilia": "Remilia",
    "patchouli": "Patchy",
    "keine": "Keine",
    "yukari": "Yukari",
}


def download(url: str, dest: str) -> None:
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise RuntimeError("文件过大，已拒绝")
    with open(dest, "wb") as f:
        f.write(data)


def distro_font() -> str:
    return r"C:\Windows\Fonts\msyh.ttc"


def face_anchor(im: Image.Image):
    """用肤色最大连通区域估计「头部」的中心与大小（归一化）。

    只看肤色区域的上半部分（头/脸），避免脖子、手、胸口把中心拉下去。
    """
    n = 64
    small = im.convert("RGB").resize((n, n), Image.BILINEAR)
    px = small.load()
    mask = [[False] * n for _ in range(n)]
    for y in range(n):
        for x in range(n):
            r, g, b = px[x, y][:3]
            if (r > 95 and g > 40 and b > 20 and max(r, g, b) - min(r, g, b) > 15
                    and abs(r - g) > 15 and r > g and r > b):
                mask[y][x] = True

    seen = [[False] * n for _ in range(n)]
    best: list[tuple[int, int]] = []
    for y in range(n):
        for x in range(n):
            if not mask[y][x] or seen[y][x]:
                continue
            stack = [(x, y)]
            seen[y][x] = True
            pts = []
            while stack:
                cx, cy = stack.pop()
                pts.append((cx, cy))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < n and 0 <= ny < n and mask[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            if len(pts) > len(best):
                best = pts
    if len(best) < 24:
        return None

    ys = sorted(p[1] for p in best)
    cut = ys[int(len(ys) * 0.55)]
    head = [(x, y) for x, y in best if y <= cut]
    if len(head) < 12:
        head = best
    xs2 = [x for x, _ in head]
    ys2 = [y for _, y in head]
    cx = (min(xs2) + max(xs2) + 1) / 2 / n
    cy = (min(ys2) + max(ys2) + 1) / 2 / n
    fw = (max(xs2) - min(xs2) + 1) / n
    fh = (max(ys2) - min(ys2) + 1) / n
    return cx, cy, fw, fh


# 手工标定的脸部中心（归一化）与裁剪边长（相对短边），按角色微调
FACE_CROPS = {
    "reimu":     (0.47, 0.42, 0.60),
    "marisa":    (0.52, 0.66, 0.58),
    "sakuya":    (0.42, 0.47, 0.60),
    "remilia":   (0.50, 0.65, 0.58),
    "patchouli": (0.58, 0.50, 0.58),
    "keine":     (0.50, 0.55, 0.52),
    "yukari":    (0.80, 0.66, 0.55),
    "flandre":   (0.50, 0.40, 0.62),
}


def make_avatar(im: Image.Image, size: int = 160, key: str = "") -> Image.Image:
    """立绘 → 脸在正中间的圆形头像。优先用手工标定的裁剪。"""
    im = im.convert("RGBA")
    manual = FACE_CROPS.get(key)
    if manual:
        cx, cy, frac = manual
        side = int(min(im.width, im.height) * frac)
        left = int(cx * im.width - side / 2)
        top = int(cy * im.height - side / 2)
    else:
        anchor = face_anchor(im)
        if anchor:
            cx, cy, fw, fh = anchor
            side = int(max(im.width * fw, im.height * fh) * 2.1)
            side = max(side, int(min(im.width, im.height) * 0.38))
            side = min(side, min(im.width, im.height))
            left = int(cx * im.width - side / 2)
            top = int(cy * im.height - side / 2)
        else:
            side = int(min(im.width, im.height) * 0.55)
            left = (im.width - side) // 2
            top = int(im.height * 0.08)

    left = max(0, min(left, im.width - side))
    top = max(0, min(top, im.height - side))
    crop = im.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((1, 1, size - 2, size - 2), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(crop, (0, 0), mask)
    return out


if __name__ == "__main__":
    sys.exit(main())


