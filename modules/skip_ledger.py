"""待人工/review 账本。

P0 规则：自动流程跳过一题前，先把题号、小问、原因写进账本；写失败就
不允许“静默离开”。账本同时给用户一个可追溯的跳过列表，避免最后只看到
一句“收工”却不知道哪题没做。
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

APP_DIR = "SpellCardHomework"
FILENAME = "review.json"
MAX_ITEMS = 500


def ledger_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / APP_DIR / FILENAME


def load() -> list[dict]:
    try:
        raw = ledger_path().read_text(encoding="utf-8")
        data = json.loads(raw)
        return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []
    except Exception:
        return []


def record(qno: int, part: list | tuple | None = None, *,
           reason: str = "", source: str = "auto") -> dict:
    """追加一条跳过记录；返回写入的记录。"""
    try:
        n = int(qno or 0)
    except Exception:
        n = 0
    try:
        p = [int(part[0]), int(part[1])] if isinstance(part, (list, tuple)) and len(part) >= 2 else []
    except Exception:
        p = []
    item = {
        "qno": n,
        "part": p,
        "reason": str(reason or "")[:500],
        "source": str(source or "auto")[:40],
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    items = load()
    items.append(item)
    if len(items) > MAX_ITEMS:
        items = items[-MAX_ITEMS:]
    path = ledger_path()
    tmp = ""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="review_", suffix=".json", dir=str(path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(items, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if tmp:
            try:
                os.unlink(tmp)
            except Exception:
                pass
        raise
    return item


def record_once(qno: int, part: list | tuple | None = None, *,
                reason: str = "", source: str = "auto") -> dict:
    """同一题/同一小问只记一次，避免重试时刷屏。"""
    try:
        n = int(qno or 0)
    except Exception:
        n = 0
    try:
        p = [int(part[0]), int(part[1])] if isinstance(part, (list, tuple)) and len(part) >= 2 else []
    except Exception:
        p = []
    for x in load():
        try:
            if int(x.get("qno") or 0) == n and list(x.get("part") or []) == p:
                return x
        except Exception:
            continue
    return record(n, p, reason=reason, source=source)


def clear() -> None:
    try:
        ledger_path().unlink()
    except FileNotFoundError:
        pass
    except Exception:
        pass


def pending_count() -> int:
    return len(load())
