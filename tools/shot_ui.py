"""截图：启动画面（子进程真实启动）、主界面、设置面板。"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from modules import capture

capture.make_dpi_aware()
shots = os.path.join(HERE, "shots")
os.makedirs(shots, exist_ok=True)

pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
if not os.path.exists(pyw):
    pyw = sys.executable
env = os.environ.copy()
env["SHINICHI_CONFIG_DIR"] = os.path.join(shots, ".cfg")

# ---- 启动画面 + 主界面（真实启动流程）
proc = subprocess.Popen([pyw, "app.pyw"], cwd=ROOT, env=env)


def find(pid, title=None, min_w=0):
    for _ in range(60):
        for w in capture.list_windows(include_own=True, allow_untitled=True):
            if w.pid != pid:
                continue
            if title is not None and w.title.strip() != title:
                continue
            if w.w < min_w:
                continue
            return w
        time.sleep(0.2)
    return None


splash = None
for _ in range(40):
    for w in capture.list_windows(include_own=True, allow_untitled=True):
        if w.pid == proc.pid and 900 <= w.w <= 1200 and w.h >= 600 and w.title.strip() != "符卡作业簿":
            splash = w
            break
    if splash:
        break
    time.sleep(0.15)
if splash:
    time.sleep(0.3)
    img = capture.grab(splash, "window").image
    img.save(os.path.join(shots, "01_splash.png"))
    print("01_splash", img.size)

main = find(proc.pid, title="符卡作业簿")
if main:
    time.sleep(1.0)
    img = capture.grab(main, "window").image
    img.save(os.path.join(shots, "02_main.png"))
    print("02_main", img.size)
proc.terminate()
try:
    proc.wait(timeout=5)
except Exception:
    proc.kill()

# ---- 设置面板（进程内打开）
import tkinter as tk

from app import App

root = tk.Tk()
app = App(root)
for _ in range(8):
    root.update()
    time.sleep(0.05)
app._open_settings()
time.sleep(0.8)
root.update()
dlg = None
for _ in range(40):
    for w in capture.list_windows(include_own=True):
        if w.pid == os.getpid() and "补习班设置" in w.title:
            dlg = w
            break
    if dlg:
        break
    time.sleep(0.1)
if dlg:
    img = capture.grab(dlg, "window").image
    img.save(os.path.join(shots, "03_settings.png"))
    print("03_settings", img.size)
try:
    app.hotkeys.stop()
    if app.clip_watcher:
        app.clip_watcher.stop()
except Exception:
    pass
root.destroy()


