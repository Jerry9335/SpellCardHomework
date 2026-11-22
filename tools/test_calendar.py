"""封笔日历测试：月历排版 + 选择返回值 + 截图。"""
import datetime as dt
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import tkinter as tk

from modules import calendar_dialog, capture

assert len(calendar_dialog.month_matrix(2026, 12)) in (4, 5, 6)
weeks = calendar_dialog.month_matrix(2026, 12)
assert weeks[0][0].weekday() == 0, "每周应从周一开始"
assert sum(1 for w in weeks for d in w if d.month == 12) == 31
print("  OK  month_matrix")

capture.make_dpi_aware()
root = tk.Tk()
root.title("日历测试")
root.geometry("900x600+80+80")

result = {}


def click_ok():
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel):
            win = next((x for x in capture.list_windows(include_own=True)
                        if x.title == "封笔日历" and x.pid == os.getpid()), None)
            if win:
                capture.grab(win, "window").image.save(
                    os.path.join(HERE, "shots", "calendar.png"))
                print("  saved calendar.png", win.w, win.h)
            for b in _buttons(w):
                if b.cget("text") == "就这天":
                    b.invoke()
                    return


def _buttons(w):
    out = []
    for c in w.winfo_children():
        if isinstance(c, tk.Button):
            out.append(c)
        out.extend(_buttons(c))
    return out


root.after(800, click_ok)
d = calendar_dialog.pick_date(root, initial=dt.date(2026, 12, 1),
                              title="封笔日历")
result["date"] = d
print("  picked:", d)
assert d == dt.date(2026, 12, 1)
root.destroy()
print("RESULT: PASS")
