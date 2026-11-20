"""验证：点全自动时，浏览器没开就自动启动（不真的开浏览器，用打桩验证）。"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ.setdefault("SHINICHI_CONFIG_DIR", os.path.join(HERE, ".test_config"))
sys.path.insert(0, ROOT)

import tkinter as tk

from app import App

root = tk.Tk()
root.withdraw()
app = App(root)

calls = []
app._launch_answer_browser = lambda: (calls.append(1), True)[1]
app.web_port_var.set(65530)          # 肯定没开的端口
app.autolaunch_var.set(True)
app.key_var.set("test-key")

app.web_var.set(True)
app._toggle_web()
for _ in range(30):
    root.update()
    app._pump()
    time.sleep(0.1)

print("启动调用次数:", len(calls))
print("状态:", app.status_var.get())
print("web_on:", app.web_on)
ok = len(calls) == 1
app.web_stop.set()
app.web_on = False
try:
    app.hotkeys.stop()
    app.clip_watcher.stop()
except Exception:
    pass
root.destroy()
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
