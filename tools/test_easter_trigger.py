"""关于作者解锁测试：方向键晃动、B/A 符卡、Konami 解锁新主题。"""
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

cfg_dir = tempfile.mkdtemp(prefix="theme_unlock_")
os.environ["SHINICHI_CONFIG_DIR"] = cfg_dir
with open(os.path.join(cfg_dir, "config.json"), "w", encoding="utf-8") as f:
    json.dump({"theme": "classic", "theme_unlocked": False}, f)

import tkinter as tk

import app as appmod
from modules import theme

root = tk.Tk()
a = appmod.App(root)
root.deiconify()
a._about_authors()
for _ in range(20):
    root.update()
    time.sleep(0.04)

win = next(w for w in root.winfo_children()
           if isinstance(w, tk.Toplevel) and w.title() == "关于作者")
win.focus_force()
root.update()


def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.02)


# 不真的写配置/重启
a._save_config = lambda: None
requested = []
a._request_theme_change = lambda name: requested.append(name)

win.event_generate("<Key>", keysym="Up")
root.update()
assert getattr(win, "_shake_base", None) is not None
pump(0.7)
assert getattr(win, "_shake_base", None) is None

win.event_generate("<Key>", keysym="b")
root.update()
assert getattr(win, "_spell_flash", None) is not None
pump(0.6)
assert getattr(win, "_spell_flash", None) is None

for k in ("Up", "Up", "Down", "Down", "Left", "Right", "Left", "Right", "b", "a", "Return"):
    win.event_generate("<Key>", keysym=k)
    root.update()
    time.sleep(0.02)

print("unlocked:", a.cfg.get("theme_unlocked"), "theme:", a.cfg.get("theme"),
      "requested:", requested)
assert a.cfg.get("theme_unlocked") is True
assert a.cfg.get("theme") == theme.THEME_NEW
assert requested and requested[-1] == theme.THEME_NEW

root.destroy()
print("RESULT: PASS")
