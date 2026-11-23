import base64
import json
import sys

import requests
import websocket

URL = sys.argv[1] if len(sys.argv) > 1 else r"tools\shots\live_after_stop.png"
tabs = requests.get("http://127.0.0.1:9222/json/list", timeout=5).json()
for t in tabs:
    if t.get("type") == "page" and "mylab" in t.get("url", ""):
        ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=10)
        ws.send(json.dumps({"id": 1, "method": "Page.captureScreenshot", "params": {"format": "png"}}))
        r = json.loads(ws.recv())
        with open(URL, "wb") as f:
            f.write(base64.b64decode(r["result"]["data"]))
        print("saved", URL, t["url"])
        ws.close()
        break
else:
    print("no mylab tab")
