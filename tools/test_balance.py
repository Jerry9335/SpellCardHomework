"""验证「查香火钱」：真实走 HTTP、解析余额、错误提示、界面截图。"""
import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ["SHINICHI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="sch_bal_")
sys.path.insert(0, ROOT)


class OKHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.endswith("/user/balance"):
            body = json.dumps({
                "is_available": True,
                "balance_infos": [{
                    "currency": "CNY", "total_balance": "8.88",
                    "granted_balance": "0.00", "topped_up_balance": "8.88",
                }],
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


class ErrHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(401)
        self.end_headers()
        self.wfile.write(b'{"error":{"message":"invalid key"}}')


def main() -> None:
    ok = ThreadingHTTPServer(("127.0.0.1", 9461), OKHandler)
    bad = ThreadingHTTPServer(("127.0.0.1", 9462), ErrHandler)
    threading.Thread(target=ok.serve_forever, daemon=True).start()
    threading.Thread(target=bad.serve_forever, daemon=True).start()

    import tkinter as tk

    import app as appmod
    from modules import capture

    capture.make_dpi_aware()
    root = tk.Tk()
    a = appmod.App(root)
    root.deiconify()

    # 直接验证文案
    data = {"is_available": True, "balance_infos": [{
        "currency": "CNY", "total_balance": "8.88",
        "granted_balance": "0.00", "topped_up_balance": "8.88"}]}
    print("balance text:", a._balance_text(data))
    print("error text:", a._balance_error(Exception("HTTP Error 401: Unauthorized")))

    # 走界面按钮
    a._open_settings()
    for _ in range(10):
        root.update()
        time.sleep(0.05)
    a._dlg_key_var.set("sk-test")
    a._dlg_base_var.set("http://127.0.0.1:9461/v1")

    def find_btn(widget):
        for w in widget.winfo_children():
            try:
                if isinstance(w, __import__("tkinter.ttk", fromlist=["Button"]).Button) and w.cget("text") == "查香火钱":
                    return w
            except Exception:
                pass
            r = find_btn(w)
            if r is not None:
                return r
        return None

    btn = None
    for top in root.winfo_children():
        if isinstance(top, tk.Toplevel) and "设置" in top.title():
            btn = find_btn(top)
            break
    print("button found:", btn is not None)
    if btn:
        btn.invoke()
        for _ in range(40):
            root.update()
            time.sleep(0.05)
    w = next((x for x in capture.list_windows(include_own=True)
              if "设置" in x.title and x.pid == os.getpid()), None)
    if w:
        capture.grab(w, "window").image.save(os.path.join(HERE, "shots", "balance.png"))
        print("saved balance.png", w.w, w.h)

    ok.shutdown()
    bad.shutdown()
    root.destroy()


if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "shots"), exist_ok=True)
    main()
