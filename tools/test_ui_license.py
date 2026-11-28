"""检查：主界面（试用提示）、设置里的授权状态、关于、结界许可窗口。"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from sch_testenv import enable  # noqa: E402

enable(prefix="sch_ui_")
sys.path.insert(0, ROOT)

import tkinter as tk

import app as appmod
from modules import capture, license as lic, settings

capture.make_dpi_aware()
shots = os.path.join(HERE, "shots")
os.makedirs(shots, exist_ok=True)
root = tk.Tk()
a = appmod.App(root)
root.deiconify()
root.lift()
for _ in range(10):
    root.update()
    time.sleep(0.05)


def grab(title_part: str, name: str) -> None:
    for _ in range(20):
        w = next((x for x in capture.list_windows(include_own=True)
                  if title_part in x.title and x.pid == os.getpid()), None)
        if w:
            capture.grab(w, "window").image.save(os.path.join(shots, name))
            print("saved", name, w.w, w.h)
            return
        time.sleep(0.1)
    print("window not found:", title_part)


grab("符卡作业簿", "main_trial.png")

# 设置
a._open_settings()
time.sleep(0.6)
root.update()
grab("补习班设置", "settings_auth.png")
for top in root.winfo_children():
    if isinstance(top, tk.Toplevel):
        top.destroy()
time.sleep(0.3)

# 关于
a._about_app()
time.sleep(0.6)
root.update()
grab("关于程序", "about_ver.png")
for top in root.winfo_children():
    if isinstance(top, tk.Toplevel):
        top.destroy()
time.sleep(0.3)

# 结界许可
def snap_and_close() -> None:
    grab("结界许可", "activation_touhou.png")
    for top in root.winfo_children():
        if isinstance(top, tk.Toplevel):
            top.destroy()


root.after(1200, snap_and_close)
ok = appmod.show_activation(root, "灵梦：五天试用到头了，先拿一张许可来吧。")
print("activation returned:", ok)
print("trial status:", lic.check_access(update=False))
root.destroy()
