"""横幅时段/淡入测试 + 白天/夜晚截图。"""
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
_cfg = tempfile.mkdtemp(prefix="banner_classic_")
os.environ["SHINICHI_CONFIG_DIR"] = _cfg
with open(os.path.join(_cfg, "config.json"), "w", encoding="utf-8") as _f:
    json.dump({"theme": "classic", "theme_unlocked": False}, _f)
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import tkinter as tk

import app as appmod
from modules import banner_time, capture

capture.make_dpi_aware()
root = tk.Tk()
a = appmod.App(root)
root.deiconify()
for _ in range(12):
    root.update()
    time.sleep(0.05)

print("当前阶段:", a._banner_phase, "期望:", banner_time.phase_for_now())
assert a._banner_phase == banner_time.phase_for_now()
assert a._banner_src is not None and a._banner_src.size == (1920, 320)


def force(phase, name):
    # 测试时固定时钟，避免 1.5s 定时器按真实时间把阶段改回去
    orig = banner_time.phase_for_now
    banner_time.phase_for_now = lambda: phase
    a._apply_banner_phase(phase, fade=True)
    for _ in range(20):
        root.update()
        time.sleep(0.03)
    assert a._banner_phase == phase
    assert a._banner_fade_job is None, "淡入应在 200ms 左右结束"
    win = next((w for w in capture.list_windows(include_own=True)
                if w.pid == os.getpid() and "符卡作业簿" in w.title), None)
    if win:
        capture.grab(win, "window").image.save(os.path.join(HERE, "shots", f"banner_{name}.png"))
        print("saved", name)
    print("切换", phase, "OK")
    banner_time.phase_for_now = orig


force("day", "day")
force("afternoon", "afternoon")
force("night", "night")
root.destroy()
print("RESULT: PASS")
