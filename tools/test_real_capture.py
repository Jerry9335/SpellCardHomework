"""真实场景测试：抓取桌面上那个练习窗口，用本地 OCR 识别，检查三个面板的流转。"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ.setdefault("SHINICHI_CONFIG_DIR", os.path.join(HERE, ".test_config"))
sys.path.insert(0, ROOT)

import tkinter as tk

from app import App
from modules import capture

capture.make_dpi_aware()

root = tk.Tk()
root.withdraw()
app = App(root)

# 找练习窗口
wins = capture.list_windows()
target = next((w for w in wins if "做作业" in w.title or "Homework" in w.title), None)
if target is None:
    print("没有找到练习窗口，当前窗口：")
    for w in wins[:10]:
        print("  ", w.title[:60])
    app.hotkeys.stop()
    root.destroy()
    sys.exit(2)

print("目标窗口:", target.title, target.rect)

app.window_var.set("整个屏幕")
app.target_title = target.title
app.target_hwnd = target.hwnd
app.region = None
app.method_var.set("后台抓取（可抓被遮挡窗口）")
app.ocr_var.set("本地 OCR")
app.trans_var.set(False)

t0 = time.time()
app.action_capture()
deadline = time.time() + 40
while time.time() < deadline:
    root.update()
    app._pump()
    if not app.busy and app._panel_text("src"):
        break
    time.sleep(0.05)

root.update()
app._pump()

print(f"\n耗时 {time.time()-t0:.1f}s")
print("--- 原文 ---")
print(app._panel_text("src")[:800])
print("--- 答案（预期因无网络/无 Key 报错）---")
print(app._panel_text("ans")[:300])
print("--- 状态 ---")
print(app.status_var.get())

ok = bool(app._panel_text("src"))
print("\nRESULT:", "PASS" if ok else "FAIL")
try:
    app.hotkeys.stop()
except Exception:
    pass
root.destroy()
sys.exit(0 if ok else 1)
