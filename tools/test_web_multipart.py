"""多小问 / Review 页回归：不允许跳题，也不允许因为旧选项禁用而误判整页。"""
import os
import sys
import tempfile
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("SHINICHI_CONFIG_DIR", os.path.join(tempfile.gettempdir(), "sc_web_multipart_test"))
sys.path.insert(0, os.path.dirname(HERE))

from app import App


class Driver:
    def __init__(self, st):
        self.st = st
        self.clicks = []
        self.filled = None

    def state(self):
        return dict(self.st)

    def click_text(self, pattern):
        self.clicks.append(pattern)
        return "ok"

    def leave_prompt(self):
        return False

    def feedback(self):
        return "correct"

    def feedback_text(self):
        return ""

    def dialog_next(self):
        return False

    def focus_field(self, _fid):
        return None

    def clear_field(self):
        return None

    def paste_math(self, text):
        self.filled = text
        return True

    def insert_math(self, _text):
        return None

    def field_text(self, _fid):
        return "-15"

    def field_label(self, _fid):
        return "y-intercept"

    def goto_question(self, n):
        self.st = dict(self.st)
        self.st["qno"] = n
        self.st["questions"] = [
            dict(q, selected=(int(q["n"]) == n))
            for q in self.st.get("questions", [])
        ]
        return "ok"


def main() -> None:
    root = tk.Tk()
    root.withdraw()
    app = App(root)
    app._web_status = lambda *_a, **_k: None
    app._web_wait_change = lambda _drv, _key, timeout=15: True
    app._web_next = lambda _drv, _key: (_ for _ in ()).throw(
        AssertionError("multi-part must not advance"))
    app._web_skip = lambda _drv, _key: (_ for _ in ()).throw(
        AssertionError("must not skip"))
    for k, v in {
        "_web_question": 0, "_web_ok": 0, "_web_fail": 0, "_web_seen": set(),
        "_web_prev": {}, "_web_hint": "", "_web_try": {}, "_web_model_fails": 0,
        "_web_current_key": "",
    }.items():
        setattr(app, k, v)

    base = {
        "hasCheck": True, "text": "The y-intercept is at y = ____.",
        "fields": [
            {"id": "S1", "label": "(-2,5)"},
            {"id": "S2", "label": "-3,-1"},
            {"id": "S3", "label": "enter your response here"},
        ],
        "radios": [], "checks": [], "inputs": [], "dropdowns": [], "selects": [],
        "radios_disabled": 2, "hasNext": True, "inDialog": False,
        "part": [4, 5],
    }
    # 新 part 的 key 必须不同，不能被 _web_seen 当成旧 part
    a = dict(base, part=[3, 5])
    b = dict(base, part=[4, 5])
    assert app._web_key(a) != app._web_key(b)

    driver = Driver(base)
    app._ask_cancellable = lambda *_a, **_k: "VALUE: -15"
    app._web_ctx = {"base": "x", "key": "k", "model": "m", "vision": "",
                    "extra": {}, "translate": False}
    assert app._web_step(driver) is True
    assert driver.filled == "-15"
    assert any("check answer" in c for c in driver.clicks)
    # Q2 已 Correct、Q3-Q6 已 Correct、Q7 仍 Partially correct、Q8 未答：
    # 应该从 Q2 跳到最近一道没完成的 Q7，而不是傻等 Next。
    qs = [
        {"n": 1, "status": "Question 1, Correct", "selected": False},
        {"n": 2, "status": "Question 2, Correct", "selected": True},
        {"n": 3, "status": "Question 3, Correct", "selected": False},
        {"n": 4, "status": "Question 4, Correct", "selected": False},
        {"n": 5, "status": "Question 5, Correct", "selected": False},
        {"n": 6, "status": "Question 6, Correct", "selected": False},
        {"n": 7, "status": "Question 7, Partially correct", "selected": False},
        {"n": 8, "status": "", "selected": False},
    ]
    jump_st = {"qno": 2, "questions": qs, "part": [1, 1], "text": "q2"}
    jump_driver = Driver(jump_st)
    assert app._web_jump_next_unanswered(jump_driver, jump_st) is True
    assert jump_driver.st["qno"] == 7
    print("next-unanswered jump OK")
    # 当前停在 Q8 未答，但 Q7 只 Partially correct：自动应回头补 Q7
    qs2 = [dict(q) for q in qs]
    for q in qs2:
        q["selected"] = (q["n"] == 8)
    back_st = {"qno": 8, "questions": qs2, "part": [1, 5], "text": "q8"}
    back_driver = Driver(back_st)
    assert app._web_jump_first_unfinished(back_driver, back_st) is True
    assert back_driver.st["qno"] == 7
    print("earlier-unfinished backfill OK")

    print("multi-part fill / review-page regression OK")
    root.destroy()


if __name__ == "__main__":
    main()
    print("RESULT: PASS")
