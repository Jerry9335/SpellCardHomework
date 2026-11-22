"""横幅时段判断：06–12 白天，12–18 下午，18–06 夜晚。"""
from __future__ import annotations

import datetime as dt

DAY_START = 6
AFTERNOON_START = 12
NIGHT_START = 18

PHASES = ("day", "afternoon", "night")


def phase_for_hour(hour: int) -> str:
    if DAY_START <= hour < AFTERNOON_START:
        return "day"
    if AFTERNOON_START <= hour < NIGHT_START:
        return "afternoon"
    return "night"


def phase_for_now(now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now()
    return phase_for_hour(now.hour)


def next_boundary(now: dt.datetime | None = None) -> dt.datetime:
    """返回下一个时段切换点（06:00 / 12:00 / 18:00 / 次日 06:00）。"""
    now = now or dt.datetime.now()
    today = now.date()
    candidates = [
        dt.datetime.combine(today, dt.time(DAY_START)),
        dt.datetime.combine(today, dt.time(AFTERNOON_START)),
        dt.datetime.combine(today, dt.time(NIGHT_START)),
        dt.datetime.combine(today + dt.timedelta(days=1), dt.time(DAY_START)),
    ]
    for point in candidates:
        if point > now:
            return point
    return candidates[-1]
