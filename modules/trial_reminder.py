"""试用到期提醒：剩 3 天 / 1 天 / 最后几小时，各提醒一次（当天不重复）。"""
from __future__ import annotations

import datetime as dt


def due(state: str, days_left: int, today: dt.date | None = None,
        seen: dict | None = None) -> tuple[str, str] | None:
    """返回 (去重键, 文案)；不该提醒时返回 None。"""
    if state != "trial":
        return None
    today = today or dt.date.today()
    try:
        days_left = int(days_left)
    except Exception:
        return None
    if days_left not in (3, 1, 0):
        return None
    key = f"trial:{today.isoformat()}:{days_left}"
    if seen and str(seen.get("trial") or "") == key:
        return None
    if days_left == 3:
        body = "紫：结界还能撑 3 天。别装没看见哦～"
    elif days_left == 1:
        body = "紫：只剩 1 天了。再不来登记，结界可要散了。"
    else:
        body = "紫：只剩最后几小时了。再不来登记，结界今晚就要散了。"
    return key, body
