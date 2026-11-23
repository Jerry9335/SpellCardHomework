"""只读探针：连接 9222，打印当前 Pearson 小问的结构化状态。"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import web  # noqa: E402


def main() -> int:
    drv = web.WebPlayer(9222, log=lambda m: None)
    drv.connect()
    st = drv.state() or {}
    out = {
        "qno": st.get("qno"),
        "part": st.get("part"),
        "questions": st.get("questions"),
        "hasCheck": st.get("hasCheck"),
        "canCheck": st.get("canCheck"),
        "hasNext": st.get("hasNext"),
        "inDialog": st.get("inDialog"),
        "graph": st.get("graph"),
        "fields": [{"id": f.get("id"), "label": f.get("label")}
                   for f in (st.get("fields") or [])],
        "inputs": [{"id": f.get("id"), "label": f.get("label")}
                   for f in (st.get("inputs") or [])],
        "radios": [{"id": f.get("id"), "label": f.get("label")}
                   for f in (st.get("radios") or [])],
        "checks": [{"id": f.get("id"), "label": f.get("label")}
                   for f in (st.get("checks") or [])],
        "dropdowns": [{"id": f.get("id"), "label": f.get("label")}
                      for f in (st.get("dropdowns") or [])],
        "selects": [{"id": f.get("id"), "label": f.get("label")}
                    for f in (st.get("selects") or [])],
        "text": (st.get("text") or "")[:4000],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    drv.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
