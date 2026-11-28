"""P0 regression: update sidecar SHA, persisted web settings, graph parser, fullwidth colon."""
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ.setdefault("SHINICHI_CONFIG_DIR", os.path.join(tempfile.gettempdir(), "sc_p0_test"))
sys.path.insert(0, ROOT)

from modules import prompts, settings, update  # noqa: E402

SHA = "a" * 64


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_a):
        pass

    def do_GET(self):
        body = (SHA + "  SpellCardHomework-Setup-1.1.7.exe\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_address[1]}/setup.exe.sha256"

# 1) USER_AGENT / .sha256 sidecar path
sha = update._find_sha256(
    [{"name": "setup.exe.sha256", "browser_download_url": url}],
    {"name": "SpellCardHomework-Setup-1.1.7.exe", "digest": ""}, "", 3.0)
assert sha == SHA, sha
print("sha sidecar OK")

# 2) persisted web settings
vals = {"web_autostart": True, "web_start_url": "https://example.test",
        "web_continue_on_wrong": False}
cfg = settings.load()
cfg.update(vals)
settings.save(cfg)
cfg2 = settings.load()
for k, v in vals.items():
    assert cfg2.get(k) == v, (k, cfg2.get(k), v)
print("web settings persist OK")

# 3) fullwidth colon
spec = prompts.parse_web_answer("CHOICE：B\nVALUE：42\nDROPDOWN：1；2")
assert spec["choices"] == ["B"] and spec["value"] == "42" and spec["drops"] == [1, 2]
print("fullwidth colon OK")

# 4) quadratic parser, including missing bx / negative a / word form
import tkinter as tk  # noqa: E402
from app import App  # noqa: E402

root = tk.Tk()
root.withdraw()
app = App(root)
graph = {"xmin": -6, "xmax": 6, "ymin": -20, "ymax": 10}
cases = {
    "y=-x^2+4": (-1.0, 0.0, 4.0),
    "y=x^2-4": (1.0, 0.0, -4.0),
    "y=x squared minus 4": (1.0, 0.0, -4.0),
    "-5x^2-20x-15": (-5.0, -20.0, -15.0),
}
for expr, want in cases.items():
    got = app._web_poly(expr)
    assert got == want, (expr, got, want)
assert app._web_quadratic_points("Graph y=-x^2+4.", graph)
assert app._web_quadratic_points("Graph y=x squared minus 4.", graph)
print("graph parser OK")
root.destroy()
srv.shutdown()
print("RESULT: PASS")

