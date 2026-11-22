"""更新检查测试（本地 mock，不联网）。"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from modules import update  # noqa: E402

PORT = 9481


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/gitee":
            self._json(200, {
                "tag_name": "v1.0.2", "name": "v1.0.2", "body": "Gitee 说明",
                "created_at": "2026-11-30T10:00:00+08:00",
                "html_url": "https://gitee.com/x/y/releases/tag/v1.0.2",
                "assets": [{"name": "Setup.exe",
                            "browser_download_url": "https://gitee.com/x/y/Setup.exe"}],
            })
        elif p == "/github":
            self._json(200, {
                "tag_name": "v1.0.3", "name": "v1.0.3", "body": "GitHub 说明",
                "published_at": "2026-12-01T10:00:00Z",
                "html_url": "https://github.com/x/y/releases/tag/v1.0.3",
                "assets": [{"name": "Setup.exe",
                            "browser_download_url": "https://github.com/x/y/Setup.exe"}],
            })
        elif p == "/gitee404":
            self._json(404, {"message": "not found"})
        else:
            self._json(404, {"message": "not found"})

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    update.GITEE_API = f"http://127.0.0.1:{PORT}/gitee"
    update.GITHUB_API = f"http://127.0.0.1:{PORT}/github"

    assert update.parse_version("v1.0.10") == (1, 0, 10)
    assert update.is_newer("v1.0.3", "1.0.2")
    assert not update.is_newer("v1.0.2", "1.0.2")
    assert update.is_newer("v1.0.2", "1.0.10") is False
    print("  OK  version compare")

    res = update.check("auto")
    assert res["source"] == "github" and res["version"] == "1.0.3", res
    assert res["download"].endswith("Setup.exe")
    print("  OK  auto -> higher:", res["source"], res["version"])

    update.GITEE_API = f"http://127.0.0.1:{PORT}/gitee404"
    res = update.check("auto")
    assert res["source"] == "github"
    print("  OK  auto fallback github")

    try:
        update.check("gitee")
    except update.UpdateError as e:
        print("  OK  gitee only fails:", e)
    else:
        raise AssertionError("gitee only should fail")

    now = 1_000_000.0
    cfg = {"update_enabled": True, "update_interval_hours": 5,
           "update_last_check": now - 4 * 3600, "update_snooze_until": 0}
    assert not update.due(cfg, now)
    cfg["update_last_check"] = now - 5 * 3600
    assert update.due(cfg, now)
    cfg["update_snooze_until"] = now + 100
    assert not update.due(cfg, now)
    print("  OK  due/interval/snooze")

    import datetime as dt
    ts = update.snooze_until(dt.date(2026, 12, 1))
    assert dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") == "2026-12-01 23:59"
    print("  OK  snooze_until")

    srv.shutdown()
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
