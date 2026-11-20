"""生成 MSIX 所需的图标（从 assets/icon.ico 或 banner.png 缩放）。"""
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "Assets")
os.makedirs(OUT, exist_ok=True)

SRC = os.path.join(ROOT, "assets", "icon.ico")
if not os.path.exists(SRC):
    SRC = os.path.join(ROOT, "assets", "banner.png")

base = Image.open(SRC).convert("RGBA")
# 用正方形画布，居中裁切
side = min(base.width, base.height)
left = (base.width - side) // 2
top = (base.height - side) // 2
square = base.crop((left, top, left + side, top + side))

SIZES = {
    "StoreLogo.png": (50, 50),
    "Square44x44Logo.png": (44, 44),
    "Square71x71Logo.png": (71, 71),
    "Square150x150Logo.png": (150, 150),
    "Square310x310Logo.png": (310, 310),
    "Wide310x150Logo.png": (310, 150),
}

for name, (w, h) in SIZES.items():
    if name.startswith("Wide"):
        canvas = Image.new("RGBA", (w, h), (20, 18, 33, 255))
        logo = square.resize((h, h), Image.LANCZOS)
        canvas.alpha_composite(logo, ((w - h) // 2, 0))
        canvas.save(os.path.join(OUT, name))
    else:
        square.resize((w, h), Image.LANCZOS).save(os.path.join(OUT, name))
    print("ok", name, (w, h))

print("图标输出:", OUT)
