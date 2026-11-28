"""验证邮箱完整显示 + 点击复制。"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from sch_testenv import enable  # noqa: E402

enable(prefix="sch_mail_")
sys.path.insert(0, ROOT)

import tkinter as tk

import app as appmod
from modules import capture

capture.make_dpi_aware()
root = tk.Tk()
root.withdraw()
state = {"labels": [], "copied": []}


def act() -> None:
    for top in root.winfo_children():
        if not (isinstance(top, tk.Toplevel) and "结界许可" in top.title()):
            continue
        labels = []

        def walk(w):
            for c in w.winfo_children():
                try:
                    if isinstance(c, tk.Label) and "@qq.com" in str(c.cget("text")):
                        labels.append(c)
                except Exception:
                    pass
                walk(c)
        walk(top)
        state["labels"] = [l.cget("text") for l in labels]
        for lb in labels:
            lb.event_generate("<Button-1>")
            root.update()
            try:
                state["copied"].append(root.clipboard_get())
            except Exception as e:
                state["copied"].append(f"ERR {e}")
        w = next((x for x in capture.list_windows(include_own=True)
                  if x.title == top.title()), None)
        if w:
            capture.grab(w, "window").image.save(os.path.join(HERE, "shots", "activation_mail.png"))
            print("saved activation_mail.png")
        top.destroy()
        return


root.after(900, act)
appmod.show_activation(root, "灵梦：第一次来？可以先用五天，或者拿一张许可咒文来。", allow_trial=True)
print("labels:", state["labels"])
print("copied:", state["copied"])
root.destroy()
