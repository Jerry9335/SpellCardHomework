"""P0 应用层回归：唯一 Check、陈旧 player_state、跳过账本、阻塞题恢复。"""
import os
import shutil
import sys
import tempfile
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault(
    "SHINICHI_CONFIG_DIR", os.path.join(tempfile.gettempdir(), "sc_pearson_p0_app"))
sys.path.insert(0, os.path.dirname(HERE))

from app import App  # noqa: E402
from modules import skip_ledger  # noqa: E402


class Driver:
    def __init__(self, st, *, player=None, completion=None, check=None):
        self.st = dict(st)
        self.player = dict(player or {"ok": False})
        self.completion = dict(completion or {"kind": "none"})
        self.check = dict(check or {"count": 1, "enabled": 1, "ok": True})
        self.clicks = []
        self.clicked_unique = 0
        self.present = set()
        for key in ("fields", "inputs", "radios", "checks", "selects", "dropdowns"):
            for c in (self.st.get(key) or []):
                if isinstance(c, dict) and c.get("uid"):
                    self.present.add(str(c["uid"]))

    def state(self):
        return dict(self.st)

    def field_present(self, uid):
        return str(uid) in self.present

    def player_state(self):
        return dict(self.player)

    def completion_state(self):
        return dict(self.completion)

    def check_state(self):
        return dict(self.check)

    def click_check_unique(self):
        self.clicked_unique += 1
        return "ok"

    def click_text(self, pattern):
        self.clicks.append(pattern)
        return "ok"

    def click_text_native(self, pattern):
        self.clicks.append(("native", pattern))
        return "ok"

    def feedback(self):
        return ""

    def dismiss_feedback(self):
        return "ok"

    def goto_question(self, n):
        self.st["qno"] = int(n)
        self.st["questions"] = [
            dict(q, selected=(int(q["n"]) == int(n)))
            for q in self.st.get("questions", [])
        ]
        return "ok"


