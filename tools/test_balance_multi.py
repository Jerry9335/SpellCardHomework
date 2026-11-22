"""多平台余额查询测试（本地 mock，不联网）。"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from modules import balance  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        auth = self.headers.get("Authorization", "")
        if auth == "Bearer bad":
            self._json(401, {"error": {"message": "invalid key"}})
            return
        p = self.path.split("?")[0]
        if p == "/deepseek/v1/user/balance":
            self._json(200, {"is_available": True, "balance_infos": [
                {"currency": "CNY", "total_balance": "8.88",
                 "granted_balance": "0.00", "topped_up_balance": "8.88"}]})
        elif p == "/openai/v1/dashboard/billing/credit_grants":
            self._json(200, {"total_granted": 10.0, "total_used": 2.5, "total_available": 7.5})
        elif p == "/moonshot/v1/users/me/balance":
            self._json(200, {"data": {"available_balance": 12.34, "voucher_balance": 2.0}})
        elif p == "/openrouter/v1/credits":
            self._json(200, {"data": {"total_credits": 20.0, "total_usage": 3.0}})
        elif p == "/modelsonly/v1/models":
            self._json(200, {"data": [{"id": "m1"}, {"id": "m2"}]})
        else:
            self._json(404, {"error": {"message": "not found"}})


def main() -> None:
    srv = ThreadingHTTPServer(("127.0.0.1", 9471), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = 9471
    cases = [
        ("deepseek", f"http://127.0.0.1:{port}/deepseek/v1"),
        ("openai", f"http://127.0.0.1:{port}/openai/v1"),
        ("moonshot", f"http://127.0.0.1:{port}/moonshot/v1"),
        ("openrouter", f"http://127.0.0.1:{port}/openrouter/v1"),
        ("models", f"http://127.0.0.1:{port}/modelsonly/v1"),
    ]
    for name, base in cases:
        res = balance.check(base, "sk-test")
        print(f"{name:10} -> {res['kind']:10} {res['text']}")
        assert res["ok"] is True

    try:
        balance.check(f"http://127.0.0.1:{port}/deepseek/v1", "bad")
    except balance.BalanceError as e:
        print("bad key   ->", e)
    else:
        raise AssertionError("bad key should fail")

    try:
        balance.check("http://127.0.0.1:9471/nope/v1", "sk-test")
    except balance.BalanceError as e:
        print("no api    ->", e)

    srv.shutdown()
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
