"""从 B 站专栏搜集东方相关图片（只做候选，供人工确认授权）。

- 搜索文章 -> 抓正文图片 -> 下载 -> 拼成带编号的预览图
- 同时记录：文章标题 / 作者 / 链接 / 文中是否写了「自取 / 转载 / 禁止转载 / 商用」
"""
from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "assets_candidates")
PREVIEW = os.path.join(ROOT, "docs", "bili_candidates.png")
os.makedirs(OUT, exist_ok=True)

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
}

KEYWORDS = ["东方 头像", "东方Project 头像", "东方 壁纸", "东方 立绘", "东方 图片分享"]
BLOCK = ("r18", "涩", "福利", "色气", "成人", "裸", "性转")
IMG_RE = re.compile(r"//i[0-9]\.hdslb\.com/bfs/article/[0-9a-f]+\.(?:png|jpg|jpeg|webp)")


def get(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def search(keyword: str, page: int = 1) -> list[dict]:
    kw = urllib.parse.quote(keyword)
    url = (f"https://api.bilibili.com/x/web-interface/search/type"
           f"?search_type=article&keyword={kw}&page={page}")
    data = json.loads(get(url))
    return (data.get("data") or {}).get("result") or []


def article_images(cvid: int) -> tuple[list[str], str]:
    """返回 (图片 URL 列表, 文章正文文本)。"""
    page = get(f"https://www.bilibili.com/read/cv{cvid}").decode("utf-8", "ignore")
    urls = []
    for m in IMG_RE.finditer(page):
        u = "https:" + m.group(0)
        if u not in urls:
            urls.append(u)
    # 粗略提取正文文字（用于判断是否允许转载）
    text = re.sub(r"<script.*?</script>", " ", page, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(re.sub(r"\s+", " ", text))
    return urls, text[:4000]


def permission_note(text: str) -> str:
    keys = {
        "自取": "文中提到「自取」",
        "可保存": "文中提到「可保存」",
        "转载": "文中提到「转载」",
        "禁止转载": "文中提到「禁止转载」",
        "禁止商用": "文中提到「禁止商用」",
        "授权": "文中提到「授权」",
    }
    hits = [v for k, v in keys.items() if k in text]
    return "；".join(hits) if hits else "未说明"


def main() -> None:
    seen_articles: set[int] = set()
    index = 0
    rows: list[dict] = []
    downloaded: list[tuple[int, str]] = []

    for kw in KEYWORDS:
        try:
            items = search(kw)
        except Exception as e:
            print("搜索失败", kw, e)
            continue
        for it in items:
            title = re.sub(r"<[^>]+>", "", it.get("title") or "")
            if any(b in title.lower() for b in BLOCK):
                continue
            cvid = it.get("id")
            if not cvid or cvid in seen_articles:
                continue
            seen_articles.add(cvid)
            try:
                urls, text = article_images(cvid)
            except Exception:
                continue
            note = permission_note(text)
            picked = 0
            for u in urls[:4]:
                index += 1
                ext = ".png" if u.endswith(".png") else ".jpg"
                dest = os.path.join(OUT, f"bili_{index:03d}{ext}")
                try:
                    data = get(u, timeout=40)
                    if len(data) < 15000:
                        index -= 1
                        continue
                    with open(dest, "wb") as f:
                        f.write(data)
                except Exception:
                    index -= 1
                    continue
                downloaded.append((index, dest))
                picked += 1
                if picked >= 4:
                    break
            if picked:
                rows.append({
                    "idx": f"{index - picked + 1}-{index}",
                    "title": title[:50],
                    "author": it.get("author"),
                    "url": f"https://www.bilibili.com/read/cv{cvid}",
                    "note": note,
                })
            if index >= 40:
                break
        if index >= 40:
            break

    with open(os.path.join(OUT, "sources.json"), "w", encoding="utf-8") as f:
        json.dump({"rows": rows}, f, ensure_ascii=False, indent=2)

    # 拼预览图
    from PIL import Image, ImageDraw, ImageFont

    scale = 180
    cols = 6
    n = len(downloaded)
    rows_n = max(1, (n + cols - 1) // cols)
    sheet = Image.new("RGB", (cols * scale, rows_n * (scale + 22)), (20, 18, 33))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 13)
    for i, (idx, path) in enumerate(downloaded):
        try:
            im = Image.open(path).convert("RGB")
        except Exception:
            continue
        im.thumbnail((scale, scale), Image.LANCZOS)
        x = (i % cols) * scale + (scale - im.width) // 2
        y = (i // cols) * (scale + 22) + 20
        sheet.paste(im, (x, y))
        draw.text((x + 2, y - 18), f"#{idx}", font=font, fill=(232, 196, 106))
    sheet.save(PREVIEW)
    print("下载图片:", n, "预览:", PREVIEW)
    for r in rows:
        print(f"  {r['idx']:>7}  {r['title']}  @{r['author']}  {r['note']}  {r['url']}")


if __name__ == "__main__":
    main()
