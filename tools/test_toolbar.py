"""工具栏方案 A 测试：抽符常驻 + 其他术式展开 + 标题状态。"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import tkinter as tk

import app as appmod
from modules import capture

capture.make_dpi_aware()
root = tk.Tk()
a = appmod.App(root)
root.deiconify()
for _ in range(12):
    root.update()
    time.sleep(0.05)

assert a._actions_open is False
assert a.actions_row.winfo_manager() == ""
assert a.greet_avatar.image is not None
assert a.greet_avatar.image.width() == 44
print("收起 OK；头像", a.greet_avatar.image.width(), "px")
print("问候:", a.greet_var.get())
print("标题:", root.title())

win = next((w for w in capture.list_windows(include_own=True)
            if w.pid == os.getpid() and "符卡作业簿" in w.title), None)
if win:
    capture.grab(win, "window").image.save(os.path.join(HERE, "shots", "toolbar_collapsed.png"))

a.btn_actions.invoke()
for _ in range(10):
    root.update()
    time.sleep(0.04)
assert a._actions_open is True
assert a.actions_row.winfo_manager() == "pack"
# 展开后第二行必须占住自己的位置：目标栏在三行下方，面板再往下
assert a.row2.winfo_y() >= a.actions_row.winfo_y() + a.actions_row.winfo_height()
assert a._theme_panel_frames[0].winfo_y() >= a.row2.winfo_y() + a.row2.winfo_height()
print("展开 OK:", a.btn_actions.cget("text"),
      "row2", a.row2.winfo_y(), "panel", a._theme_panel_frames[0].winfo_y())
if win:
    capture.grab(win, "window").image.save(os.path.join(HERE, "shots", "toolbar_expanded.png"))

# 模拟执行动作后自动收起
a._run_action(lambda: None)
root.update()
assert a._actions_open is False
assert a.actions_row.winfo_manager() == ""
print("动作后自动收起 OK")

# 标题状态
a.auto_var.set(True)
a.browser_var.set(True)
a.web_var.set(True)
a._refresh_action_status()
print("标题状态:", root.title())
assert "自动监视" in root.title() and "结界" in root.title() and "退治中" in root.title()
a.auto_var.set(False)
a.browser_var.set(False)
a.web_var.set(False)
a._refresh_action_status()
assert root.title() == appmod.APP_TITLE
print("标题恢复 OK")

# 窄窗口隐藏问候，宽窗口显示
root.geometry("1020x660")
for _ in range(10):
    root.update()
    time.sleep(0.04)
print("1020 问候可见:", bool(a.greet_frame.winfo_manager()))
root.geometry("1380x880")
for _ in range(10):
    root.update()
    time.sleep(0.04)
print("1380 问候可见:", bool(a.greet_frame.winfo_manager()))

root.destroy()
print("RESULT: PASS")
