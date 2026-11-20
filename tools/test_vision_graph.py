"""真实场景：只给图、不给文字线索，测视觉模型能否读出定义域/值域。

图：闭圆点 (-7,2.5) → 升到最高 (-5,6) → 降到最低 (0,-5) → 升到 (5,5.8) → 开圆点 (9,2.5)
标准答案：定义域 [-7,9)，值域 [-5,6]
"""
import base64
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from PIL import Image, ImageDraw, ImageFont

from modules import llm, prompts, settings

FONT = r"C:\Windows\Fonts\arial.ttf"
W, H = 900, 520
im = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(im)
f = ImageFont.truetype(FONT, 18)

ox, oy = W // 2, H // 2
sx, sy = 30, 22


def px(x, y):
    return ox + x * sx, oy - y * sy


for i in range(-10, 11):
    d.line([px(i, -10), px(i, 10)], fill=(205, 215, 205))
    d.line([px(-10, i), px(10, i)], fill=(205, 215, 205))
d.line([px(-10, 0), px(10, 0)], fill="black", width=2)
d.line([px(0, -10), px(0, 10)], fill="black", width=2)
for i in range(-10, 11, 2):
    d.text(px(i - 0.25, -0.8), str(i), font=f, fill="black")
    if i:
        d.text(px(-1.1, i - 0.25), str(i), font=f, fill="black")
d.text(px(10.3, 0), "x", font=f, fill="black")
d.text(px(0.3, 10), "y", font=f, fill="black")

pts = [(-7, 2.5), (-6.5, 4.2), (-6, 5.4), (-5, 6), (-4, 5.2), (-3, 3.2),
       (-2, 0.8), (-1, -1.8), (0, -5), (1, -1.8), (2, 1.2), (3, 3.8),
       (4, 5.2), (5, 5.8), (6, 5.2), (7, 4), (8, 3.2), (9, 2.5)]
xy = [px(x, y) for x, y in pts]
d.line(xy, fill=(20, 20, 160), width=4)
d.ellipse([xy[0][0] - 7, xy[0][1] - 7, xy[0][0] + 7, xy[0][1] + 7], fill=(20, 20, 160))
d.ellipse([xy[-1][0] - 7, xy[-1][1] - 7, xy[-1][0] + 7, xy[-1][1] + 7],
          outline=(20, 20, 160), width=4, fill="white")

p = os.path.join(HERE, "_vision_graph.png")
im.save(p)
url = "data:image/png;base64," + base64.b64encode(open(p, "rb").read()).decode("ascii")

cfg = settings.load()
vision = (cfg.get("vision_model") or cfg.get("model") or "").strip()
base = (cfg.get("vision_base_url") or cfg.get("base_url") or "").strip()
key = (cfg.get("vision_api_key") or cfg.get("api_key") or "").strip()

q = "Give the domain and the range of the function in the graph. Answer in interval notation."
msgs = prompts.web_messages_image(q, url)

res = llm.chat_once(base, key, vision, msgs, temperature=0.0)
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
sys.exit(0 if all(checks.values()) else 1)
