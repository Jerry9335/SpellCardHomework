"""像用户一样点「全自动」，在真实 Pearson 页面上跑一段，观察状态并截图。"""
import base64
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

sys.path.insert(0, ROOT)

import tkinter as tk

from app import App
from modules import settings

cfg = settings.load()
root = tk.Tk()
root.withdraw()
app = App(root)
app.base_var.set(cfg["base_url"])
app.key_var.set(cfg["api_key"])
app.model_var.set(cfg.get("model") or "deepseek-flash")
app.web_port_var.set(9222)

app.trans_var.set(False)

seen = []
app.web_var.set(True)
app._toggle_web()

deadline = time.time() + 35
while time.time() < deadline:
    root.update()
    app._pump()
    s = app.status_var.get()
    if not seen or seen[-1] != s:
        seen.append(s)
        print(f"[{time.strftime('%H:%M:%S')}] {s}")
    time.sleep(0.2)

app.web_stop.set()
time.sleep(0.5)
root.update()

from modules import web

drv = web.WebPlayer(9222, log=lambda *a: None).connect()
st = drv.state()
print("\n小问:", st.get("part"), "| 框:", [(f["id"], (f.get("label") or "")[:24]) for f in st.get("fields", [])])
print("判分:", repr(drv.feedback()))
r = drv.ws.call("Page.captureScreenshot", {"format": "png"})
shot = os.path.join(ROOT, "docs", "pearson_test.png")
open(shot, "wb").write(base64.b64decode(r["data"]))
print("截图:", shot)
drv.close()

try:
    app.hotkeys.stop()
    app.clip_watcher.stop()
except Exception:
    pass
root.destroy()



