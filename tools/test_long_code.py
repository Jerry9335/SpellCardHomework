"""看一下 132 字符的激活码贴进输入框的样子。"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ["SHINICHI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="sch_long_")
sys.path.insert(0, ROOT)

import tkinter as tk

import app as appmod
from modules import capture, license as lic, license_sign as signer

capture.make_dpi_aware()
code = signer.make_code(lic.machine_code())
print("code len:", len(code))

root = tk.Tk()
root.withdraw()


def fill() -> None:
    for top in root.winfo_children():
        if isinstance(top, tk.Toplevel) and "结界许可" in top.title():
            def walk(w):
                for c in w.winfo_children():
                    try:
                        if isinstance(c, tk.Entry):
                            c.insert(0, code)
                    except Exception:
                        pass
                    walk(c)
            walk(top)
            for _ in range(8):
                root.update()
            w = next((x for x in capture.list_windows(include_own=True)
                      if x.title == top.title()), None)
            if w:
                capture.grab(w, "window").image.save(os.path.join(HERE, "shots", "long_code.png"))
                print("saved long_code.png")
            top.destroy()
            return


root.after(900, fill)
appmod.show_activation(root, "灵梦：把收到的咒文贴进来吧。", allow_trial=False)
root.destroy()
