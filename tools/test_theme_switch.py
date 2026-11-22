"""主题切换逻辑：空闲立即重启，答题中延后。"""
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

cfg_dir = tempfile.mkdtemp(prefix="theme_switch_")
os.environ["SHINICHI_CONFIG_DIR"] = cfg_dir
with open(os.path.join(cfg_dir, "config.json"), "w", encoding="utf-8") as f:
    json.dump({"theme": "classic", "theme_unlocked": True}, f)

import tkinter as tk

import app as appmod
from modules import theme

root = tk.Tk()
a = appmod.App(root)
root.deiconify()
a._save_config = lambda: None
relaunched = []
a._relaunch_for_theme = lambda: relaunched.append(a.cfg.get("theme"))


def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.02)


pump(0.3)
a._request_theme_change(theme.THEME_NEW)
pump(0.8)
print("idle request:", relaunched, "cfg:", a.cfg.get("theme"))
assert relaunched == [theme.THEME_NEW]
assert a.cfg.get("theme") == theme.THEME_NEW

# 模拟切回经典，但正在答题：先不重启
a.theme = theme.THEME_NEW
a.cfg["theme"] = theme.THEME_NEW
a._pending_theme = None
relaunched.clear()
a.busy = True
a._request_theme_change(theme.THEME_CLASSIC)
pump(0.7)
assert not relaunched, relaunched
print("busy deferred:", a._pending_theme)
a.busy = False
a._maybe_apply_pending_theme()
pump(0.8)
print("after idle:", relaunched, "cfg:", a.cfg.get("theme"))
assert relaunched == [theme.THEME_CLASSIC]
assert a.cfg.get("theme") == theme.THEME_CLASSIC

root.destroy()
print("RESULT: PASS")
