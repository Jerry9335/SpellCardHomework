"""用 DiceBear 生成一批「可安全使用」的二次元风格头像（CC BY 4.0），并拼成预览图。"""
import os
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "assets_candidates", "dicebear")
os.makedirs(OUT, exist_ok=True)

UA = {"User-Agent": "SpellCardHomework/1.0"}
STYLES = ["lorelei", "adventurer", "micah", "notionists"]
SEEDS = ["Shinichi", "Fastrof", "Reimu", "Marisa", "Sakuya", "Patchouli", "Yukari", "Keine"]
BG = "2A2342"


def fetch(style: str, seed: str) -> str:
    q = urllib.parse.urlencode({"seed": seed, "size": "256", "backgroundColor": BG})
    url = f"https://api.dicebear.com/9.x/{style}/png?{q}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    dest = os.path.join(OUT, f"{style}_{seed}.png")
    with open(dest, "wb") as f:
        f.write(data)
    return dest


def main() -> None:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 15)
    cell = 150
    cols = len(SEEDS)
    sheet = Image.new("RGB", (cols * cell, len(STYLES) * (cell + 26) + 10), (20, 18, 33))
    draw = ImageDraw.Draw(sheet)
    for row, style in enumerate(STYLES):
        for col, seed in enumerate(SEEDS):
            try:
                path = fetch(style, seed)
                im = Image.open(path).convert("RGBA").resize((cell - 20, cell - 20), Image.LANCZOS)
            except Exception as e:
                print("fail", style, seed, e)
                continue
            # 圆形裁切
            mask = Image.new("L", im.size, 0)
            ImageDraw.Draw(mask).ellipse((0, 0, im.width - 1, im.height - 1), fill=255)
            bg = Image.new("RGBA", im.size, (28, 24, 48, 255))
            bg.paste(im, (0, 0), mask)
            x = col * cell + 10
            y = row * (cell + 26) + 26
            sheet.paste(bg.convert("RGB"), (x, y))
            if col == 0:
                draw.text((x, y - 22), style, font=font, fill=(232, 196, 106))
    out = os.path.join(ROOT, "docs", "dicebear_samples.png")
    sheet.save(out)
    print("saved", out)


if __name__ == "__main__":
    main()
