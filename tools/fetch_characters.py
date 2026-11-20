"""从 THBWiki 抓取东方角色官方立绘，并生成圆形头像。

安全策略：
- 只接受图片（魔数校验 + Pillow 完整解码），限制单文件大小；
- 统一转存 PNG（RGBA），不执行任何脚本；
- 记录来源到 assets/char/SOURCES.md；
- 下载后由 tools/scan_assets.py 调用 Windows Defender 扫描。
"""
from __future__ import annotations

import io
import os
import re
import sys
import time
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "assets", "char")
os.makedirs(OUT, exist_ok=True)

RAW = "https://raw.githubusercontent.com/Delsin-Yu/THBWiki-Markdown/main/sources/"
MODERN_PAGE = "东方刚欲异闻"

# key, 中文名, 优先从哪个作品页取立绘（None = 用角色自己的词条页）
CHARACTERS = [
    ("reimu", "博丽灵梦", "东方刚欲异闻"),
    ("marisa", "雾雨魔理沙", "东方刚欲异闻"),
    ("keine", "上白泽慧音", None),
    ("yukari", "八云紫", None),
    ("remilia", "蕾米莉亚·斯卡蕾特", "东方绯想天"),
    ("patchouli", "帕秋莉·诺蕾姬", "东方绯想天"),
    ("sakuya", "十六夜咲夜", "东方虹龙洞"),
    ("flandre", "芙兰朵露·斯卡蕾特", "东方刚欲异闻"),
]

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "image/*,*/*",
}
MAX_BYTES = 8 * 1024 * 1024
ALLOWED = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"RIFF", b"GIF8")

_URL_RE = re.compile(r"https://upload\.thwiki\.cc/(?:thumb/)?[^\"' )\s]+?\.png(?:/\d+px-[^\"' )\s]+)?")


def http_get(url: str, timeout: float = 40) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise RuntimeError(f"文件过大：{url}")
    return data


def check_image(data: bytes) -> None:
    if not any(data.startswith(m) for m in ALLOWED):
        raise RuntimeError("不是图片（魔数不匹配）")
    im = Image.open(io.BytesIO(data))
    im.load()
    if im.width < 40 or im.height < 40:
        raise RuntimeError(f"尺寸异常：{im.size}")


def thumb_to_original(url: str) -> str:
    m = re.match(r"(https://upload\.thwiki\.cc)/thumb/([0-9a-f])/([0-9a-f]{2})/([^/]+)/\d+px-.*", url)
    return f"{m.group(1)}/{m.group(2)}/{m.group(3)}/{m.group(4)}" if m else url


def page_markdown(page: str) -> str:
    return http_get(RAW + urllib.parse.quote(page) + ".md").decode("utf-8", "replace")


def portraits(md: str) -> list[tuple[str, str]]:
    out, seen = [], set()
    for m in _URL_RE.finditer(md):
        u = m.group(0)
        name = u.split("/")[-2] if "/thumb/" in u else u.split("/")[-1]
        name = urllib.parse.unquote(name)
        if "立绘" not in name or name in seen:
            continue
        seen.add(name)
        out.append((name, thumb_to_original(u)))
    return out


def make_avatar(im: Image.Image, size: int = 96) -> Image.Image:
    """从立绘里裁出头像，并做成圆形。"""
    bbox = im.getbbox() or (0, 0, im.width, im.height)
    bx0, by0, bx1, by1 = bbox
    bw, bh = bx1 - bx0, by1 - by0
    side = int(min(bw * 0.48, bh * 0.52)) or min(bw, bh)
    left = bx0 + (bw - side) // 2
    top = by0 + int(bh * 0.20)
    if top + side > by1:
        top = max(by0, by1 - side)
    head = im.crop((left, top, left + side, top + side))
    head = head.resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((1, 1, size - 2, size - 2), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(head, (0, 0), mask)
    return out


def main() -> int:
    sources, ok = [], 0
    cache: dict[str, list[tuple[str, str]]] = {}

    def page_portraits(page: str) -> list[tuple[str, str]]:
        if page not in cache:
            try:
                cache[page] = portraits(page_markdown(page))
            except Exception as e:
                print(f"[warn] 取《{page}》页失败：{e}")
                cache[page] = []
        return cache[page]

    for key, cn, prefer_page in CHARACTERS:
        try:
            name = url = None
            if prefer_page:
                for pname, purl in page_portraits(prefer_page):
                    if pname.startswith(cn):
                        name, url = pname, purl
                        break
            if url is None:
                for pname, purl in page_portraits(cn):
                    name, url = pname, purl
                    break
            if url is None:
                print(f"[skip] {cn}: 没找到立绘")
                continue

            data = None
            for attempt in range(3):
                try:
                    data = http_get(url)
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(1.0)
            check_image(data)
            im = Image.open(io.BytesIO(data)).convert("RGBA")
            im.save(os.path.join(OUT, f"{key}.png"), "PNG")
            make_avatar(im).save(os.path.join(OUT, f"avatar_{key}.png"), "PNG")
            sources.append((cn, key, name, f"{im.width}x{im.height}", url))
            print(f"[ok] {cn}: {im.size} <- {name}")
            ok += 1
            time.sleep(0.4)
        except Exception as e:
            print(f"[fail] {cn}: {e}")

    with open(os.path.join(OUT, "SOURCES.md"), "w", encoding="utf-8") as f:
        f.write("# 角色立绘来源\n\n")
        f.write("图像取自 THBWiki（https://thwiki.cc）收录的《东方 Project》原作立绘。\n")
        f.write("版权归 ZUN / 上海爱丽丝幻乐团 所有，本工具仅作个人学习用途，不作商业使用。\n\n")
        f.write("| 角色 | 文件 | 原图名 | 尺寸 | 来源 |\n|---|---|---|---|---|\n")
        for cn, key, name, size, url in sources:
            f.write(f"| {cn} | {key}.png | {name} | {size} | {url} |\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())




