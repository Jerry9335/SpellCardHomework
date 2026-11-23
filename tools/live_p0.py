# -*- coding: utf-8 -*-
"""P0 真实页面只读探针：不填、不点、不提交。

用法：
    python tools/live_p0.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules.web import WebPlayer  # noqa: E402


def _brief(st):
    out = {
        "qno": st.get("qno"),
        "part": st.get("part"),
        "hasCheck": st.get("hasCheck"),
        "canCheck": st.get("canCheck"),
        "hasNext": st.get("hasNext"),
        "problemKey": st.get("problemKey"),
        "signature": (st.get("signature") or "")[:180],
        "checkCandidates": st.get("checkCandidates") or [],
        "fields": [
            {k: f.get(k) for k in ("id", "uid", "label", "disabled", "readonly")}
            for f in (st.get("fields") or [])
        ],
        "inputs": [
            {k: f.get(k) for k in ("id", "uid", "label", "disabled", "readonly", "value")}
            for f in (st.get("inputs") or [])
        ],
        "radios": [
            {k: f.get(k) for k in ("id", "uid", "label", "checked", "disabled")}
            for f in (st.get("radios") or [])
        ],
        "checks": [
            {k: f.get(k) for k in ("id", "uid", "label", "checked", "disabled")}
            for f in (st.get("checks") or [])
        ],
        "selects": [
            {k: f.get(k) for k in ("id", "uid", "label", "disabled")}
            for f in (st.get("selects") or [])
        ],
        "dropdowns": [
            {k: f.get(k) for k in ("id", "uid", "label", "disabled", "options")}
            for f in (st.get("dropdowns") or [])
        ],
        "graph": st.get("graph"),
        "text": (st.get("text") or "")[:400],
    }
    return out


def main():
    drv = WebPlayer(port=9222)
    print("connect:", drv.connect())
    st = drv.state() or {}
    print("\n=== state ===")
    print(json.dumps(_brief(st), ensure_ascii=False, indent=2))
    try:
        ps = drv.player_state() or {}
    except Exception as exc:
        ps = {"error": repr(exc)}
    print("\n=== player_state ===")
    print(json.dumps(ps, ensure_ascii=False, indent=2))
    try:
        cs = drv.check_state() or {}
    except Exception as exc:
        cs = {"error": repr(exc)}
    print("\n=== check_state ===")
    print(json.dumps(cs, ensure_ascii=False, indent=2))
    print("\n=== signature stability (read-only, 2s) ===")
    import time
    a = st.get("signature")
    time.sleep(2)
    b = (drv.state() or {}).get("signature")
    print("same:", a == b)


if __name__ == "__main__":
    main()
