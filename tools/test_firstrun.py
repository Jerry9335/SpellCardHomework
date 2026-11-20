"""首次启动：激活窗口是否出现，点「试用」后能进主界面。"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ["SHINICHI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="sch_first_")
sys.path.insert(0, ROOT)

import tkinter as tk

import app as appmod
from modules import capture, license as lic

capture.make_dpi_aware()
print("启动前状态:", lic.check_access())

root = tk.Tk()
root.withdraw()
state = {"clicked": False}


def click_trial() -> None:
    for top in root.winfo_children():
        if isinstance(top, tk.Toplevel) and "结界许可" in top.title():
            capture.grab(
                next((w for w in capture.list_windows(include_own=True)
                      if w.title == top.title()), None), "window"
            ).image.save(os.path.join(HERE, "shots", "firstrun.png"))
            print("saved firstrun.png")

            def walk(w):
                for c in w.winfo_children():
                    try:
                        if isinstance(c, tk.Button) and c.cget("text") == "先试用 5 天":
                            c.invoke()
                            state["clicked"] = True
                            return True
                    except Exception:
                        pass
                    if walk(c):
                        return True
                return False

            walk(top)
            return


root.after(1200, click_trial)
ok = appmod.show_activation(root, "灵梦：第一次来？可以先用五天，或者拿一张许可咒文来。", allow_trial=True)
print("窗口返回:", ok, "点了试用:", state["clicked"])
print("之后状态:", lic.check_access())
root.destroy()