def main() -> None:
    root = tk.Tk()
    root.withdraw()
    app = App(root)
    statuses = []
    app._web_status = lambda text, level="info": statuses.append((level, text))
    for k, v in {
        "_web_round_failed": False,
        "_web_blocked": [],
        "_web_all_done": False,
        "_web_partial_done": set(),
        "_web_current_key": "",
    }.items():
        setattr(app, k, v)

    # 1) 陈旧 player_state：上一题 _correctness=correct，但当前没有反馈，
    #    不能因此拒绝点击新题的 Check。
    stale = Driver(
        {"qno": 3, "part": [1, 1], "text": "q3", "checkCandidates": []},
        player={"ok": True, "correctness": "correct",
                "feedbackOpen": False, "resultPosted": 0},
        completion={"kind": "none"},
        check={"count": 1, "enabled": 1, "ok": True},
    )
    assert app._web_click_check(stale) is True, "stale player state blocked Check"
    assert stale.clicked_unique == 1

    # 2) 多个 Check：绝不点，标记失败。
    multi = Driver(
        {"qno": 3, "part": [1, 1], "text": "q3"},
        player={"ok": False},
        completion={"kind": "none"},
        check={"count": 2, "enabled": 2, "ok": False},
    )
    app._web_round_failed = False
    assert app._web_click_check(multi) is False
    assert multi.clicked_unique == 0
    assert app._web_round_failed is True
    assert any("多个 Check" in t for _, t in statuses), statuses

    # 3) 反馈：没有新反馈时，陈旧 player_state 不能被当作本题正确。
    stale_fb = Driver(
        {"qno": 4, "part": [1, 1], "text": "q4"},
        player={"ok": True, "correctness": "correct",
                "feedbackOpen": False, "resultPosted": 0},
        completion={"kind": "none"},
    )
    assert app._web_feedback(stale_fb, timeout=0.2) == ""
    fresh_fb = Driver(
        {"qno": 4, "part": [1, 1], "text": "q4"},
        player={"ok": True, "correctness": "correct",
                "feedbackOpen": True, "resultPosted": 0},
        completion={"kind": "none"},
    )
    assert app._web_feedback(fresh_fb, timeout=0.5) == "correct"

    # 4) 填写前快照闸门：签名变化或字段 UID 消失都必须拒绝填。
    snap_st = {"qno": 5, "part": [1, 2], "signature": "sig-a",
               "fields": [{"uid": "u1", "id": "f1"}],
               "radios": [{"uid": "u2", "id": "r1"}]}
    snap = Driver(snap_st)
    assert app._web_snapshot_intact(snap, snap_st) is True
    snap.st = dict(snap.st, signature="sig-b")
    assert app._web_snapshot_intact(snap, snap_st) is False
    snap2 = Driver(snap_st)
    snap2.present.discard("u1")
    assert app._web_snapshot_intact(snap2, snap_st) is False
    print("snapshot gate OK")

    # 4b) 离开警告：默认只点 No；只有允许（已入账/已判分）才点 Yes。
    class LeaveDriver(Driver):
        def __init__(self):
            super().__init__({"qno": 6, "part": [1, 2], "text": "q6"})
            self.leave_clicks = []

        def leave_prompt(self):
            return True

        def leave_state(self):
            return {"visible": True, "kind": "unchecked",
                    "yes_count": 1, "no_count": 1}

        def click_leave(self, choice="no"):
            self.leave_clicks.append(choice)
            return "ok"

    ld = LeaveDriver()
    assert app._web_leave_if_prompt(ld, allow=False) is False
    assert ld.leave_clicks == ["no"], ld.leave_clicks
    ld2 = LeaveDriver()
    assert app._web_leave_if_prompt(ld2, allow=True) is True
    assert ld2.leave_clicks == ["yes"], ld2.leave_clicks
    print("leave guard OK")

    # 4c) inventory 不完整时 _web_step 不盲答，必须走 _web_skip。
    skipped = []
    orig_skip = app._web_skip
    app._web_skip = lambda drv, key: skipped.append(key) or False
    inc = Driver({"qno": 7, "part": [1, 2], "text": "q7",
                  "incomplete": True, "inventory": {"rendered": 3, "captured": 2,
                                                     "missing": 1, "groups": 1},
                  "questions": [{"n": 7, "status": ""}]})
    try:
        assert app._web_step(inc) is False
        assert skipped, "incomplete question should be skipped, not answered"
    finally:
        app._web_skip = orig_skip
    print("incomplete guard OK")

    # 5) 账本写失败必须“停在原题”，不能无记录地跳过。
    orig_record_once = skip_ledger.record_once

    def _boom(*_a, **_k):
        raise OSError("disk full")

    bad_drv = Driver({"qno": 9, "part": [1, 2], "text": "q9",
                      "questions": [{"n": 9, "status": ""},
                                    {"n": 10, "status": ""}]})
    skip_ledger.record_once = _boom
    try:
        app._web_ledger_failed = False
        assert app._web_skip(bad_drv, "k9") is False
        assert app._web_ledger_failed is True
        assert app._web_recover_blocked(bad_drv) is False
        assert app._web_blocked == [], app._web_blocked
    finally:
        skip_ledger.record_once = orig_record_once
        app._web_ledger_failed = False
    print("ledger failure stops OK")

    # 5b) 恢复跳题时的入账失败同样必须停，且不能把题号冒充成“已入账”。
    skip_ledger.record_once = _boom
    try:
        app._web_ledger_failed = False
        app._web_round_failed = False
        app._web_blocked = []
        assert app._web_recover_blocked(bad_drv) is False
        assert app._web_ledger_failed is True
        assert app._web_blocked == [], app._web_blocked
    finally:
        skip_ledger.record_once = orig_record_once
        app._web_ledger_failed = False
        app._web_round_failed = False
    print("recover ledger failure stops OK")

    # 6) 跳过账本 + 阻塞题恢复：Q7 失败后记录，并跳到 Q8；重复记录不刷屏。
    tmp = tempfile.mkdtemp(prefix="shinichi_p0_app_")
    old_appdata = os.environ.get("APPDATA")
    os.environ["APPDATA"] = tmp
    try:
        skip_ledger.clear()
        qs = [
            {"n": 7, "status": "Question 7, Partially correct", "selected": True},
            {"n": 8, "status": "", "selected": False},
        ]
        drv = Driver({"qno": 7, "part": [2, 3], "text": "q7", "questions": qs})
        app._web_skip(drv, "k7")
        app._web_skip(drv, "k7")
        items = skip_ledger.load()
        print("ledger:", items)
        assert len(items) == 1 and items[0]["qno"] == 7, items
        assert any("累计待人工 1 题" in t for _, t in statuses), statuses

        app._web_blocked = []
        assert app._web_recover_blocked(drv) is True
        assert app._web_blocked == [7], app._web_blocked
        assert drv.st["qno"] == 8, drv.st
        # recover 写的是同一题，不应重复加一条
        assert len(skip_ledger.load()) == 1, skip_ledger.load()
        print("blocked recover OK")
    finally:
        skip_ledger.clear()
        shutil.rmtree(tmp, ignore_errors=True)
        if old_appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = old_appdata

    print("RESULT: PASS")
    root.destroy()


if __name__ == "__main__":
    main()
