"""截取「关于程序 / 关于作者」对话框，检查排版与头像。"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ.setdefault("SHINICHI_CONFIG_DIR", os.path.join(HERE, "shots", ".cfg"))
sys.path.insert(0, ROOT)

import tkinter as tk

from app import App
from modules import capture

capture.make_dpi_aware()
shots = os.path.join(HERE, "shots")
os.makedirs(shots, exist_ok=True)

root = tk.Tk()
app = App(root)
for _ in range(10):
    root.update()
    time.sleep(0.05)

main = None
for _ in range(30):
    for w in capture.list_windows(include_own=True):
        if w.pid == os.getpid() and w.title.strip() == "符卡作业簿":
            main = w
            break
    if main:
        break
    time.sleep(0.1)
if main:
    time.sleep(0.6)
    capture.grab(main, "window").image.save(os.path.join(shots, "main_about.png"))
    print("main saved")


def shot_dialog(title: str, name: str, opener) -> None:
    opener()
    time.sleep(0.9)
    root.update()
    for _ in range(30):
        w = next((x for x in capture.list_windows(include_own=True)
                  if x.pid == os.getpid() and x.title.strip() == title), None)
        if w:
            time.sleep(0.4)
            capture.grab(w, "window").image.save(os.path.join(shots, name))
            print(name, "saved", w.w, "x", w.h)
            break
        time.sleep(0.1)
    for child in root.winfo_children():
        if isinstance(child, tk.Toplevel):
            try:
                child.destroy()
            except Exception:
                pass
    time.sleep(0.3)


shot_dialog("关于程序", "about_app.png", app._about_app)
shot_dialog("关于作者", "about_authors.png", app._about_authors)

try:
    app.hotkeys.stop()
    app.clip_watcher.stop()
except Exception:
    pass
root.destroy()
