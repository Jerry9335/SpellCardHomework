"""生成作者圆形头像（160px，带金色圆环）。"""
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "assets", "authors")
os.makedirs(OUT, exist_ok=True)

SOURCES = {
    "shinichi": r"D:\zack\Desktop\Shinichi.jpg",
    "fastrof": r"D:\zack\Desktop\Fastrof.jpg",
}


def make_round(src: str, dest: str, size: int = 200) -> None:
    im = Image.open(src).convert("RGB")
    # 居中裁成正方形
    side = min(im.width, im.height)
    left = (im.width - side) // 2
    top = (im.height - side) // 2
    im = im.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)

    ring = max(3, size // 40)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((ring, ring, size - ring, size - ring), fill=255)
    canvas.paste(im, (0, 0), mask)
    d = ImageDraw.Draw(canvas)
    d.ellipse((ring // 2, ring // 2, size - ring // 2, size - ring // 2),
              outline=(232, 196, 106, 255), width=ring)
    canvas.save(dest)


if __name__ == "__main__":
    for name, src in SOURCES.items():
        if not os.path.exists(src):
            print("找不到", src)
            continue
        dest = os.path.join(OUT, f"{name}.png")
        make_round(src, dest)
        print("ok", dest, os.path.getsize(dest) // 1024, "KB")
