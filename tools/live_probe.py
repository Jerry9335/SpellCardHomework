"""连接 9222 调试端口，打印当前页面标题/URL/可见文字，用于实测定位。

不修改页面、不提交答案；只是只读探针。
"""
from __future__ import annotations

import json
import sys
import urllib.request

import websocket


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9222
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as r:
        targets = json.loads(r.read().decode("utf-8"))
    pages = [t for t in targets if t.get("type") == "page"]
    if not pages:
        print("NO_PAGE")
        return 2
    for i, t in enumerate(pages):
        print(f"[{i}] {t.get('title')} | {t.get('url')}")
    # 优先 Pearson / kysu 页面
    pick = next((t for t in pages if "pearson" in (t.get("url") or "").lower()), None)
    pick = pick or next((t for t in pages if "kysu" in (t.get("url") or "").lower()), pages[0])
    ws = websocket.create_connection(pick["webSocketDebuggerUrl"], timeout=10)
    try:
        ws.send(json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {
                "expression": "({title:document.title,url:location.href,text:(document.body?document.body.innerText:'').slice(0,1600)})",
                "returnByValue": True,
            },
        }))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                val = (msg.get("result") or {}).get("result", {}).get("value") or {}
                print("TITLE:", val.get("title"))
                print("URL:", val.get("url"))
                print("TEXT:")
                print(val.get("text") or "")
                return 0
    finally:
        try:
            ws.close()
        except Exception:
            pass
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
