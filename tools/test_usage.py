"""用量记账：mock 服务端到端验证 + 账本窗口截图。"""
import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ["SHINICHI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="sch_usage_")
sys.path.insert(0, ROOT)

from modules import llm, usage  # noqa: E402

CAPTURED = {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        CAPTURED.update(body)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        chunks = [
            {"choices": [{"delta": {"content": "答"}}]},
            {"choices": [{"delta": {"content": "案"}}]},
            {"choices": [], "usage": {"prompt_tokens": 1234, "completion_tokens": 56,
                                      "total_tokens": 1290}},
        ]
        for c in chunks:
            self.wfile.write(("data: " + json.dumps(c) + "\n\n").encode())
        self.wfile.write(b"data: [DONE]\n\n")


def main() -> None:
    srv = ThreadingHTTPServer(("127.0.0.1", 9451), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    res = llm.chat_stream("http://127.0.0.1:9451/v1", "k", "deepseek-flash",
                          [{"role": "user", "content": "hi"}])
    print("stream_options sent:", CAPTURED.get("stream_options"))
    print("usage:", res.usage, "elapsed:", round(res.elapsed, 2), "text:", res.text)
    rows = usage.load()
    print("recorded:", rows[-1] if rows else None)
    srv.shutdown()

    # 造一批历史数据用于截图
    import random
    now = time.time()
    models = ["deepseek-flash", "deepseek-v4-pro", "gpt-4o-mini", "qwen-plus"]
    for i in range(60):
        t = now - random.randint(0, 25) * 86400 - random.randint(0, 3600)
        u = {"prompt_tokens": random.randint(800, 9000),
             "completion_tokens": random.randint(100, 2500)}
        row = usage.record(random.choice(models), u, random.uniform(1.2, 8.0))
        row["t"] = int(t)
        with open(usage.path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    import tkinter as tk

    import app as appmod
    from modules import capture

    capture.make_dpi_aware()
    root = tk.Tk()
    a = appmod.App(root)
    root.deiconify()
    for _ in range(10):
        root.update()
        time.sleep(0.05)
    mw = next((x for x in capture.list_windows(include_own=True)
               if x.title.strip() == '符卡作业簿'), None)
    if mw:
        capture.grab(mw, 'window').image.save(os.path.join(HERE, 'shots', 'main_usage.png'))
        print('saved main_usage.png')
    a._open_usage()
    for _ in range(20):
        root.update()
        time.sleep(0.05)
    w = next((x for x in capture.list_windows(include_own=True)
              if "香火钱" in x.title and x.pid == os.getpid()), None)
    if w:
        capture.grab(w, "window").image.save(os.path.join(HERE, "shots", "usage.png"))
        print("saved usage.png", w.w, w.h)
    else:
        print("usage window not found")
    root.destroy()


if __name__ == "__main__":
    os.makedirs(os.path.join(HERE, "shots"), exist_ok=True)
    main()
