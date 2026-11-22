"""下载模块测试：Range 多分片、暂停/继续、SHA256。"""
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
from modules.update_download import DownloadJob  # noqa: E402

DATA = bytes((i * 37 + 11) % 256 for i in range(6 * 1024 * 1024 + 12345))
SHA = hashlib.sha256(DATA).hexdigest()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Length", str(len(DATA)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("ETag", '"test-etag"')
        self.end_headers()

    def do_GET(self):
        rng = self.headers.get("Range")
        if rng and rng.startswith("bytes="):
            a, b = rng[6:].split("-", 1)
            start = int(a)
            end = int(b) if b else len(DATA) - 1
            end = min(end, len(DATA) - 1)
            body = DATA[start:end + 1]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(DATA)}")
        else:
            body = DATA
            self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("ETag", '"test-etag"')
        self.end_headers()
        for i in range(0, len(body), 64 * 1024):
            time.sleep(0.02)
            self.wfile.write(body[i:i + 64 * 1024])


srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_address[1]}/setup.exe"
tmp = tempfile.mkdtemp(prefix="dl_")
dest = os.path.join(tmp, "setup.exe")

job = DownloadJob(url, dest, SHA, max_threads=4)
job.start()
paused = False
seen_threads = 0
deadline = time.time() + 30
while time.time() < deadline:
    try:
        ev = job.events.get(timeout=0.2)
    except Exception:
        continue
    if ev["type"] == "meta":
        seen_threads = ev["threads"]
        print("meta", ev["total"], "threads", seen_threads)
    elif ev["type"] == "progress" and not paused and ev["done"] > 1 * 1024 * 1024:
        print("pause at", ev["done"])
        job.pause()
        paused = True
    elif ev["type"] == "paused":
        print("paused")
        time.sleep(0.3)
        job.resume()
    elif ev["type"] == "done":
        print("done", ev["verified"], ev["sha256"])
        assert ev["verified"]
        assert os.path.getsize(dest) == len(DATA)
        with open(dest, "rb") as f:
            assert hashlib.sha256(f.read()).hexdigest() == SHA
        break
    elif ev["type"] == "error":
        raise AssertionError(ev)
else:
    raise AssertionError("download timeout")
assert seen_threads >= 2, seen_threads

# 校验失败必须删除坏包并报错
dest2 = os.path.join(tmp, "bad.exe")
bad = DownloadJob(url, dest2, "0" * 64, max_threads=2)
bad.start()
err = None
end = time.time() + 20
while time.time() < end:
    try:
        ev = bad.events.get(timeout=0.2)
    except Exception:
        continue
    if ev["type"] == "error":
        err = ev.get("code")
        break
print("wrong sha error:", err)
assert err == "sha256"
assert not os.path.exists(dest2)

print("RESULT: PASS")
try:
    srv.shutdown()
    srv.server_close()
except Exception:
    pass
