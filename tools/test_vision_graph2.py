"""清晰版函数图：每格 1 单位、每个刻度都标数字，测视觉模型读数。"""
import base64
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from PIL import Image, ImageDraw, ImageFont

from modules import llm, prompts, settings

FONT = r"C:\Windows\Fonts\arial.ttf"
W, H = 1200, 760
im = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(im)
f = ImageFont.truetype(FONT, 16)

ox, oy = W // 2, H // 2
sx, sy = 40, 32


def px(x, y):
    return ox + x * sx, oy - y * sy


for i in range(-10, 11):
    d.line([px(i, -10), px(i, 10)], fill=(200, 210, 200))
    d.line([px(-10, i), px(10, i)], fill=(200, 210, 200))
d.line([px(-10, 0), px(10, 0)], fill="black", width=3)
d.line([px(0, -10), px(0, 10)], fill="black", width=3)
for i in range(-10, 11):
    if i == 0:
        continue
    x, y = px(i, 0)
    d.text((x - 6, y + 6), str(i), font=f, fill="black")
    x, y = px(0, i)
    d.text((x + 8, y - 9), str(i), font=f, fill="black")
d.text(px(10.4, 0), "x", font=f, fill="black")
d.text(px(0.4, 10.2), "y", font=f, fill="black")

pts = [(-7, 2.5), (-6.5, 4.2), (-6, 5.4), (-5, 6), (-4, 5.2), (-3, 3.2),
       (-2, 0.8), (-1, -1.8), (0, -5), (1, -1.8), (2, 1.2), (3, 3.8),
       (4, 5.2), (5, 5.8), (6, 5.2), (7, 4), (8, 3.2), (9, 2.5)]
xy = [px(x, y) for x, y in pts]
d.line(xy, fill=(20, 20, 180), width=5)
d.ellipse([xy[0][0] - 8, xy[0][1] - 8, xy[0][0] + 8, xy[0][1] + 8], fill=(20, 20, 180))
d.ellipse([xy[-1][0] - 8, xy[-1][1] - 8, xy[-1][0] + 8, xy[-1][1] + 8],
          outline=(20, 20, 180), width=5, fill="white")

p = os.path.join(HERE, "_vision_graph2.png")
im.save(p)
url = "data:image/png;base64," + base64.b64encode(open(p, "rb").read()).decode("ascii")

cfg = settings.load()
vision = (cfg.get("vision_model") or cfg.get("model") or "").strip()
base = (cfg.get("vision_base_url") or cfg.get("base_url") or "").strip()
key = (cfg.get("vision_api_key") or cfg.get("api_key") or "").strip()

q = ("Read the graph carefully using the axis labels. "
     "Give the domain and the range of the function. Answer in interval notation.")
res = llm.chat_once(base, key, vision, prompts.web_messages_image(q, url), temperature=0.0)
print("=== 模型输出 ===")
print(res.text[:400])

text = res.text.replace(" ", "")
checks = {
    "定义域左端 -7": "[-7" in text,
    "定义域右端 9（开）": "9)" in text,
    "值域下界 -5": "-5" in text,
    "值域上界 6": "6" in text,
}
for k, v in checks.items():
    print(("  ✓ " if v else "  ✗ ") + k)
print("RESULT:", "PASS" if all(checks.values()) else "FAIL")
