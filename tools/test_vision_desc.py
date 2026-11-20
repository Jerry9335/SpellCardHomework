"""图注 + 截图 一起给模型：验证 Pearson 场景下能否精确读出定义域/值域。"""
import base64
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from modules import llm, prompts, settings

img = os.path.join(HERE, "_vision_graph2.png")
url = "data:image/png;base64," + base64.b64encode(open(img, "rb").read()).decode("ascii")

cfg = settings.load()
vision = (cfg.get("vision_model") or cfg.get("model") or "").strip()
base = (cfg.get("vision_base_url") or cfg.get("base_url") or "").strip()
key = (cfg.get("vision_api_key") or cfg.get("api_key") or "").strip()

desc = ("【图注】A coordinate system has a horizontal x-axis labeled from negative 10 to 10 "
        "in increments of 1 and a vertical y-axis labeled from negative 10 to 10 in increments of 1. "
        "A curve begins at the closed circle plotted point (negative 7, 2.5) and rises to the point "
        "(negative 5, 6). The curve then falls to the point (0, negative 5) and then rises again to "
        "the point (5, 5.8). The curve then falls to the open circle plotted point (9, 2.5).")

q = ("Give the domain and the range of the function in the graph. Answer in interval notation.\n\n"
     + desc)

for attempt in range(2):
    res = llm.chat_once(base, key, vision, prompts.web_messages_image(q, url), temperature=0.0)
    print(f"--- 第 {attempt + 1} 次 ---")
    print(res.text[:300])
    text = res.text.replace(" ", "")
    checks = {
        "定义域 [-7,9)": "[-7" in text and "9)" in text,
        "值域 [-5,6]": "-5" in text and "6]" in text,
    }
    for k, v in checks.items():
        print(("  ✓ " if v else "  ✗ ") + k)
    if all(checks.values()):
        print("RESULT: PASS")
        break
else:
    print("RESULT: FAIL")
