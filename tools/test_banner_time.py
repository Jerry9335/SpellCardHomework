"""横幅时段纯逻辑测试。"""
import datetime as dt
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from modules import banner_time as bt  # noqa: E402


def main() -> None:
    expect = {0: "night", 5: "night", 6: "day", 11: "day",
              12: "afternoon", 17: "afternoon", 18: "night", 23: "night"}
    for hour, phase in expect.items():
        assert bt.phase_for_hour(hour) == phase, (hour, phase)
        print(f"  OK  {hour:02d}:00 -> {phase}")

    cases = [
        ("05:59:59", "06:00"),
        ("06:00:00", "12:00"),
        ("11:59:00", "12:00"),
        ("12:00:00", "18:00"),
        ("17:59:00", "18:00"),
        ("18:00:00", "06:00"),
        ("23:59:00", "06:00"),
        ("00:00:00", "06:00"),
    ]
    for t, want in cases:
        now = dt.datetime.fromisoformat("2026-11-21T" + t)
        got = bt.next_boundary(now).strftime("%H:%M")
        assert got == want, (t, got, want)
        print(f"  OK  {t} -> next {got}")

    print("RESULT: PASS")


if __name__ == "__main__":
    main()
