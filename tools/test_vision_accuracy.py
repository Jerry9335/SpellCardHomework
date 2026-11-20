"""更严格的识别准确性测试：已知文本/公式，OCR 后逐项核对。"""
import base64
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from PIL import Image, ImageDraw, ImageFont

from modules import llm, prompts, settings

FONT = r"C:\Windows\Fonts\msyh.ttc"

LINES = [
    "1. 求 f(x) = x² - 4x + 3 的最小值。",
    "2. 若 sin θ = 1/2，则 θ = 30°。",
    "3. 矩阵 [[1, 2], [3, 4]] 的行列式 = -2。",
    "4. 集合 A = {x | x ≥ 3}，B = (-∞, 5)，则 A ∩ B = [3, 5)。",
]
EXPECT = ["4x", "3", "sin", "1/2", "30", "1", "2", "3", "4", "-2", "≥", "5"]

im = Image.new("RGB", (980, 360), "white")
d = ImageDraw.Draw(im)
f = ImageFont.truetype(FONT, 28)
for i, ln in enumerate(LINES):
    d.text((30, 30 + i * 70), ln, font=f, fill="black")
p = os.path.join(HERE, "_vision_test2.png")
im.save(p)

raw = open(p, "rb").read()
url = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")

cfg = settings.load()
vision = (cfg.get("vision_model") or cfg.get("model") or "").strip()
base = (cfg.get("vision_base_url") or cfg.get("base_url") or "").strip()
key = (cfg.get("vision_api_key") or cfg.get("api_key") or "").strip()

res = llm.chat_once(base, key, vision, prompts.ocr_messages(url), temperature=0.0)
text = res.text
print("=== 识别结果 ===")
print(text)
print("\n=== 逐项核对 ===")

from modules.latex import latex_to_text

plain = latex_to_text(text)
flat = plain.replace(" ", "").replace("\n", "")
missing = [t for t in EXPECT if t not in flat and t not in text]
print("应包含:", EXPECT)
print("缺失:", missing or "无")
ok = not missing
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
