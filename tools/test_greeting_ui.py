"""问候语 UI 测试：头像、名字、时段切换、宽度。"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import tkinter as tk

import app as appmod
from modules import capture, greetings

capture.make_dpi_aware()
root = tk.Tk()
a = appmod.App(root)
root.deiconify()
for _ in range(12):
    root.update()
    time.sleep(0.05)

text = a.greet_var.get()
print("用户名:", a._user_display)
print("问候:", text)
assert a._user_display
assert a._user_display in text, text
assert "{name}" not in text
assert a.greet_avatar.image is not None
assert len(a._greet_avatars) == 14, len(a._greet_avatars)
assert "：" in text
print("宽度 bar=%d frame=%d label=%d req=%d" % (
    a.greet_frame.master.winfo_width(),
    a.greet_frame.winfo_width(),
    a.greet_label.winfo_width(),
    a.greet_label.winfo_reqwidth(),
))

for slot, name in (("morning", "morning"), ("afternoon", "afternoon"),
                   ("evening", "evening"), ("late", "late")):
    orig = greetings.slot_for_now
    greetings.slot_for_now = lambda s=slot: s
    try:
        a._refresh_greeting(slot)
        for _ in range(8):
            root.update()
            time.sleep(0.03)
        print(slot, "->", a.greet_var.get())
        assert a.greet_var.get()
        assert a._user_display in a.greet_var.get()
        assert a._greet_tooltip.text
    finally:
        greetings.slot_for_now = orig

win = next((w for w in capture.list_windows(include_own=True)
            if w.pid == os.getpid() and "符卡作业簿" in w.title), None)
if win:
    capture.grab(win, "window").image.save(os.path.join(HERE, "shots", "greeting.png"))
    print("saved greeting.png")

root.destroy()
print("RESULT: PASS")
