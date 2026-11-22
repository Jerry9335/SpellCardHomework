"""问候语数据/时段/去重测试。"""
import datetime as dt
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from modules import greetings as g  # noqa: E402


def main() -> None:
    assert len(g.ENTRIES) == 60, len(g.ENTRIES)
    assert g.ROTATE_SECONDS == 60, g.ROTATE_SECONDS
    assert g.all_avatars() == {
        "reimu", "marisa", "aya", "sakuya", "keine",
        "patchouli", "remilia", "flandre", "yukari",
    }
    for e in g.ENTRIES:
        assert "{name}" in e["text"], e
    print("  OK  60 条 / 9 个角色 / 都带 {name}")

    expect = {0: g.LATE, 5: g.LATE, 6: g.MORNING, 11: g.MORNING,
              12: g.AFTERNOON, 17: g.AFTERNOON, 18: g.EVENING,
              22: g.EVENING, 23: g.LATE}
    for hour, slot in expect.items():
        assert g.slot_for_hour(hour) == slot, (hour, slot)
    print("  OK  时段边界 06 / 12 / 18 / 23")

    cases = [
        ("05:59:59", "06:00"),
        ("06:00:00", "12:00"),
        ("11:59:00", "12:00"),
        ("12:00:00", "18:00"),
        ("17:59:00", "18:00"),
        ("18:00:00", "23:00"),
        ("22:59:00", "23:00"),
        ("23:00:00", "06:00"),
        ("00:00:00", "06:00"),
    ]
    for t, want in cases:
        now = dt.datetime.fromisoformat("2026-11-21T" + t)
        got = g.next_boundary(now).strftime("%H:%M")
        assert got == want, (t, got, want)
    print("  OK  下一时段边界")

    bad = {
        g.MORNING: ("下午好", "晚上好", "凌晨", "深夜"),
        g.AFTERNOON: ("早上好", "晚上好", "凌晨", "深夜"),
        g.EVENING: ("早上好", "下午好", "凌晨", "深夜"),
        g.LATE: ("早上好", "下午好", "晚上好"),
        "any": ("早上好", "下午好", "晚上好", "凌晨", "深夜"),
    }
    for slot, words in bad.items():
        for e in g.ENTRIES:
            if e["slot"] == slot:
                assert not any(w in e["text"] for w in words), e
    print("  OK  时段文案没有串词")

    # 连续抽取：最近 10 条去重 + 不连续同一角色
    rng = random.Random(20261121)
    recent = []
    last = ""
    slides = []
    for _ in range(80):
        e = g.pick_entry(g.EVENING, recent, last, rng)
        assert e["id"] not in recent, e
        assert e["avatar"] != last, (last, e)
        recent = (recent + [e["id"]])[-10:]
        last = e["avatar"]
        slides.append(e["id"])
    assert len(set(slides)) >= 10
    print("  OK  最近 10 条不重复 / 不连续同一角色")

    print("RESULT: PASS")


if __name__ == "__main__":
    main()
