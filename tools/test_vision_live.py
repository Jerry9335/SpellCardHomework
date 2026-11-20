"""实测视觉模型：生成一张带已知答案的题图，看它能否正确识别/作答。"""
import base64
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from PIL import Image, ImageDraw, ImageFont

from modules import llm, prompts, settings

FONT = r"C:\Windows\Fonts\msyh.ttc"


def make_image(path: str) -> str:
    im = Image.new("RGB", (860, 420), "white")
    d = ImageDraw.Draw(im)
    f_big = ImageFont.truetype(FONT, 30)
    f_mid = ImageFont.truetype(FONT, 26)
    d.text((28, 24), "Solve for x:  2x + 6 = 14", font=f_big, fill="black")
    d.text((28, 86), "Choose the correct answer:", font=f_mid, fill="black")
    opts = ["A. x = 2", "B. x = 4", "C. x = 6", "D. x = 8"]
    for i, o in enumerate(opts):
        d.text((48, 136 + i * 44), o, font=f_mid, fill="black")
    d.text((28, 330), "第二行：求 3² + 4² 的值 = 25", font=f_mid, fill=(20, 20, 120))
    im.save(path)
    return path


def data_url(path: str) -> str:
    raw = open(path, "rb").read()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


cfg = settings.load()
vision = (cfg.get("vision_model") or cfg.get("model") or "").strip()
base = (cfg.get("vision_base_url") or cfg.get("base_url") or "").strip()
key = (cfg.get("vision_api_key") or cfg.get("api_key") or "").strip()
print("视觉模型:", vision, "| 接口:", base)
print("Key:", key[:6] + "..." if key else "(空)")

p = make_image(os.path.join(HERE, "_vision_test.png"))
url = data_url(p)
print("测试图:", p, os.path.getsize(p), "bytes")

print("\n=== 1) 识图作答（web_messages_image） ===")
try:
    res = llm.chat_once(base, key, vision, prompts.web_messages_image(
        "Solve for x: 2x + 6 = 14. Which option is correct?", url), temperature=0.2)
    print(res.text[:400])
    print("解析:", prompts.parse_web_answer(res.text))
except Exception as e:
    print("调用失败:", e)

print("\n=== 2) 纯 OCR（ocr_messages） ===")
try:
    res = llm.chat_once(base, key, vision, prompts.ocr_messages(url), temperature=0.0)
    print(res.text[:400])
except Exception as e:
    print("调用失败:", e)
