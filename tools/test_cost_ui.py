"""检查：状态栏本单费用文案 + 账本标题字体。"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ["SHINICHI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="sch_cost_")
sys.path.insert(0, ROOT)

import tkinter as tk

import app as appmod
from modules import capture, usage

capture.make_dpi_aware()
root = tk.Tk()
a = appmod.App(root)
root.deiconify()
for _ in range(10):
    root.update()
    time.sleep(0.05)

text = a._cost_text("deepseek-flash", {"prompt_tokens": 711, "completion_tokens": 20})
print("cost text:", text)
a.meta_var.set(text)
for _ in range(5):
    root.update()

w = next((x for x in capture.list_windows(include_own=True)
          if x.title.strip() == "符卡作业簿"), None)
if w:
    capture.grab(w, "window").image.save(os.path.join(HERE, "shots", "main_cost.png"))
    print("saved main_cost.png")

# 账本窗口
a._open_usage()
for _ in range(20):
    root.update()
    time.sleep(0.05)
u = next((x for x in capture.list_windows(include_own=True)
          if "香火钱账本" in x.title), None)
if u:
    capture.grab(u, "window").image.save(os.path.join(HERE, "shots", "usage_font.png"))
    print("saved usage_font.png")
root.destroy()
