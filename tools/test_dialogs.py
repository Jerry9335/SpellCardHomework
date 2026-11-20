"""截取设置 / 关于程序 / 关于作者，检查是否还有内容被裁掉。"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import tkinter as tk

import app as appmod
from modules import capture

capture.make_dpi_aware()
root = tk.Tk()
a = appmod.App(root)
root.deiconify()
for _ in range(10):
    root.update()
    time.sleep(0.05)


def grab(title: str, name: str) -> None:
    for _ in range(20):
        w = next((x for x in capture.list_windows(include_own=True)
                  if title in x.title and x.pid == os.getpid()), None)
        if w:
            capture.grab(w, "window").image.save(os.path.join(HERE, "shots", name))
            print(name, w.w, w.h)
            return
        time.sleep(0.1)
    print("not found", title)


a._open_settings()
time.sleep(0.6)
root.update()
grab("设置", "settings_fixed.png")
for t in root.winfo_children():
    if isinstance(t, tk.Toplevel):
        t.destroy()
time.sleep(0.3)

a._about_app()
time.sleep(0.5)
root.update()
grab("关于程序", "about_fixed.png")
for t in root.winfo_children():
    if isinstance(t, tk.Toplevel):
        t.destroy()
time.sleep(0.3)

a._about_authors()
time.sleep(0.5)
root.update()
grab("关于作者", "authors_fixed.png")
root.destroy()
