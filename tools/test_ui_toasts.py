# -*- coding: utf-8 -*-
"""UI 行为回归：手动启动、结界开/关 Toast、退治开始/停止 Toast。"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ.setdefault("SHINICHI_CONFIG_DIR", os.path.join(HERE, ".test_config_toast"))
sys.path.insert(0, ROOT)

import tkinter as tk

from app import App

root = tk.Tk()
root.withdraw()
app = App(root)

events = []
app._notify = lambda *args, **kwargs: events.append((args, kwargs))

# 1) 启动时绝不能自动进入退治：_autostart_web 已被删除。
assert not hasattr(app, "_autostart_web"), "不应再存在自动启动入口"
assert app.web_on is False
print("no autostart OK")

# 2) 点「张开结界」：端口起来后弹“已张开”。
state = {"open": False}
app.web_port_var.set(65530)
app._web_port_open = lambda port: bool(state["open"])
app._launch_answer_browser = lambda: True
app._close_answer_browser = lambda port: (state.__setitem__("open", False) or True)
app._barrier_last = False
app.browser_var.set(True)
app._toggle_browser()
assert app._barrier_launching is True
state["open"] = True
app._watch_barrier()
assert app.browser_var.get() is True
assert any("结界已张开" in a[2] for a, _ in events), events
print("open barrier toast OK")

# 3) 手动关浏览器 / 点关闭结界：弹“已关闭”。
events.clear()
app.browser_var.set(False)
app._toggle_browser()
app._watch_barrier()
assert app.browser_var.get() is False
assert any("结界已关闭" in a[2] for a, _ in events), events
print("close barrier toast OK")

# 4) 开始退治 / 停止退治：各弹一条。
events.clear()
app.key_var.set("test-key")
app._ctx = lambda: {"base": "http://example.invalid", "key": "k", "model": "m",
                    "vision": "", "vision_base": "", "vision_key": ""}
app._web_port_open = lambda port: True
app._web_loop = lambda: None
app.web_var.set(True)
app._toggle_web()
assert any("退治开始" in a[2] for a, _ in events), events
events.clear()
app.web_var.set(False)
app._toggle_web()
assert any("退治已停止" in a[2] for a, _ in events), events
print("auto start/stop toast OK")

app.web_stop.set()
app.web_on = False
try:
    app.hotkeys.stop()
    app.clip_watcher.stop()
except Exception:
    pass
root.destroy()
print("RESULT: PASS")
