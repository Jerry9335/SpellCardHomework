"""GUI 级测试：真实创建窗口，直接把图片塞进识别流水线，验证三个面板与流式输出。"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ.setdefault("SHINICHI_CONFIG_DIR", os.path.join(HERE, ".test_config"))
sys.path.insert(0, ROOT)

import tkinter as tk
from PIL import Image

from app import App
from modules import capture
from tools.mock_server import serve

srv = serve(8766)
capture.make_dpi_aware()

root = tk.Tk()
root.withdraw()  # 测试时不显示窗口
app = App(root)

app.base_var.set("http://127.0.0.1:8766/v1")
app.key_var.set("test-key")
app.model_var.set("mock-reasoner")
app.vision_var.set("mock-vision")
app.ocr_var.set("视觉模型")
app.trans_var.set(True)
app.effort_var.set("中 medium")

img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots", "grab_front.png")
if not os.path.exists(img_path):
    img_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_quiz.png")
    Image.new("RGB", (900, 400), "white").save(img_path)
image = Image.open(img_path)

app._start_job("recognize", image=image, source="测试截图")

deadline = time.time() + 20
while time.time() < deadline:
    root.update()
    app._pump()
    if not app.busy and app._panel_text("ans"):
        break
    time.sleep(0.02)

root.update()
app._pump()

print("=== 原文面板 ===")
print(app._panel_text("src")[:400])
print("\n=== 翻译面板 ===")
print(app._panel_text("trans")[:300])
print("\n=== 答案面板 ===")
print(app._panel_text("ans")[:400])
print("\n=== 状态 ===")
print("status:", app.status_var.get())
print("meta:", app.meta_var.get())
print("busy:", app.busy)

ok = bool(app._panel_text("src")) and bool(app._panel_text("trans")) and bool(app._panel_text("ans"))
print("\nRESULT:", "PASS" if ok else "FAIL")

try:
    app.hotkeys.stop()
except Exception:
    pass
root.destroy()
srv.shutdown()
sys.exit(0 if ok else 1)
