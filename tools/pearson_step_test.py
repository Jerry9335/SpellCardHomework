"""用 App 的真实 _web_step 在你的 Pearson 页面走一步（多小问）。"""
import base64
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

sys.path.insert(0, ROOT)

import tkinter as tk

from app import App
from modules import settings, web

cfg = settings.load()
root = tk.Tk()
root.withdraw()
app = App(root)
import threading
app._web_seen = set()
app._web_ok = 0
app._web_fail = 0
app._web_question = 0
app.web_stop = threading.Event()
app.web_on = True
app._web_ctx = {
    "base": cfg["base_url"],
    "key": cfg["api_key"],
    "model": cfg.get("model") or "deepseek-flash",
    "vision": cfg.get("vision_model") or cfg.get("model") or "deepseek-flash",
    "vision_base": cfg.get("vision_base_url") or cfg["base_url"],
    "vision_key": cfg.get("vision_api_key") or cfg["api_key"],
    "effort": None,
    "extra": {},
    "translate": False,
}

drv = web.WebPlayer(9222, log=print).connect()
st = drv.state()
print("小问:", st.get("part"), "| 框:", [(f["id"], (f.get("label") or "")[:20]) for f in st.get("fields", [])])

print("\n--- 执行 _web_step ---")
ok = app._web_step(drv)
for _ in range(30):
    root.update()
    app._pump()
    time.sleep(0.1)

print("step 返回:", ok)
print("状态:", app.status_var.get())
print("判分:", repr(drv.feedback()))

time.sleep(0.5)
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
