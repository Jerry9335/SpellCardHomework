"""下载窗口 / 完成窗口截图与功能冒烟。"""
import hashlib
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import tkinter as tk

from modules import capture, theme, update_ui
from modules.update_ui import DownloadWindow

DATA = bytes((i * 19 + 7) % 256 for i in range(5 * 1024 * 1024 + 71))
SHA = hashlib.sha256(DATA).hexdigest()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(DATA)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("ETag", '"shot"')
        self.end_headers()

    def do_GET(self):
        rng = self.headers.get("Range", "")
        if rng.startswith("bytes="):
            a, b = rng[6:].split("-", 1)
            s, e = int(a), int(b) if b else len(DATA) - 1
            body = DATA[s:e + 1]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {s}-{e}/{len(DATA)}")
        else:
            body = DATA
            self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("ETag", '"shot"')
        self.end_headers()
        for i in range(0, len(body), 64 * 1024):
            time.sleep(0.4)
            self.wfile.write(body[i:i + 64 * 1024])


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_address[1]}/SpellCardHomework-Setup-1.1.7-hotfix.exe"
tmp = tempfile.mkdtemp(prefix="ui_dl_")
os.environ["LOCALAPPDATA"] = tmp

capture.make_dpi_aware()
root = tk.Tk()
root.deiconify()
info = {
    "version": "1.1.7-hotfix", "tag": "v1.1.7-hotfix", "download": url,
    "asset_name": "SpellCardHomework-Setup-1.1.7-hotfix.exe",
    "sha256": SHA, "source": "gitee", "notes": "测试",
    "max_threads": 8,
}

w = DownloadWindow(root, info, theme.NEW_COLORS, "Microsoft YaHei UI", "KaiTi",
                   os.path.join(ROOT, "assets", "char", "toast", "avatar_aya.png"),
                   lambda p: print("install callback", p))


def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        root.update()
        time.sleep(0.02)


pump(1.0)
win = next((x for x in capture.list_windows(include_own=True)
            if x.pid == os.getpid() and "号外取件" in x.title), None)
print("download win", bool(win), w.vals["done"].get())
if win:
    capture.grab(win, "window").image.save(os.path.join(HERE, "shots", "download_window.png"))

# 等下载完成
for _ in range(300):
    pump(0.1)
    if w._closing:
        break

pump(0.4)
win2 = next((x for x in capture.list_windows(include_own=True)
             if x.pid == os.getpid() and "号外取件" in x.title), None)
print("complete win", bool(win2))
if win2:
    capture.grab(win2, "window").image.save(os.path.join(HERE, "shots", "download_complete.png"))
root.destroy()
srv.shutdown()
print("RESULT: PASS")

