"""截图：设置里的香火钱行，查询后长文本是否完整显示。"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import tkinter as tk
import tkinter.ttk as ttk

import app as appmod
from modules import capture


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = json.dumps({"is_available": True, "balance_infos": [{
            "currency": "CNY", "total_balance": "1234.56",
            "granted_balance": "34.56", "topped_up_balance": "1200.00"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


srv = ThreadingHTTPServer(("127.0.0.1", 9472), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()

capture.make_dpi_aware()
root = tk.Tk()
a = appmod.App(root)
root.deiconify()
for _ in range(10):
    root.update()
    time.sleep(0.05)

a._open_settings()
for _ in range(10):
    root.update()
    time.sleep(0.05)

a._dlg_base_var.set("http://127.0.0.1:9472/v1")
a._dlg_key_var.set("sk-test")


def find_btn(w):
    for c in w.winfo_children():
        try:
            if isinstance(c, ttk.Button) and c.cget("text") == "查香火钱":
                return c
        except Exception:
            pass
        r = find_btn(c)
        if r is not None:
            return r
    return None


btn = None
for top in root.winfo_children():
    if isinstance(top, tk.Toplevel) and "设置" in top.title():
        btn = find_btn(top)
        break
print("button:", bool(btn))
if btn:
    btn.invoke()
    for _ in range(30):
        root.update()
        time.sleep(0.1)

w = next((x for x in capture.list_windows(include_own=True)
          if "设置" in x.title and x.pid == os.getpid()), None)
if w:
    capture.grab(w, "window").image.save(os.path.join(HERE, "shots", "balance_multi.png"))
    print("saved balance_multi.png", w.w, w.h)
srv.shutdown()
root.destroy()
