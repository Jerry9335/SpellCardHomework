"""把 palette_console_probe.js 用带 CORS 的本地 HTTP 服务暴露出来。

用途：在 Pearson 页面（https）的控制台里手打一行
    fetch('http://127.0.0.1:8901/p.js').then(r=>r.text()).then(t=>eval(t))
即可加载并执行脚本，避免粘贴/长文本输入。
"""
from __future__ import annotations

import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "palette_console_probe.js")
PORT = int(os.environ.get("PALETTE_PORT", "8901"))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] not in ("/p.js", "/"):
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = open(SCRIPT, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", "text/javascript; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"serving {SCRIPT} at http://127.0.0.1:{PORT}/p.js")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
