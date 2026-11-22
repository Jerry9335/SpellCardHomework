"""「晨午宵绘卷」主题：主界面三时段 + 启动画面。"""
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

cfg_dir = tempfile.mkdtemp(prefix="theme_new_")
os.environ["SHINICHI_CONFIG_DIR"] = cfg_dir
with open(os.path.join(cfg_dir, "config.json"), "w", encoding="utf-8") as f:
    json.dump({"theme": "chenwuxiao", "theme_unlocked": True}, f)

import tkinter as tk

import app as appmod
from modules import banner_time, capture, theme

capture.make_dpi_aware()
root = tk.Tk()
a = appmod.App(root)
root.deiconify()
orig_phase = banner_time.phase_for_now


def pump(sec=0.3):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.02)


pump(0.8)
assert a.theme == theme.THEME_NEW, a.theme
assert a._full_bg_item is not None
assert len(a._theme_panel_frames) == 3
assert all(f.winfo_manager() == "place" for f in a._theme_panel_frames)
assert a._full_bg_canvas.find_withtag("theme_title")
print("theme:", a.theme, "full_bg:", bool(a._full_bg_item),
      "title:", bool(a._full_bg_canvas.find_withtag("theme_title")),
      "panels:", [f.winfo_manager() for f in a._theme_panel_frames])


def shot(phase, name):
    banner_time.phase_for_now = lambda p=phase: p
    a._apply_phase(phase, fade=True)
    pump(0.8)
    win = next((w for w in capture.list_windows(include_own=True)
                if w.pid == os.getpid() and "符卡作业簿" in w.title), None)
    if win:
        capture.grab(win, "window").image.save(os.path.join(HERE, "shots", f"theme_new_{name}.png"))
    print("saved", name, a.greet_var.get())


shot("day", "morning")
shot("afternoon", "afternoon")
shot("night", "night")
banner_time.phase_for_now = orig_phase

# 启动画面：直接调用 make_splash
banner_time.phase_for_now = lambda: "day"
sp = appmod.make_splash(root)
pump(0.4)
assert sp is not None
sp[0].update_idletasks()
x, y = sp[0].winfo_rootx(), sp[0].winfo_rooty()
w, h = sp[0].winfo_width(), sp[0].winfo_height()
capture.grab_region((x, y, x + w, y + h)).image.save(
    os.path.join(HERE, "shots", "theme_new_splash_morning.png"))
print("saved splash")
try:
    sp[0].destroy()
except Exception:
    pass
banner_time.phase_for_now = orig_phase
root.destroy()
print("RESULT: PASS")
