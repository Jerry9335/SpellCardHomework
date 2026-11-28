"""截图：设置页下半部分 + 号外窗口。"""
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

a._open_settings()
for _ in range(10):
    root.update()
    time.sleep(0.05)

# 滚到底
for w in root.winfo_children():
    if isinstance(w, tk.Toplevel) and "设置" in w.title():
        for c in w.winfo_children():
            if isinstance(c, tk.Frame):
                for cc in c.winfo_children():
                    if isinstance(cc, tk.Canvas):
                        cc.yview_moveto(1.0)
for _ in range(20):
    root.update()
    time.sleep(0.05)

win = next((x for x in capture.list_windows(include_own=True)
            if "设置" in x.title and x.pid == os.getpid()), None)
if win:
    capture.grab(win, "window").image.save(os.path.join(HERE, "shots", "settings_bottom.png"))
    print("saved settings_bottom.png")

info = {"version": "1.1.7", "tag": "v1.1.7", "source": "gitee",
        "date": "2026-11-30", "notes": "· 新增自动检查更新\n· 新增 Windows Toast 通知\n· 自动答题稳定性修复",
        "url": "https://gitee.com/jerry6663/SpellCardHomework/releases/tag/v1.0.2",
        "download": "https://gitee.com/jerry6663/SpellCardHomework/releases/download/v1.0.2/Setup.exe"}
a._show_update_dialog(info)
for _ in range(20):
    root.update()
    time.sleep(0.05)
w2 = next((x for x in capture.list_windows(include_own=True)
           if "号外" in x.title and x.pid == os.getpid()), None)
if w2:
    capture.grab(w2, "window").image.save(os.path.join(HERE, "shots", "update_dialog.png"))
    print("saved update_dialog.png")
root.destroy()

