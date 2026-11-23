"""回归测试：1.0.6-beta 修掉的那批显性 bug，防止再犯。

覆盖：版本比较、答案解析容错、填空数量校验、题号状态判定、试用重置、
账本柱状图字体、全自动「跳过题 ↔ 回补题」死循环、收工标志、全错计数。

不连浏览器、不连网络、不弹窗口。
"""
from __future__ import annotations

import os
import queue
import shutil
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CFG = os.path.join(HERE, ".test_config_bugfixes")
shutil.rmtree(CFG, ignore_errors=True)
os.makedirs(CFG, exist_ok=True)
os.environ["SHINICHI_CONFIG_DIR"] = CFG      # 必须在导入 app/settings 之前
sys.path.insert(0, ROOT)

from app import App                                     # noqa: E402
from modules import license as lic, prompts, settings    # noqa: E402
from modules import update, usage, verify_math           # noqa: E402

FAILED: list[str] = []


def check(label: str, got, want) -> None:
    ok = got == want
    print(f"  {'OK  ' if ok else 'FAIL'} {label}: {got!r}")
    if not ok:
        FAILED.append(f"{label} -> {got!r} (want {want!r})")


def _driver(statuses: dict[int, str], cur: int):
    """假浏览器：只提供状态机需要读的页面快照。"""

    class Drv:
        def __init__(self):
            self.cur = cur
            self.jumps: list[tuple[int, int]] = []
            self.statuses = statuses

        def _q(self, n):
            return {"n": n, "status": self.statuses.get(n, ""), "selected": n == self.cur}

        def state(self):
            n = self.cur
            return {"text": f"Question {n}: solve x + {n} = 0.", "qkey": f"q{n}",
                    "part": [0, 0], "qno": n,
                    "questions": [self._q(i) for i in sorted(self.statuses)],
                    "fields": [{"id": f"S{n}", "label": "x", "readonly": False,
                                "disabled": False}],
                    "inputs": [], "radios": [], "checks": [], "selects": [],
                    "dropdowns": [], "imgs": [], "graph": None, "radios_disabled": 0,
                    "hasCheck": False, "canCheck": False, "hasNext": True,
                    "inDialog": False}

        def feedback(self):
            return ""

        def completion_state(self):
            return {"kind": "none", "hasOk": False, "hasNext": False, "dialogId": ""}

        def leave_prompt(self):
            return False

        def click_text(self, pattern):
            if "next" in pattern:
                self.cur = min(max(self.statuses), self.cur + 1)
            return "ok"

        def click_text_native(self, p):
            return self.click_text(p)

        def dialog_next(self):
            return False

        def goto_question(self, n):
            self.jumps.append((self.cur, n))
            self.cur = n
            return "ok"

    return Drv()


def _app():
    a = App.__new__(App)
    a.q = queue.Queue()
    a.web_stop = threading.Event()
    a._web_seen, a._web_prev, a._web_try = set(), {}, {}
    a._web_hint = ""
    a._web_graph_done = set()
    a._web_blocked, a._web_partial_done = [], set()
    a._web_all_done = False
    a._web_ok = a._web_fail = a._web_question = 0
    a._web_continue_wrong = True
    a._web_current_key = ""
    a._web_ctx = {}
    a._web_model_fails = 0
    a._web_empty_since = 0
    a._web_round_failed = False
    a.log: list[str] = []
    a._web_status = lambda text, level="info": a.log.append(text)
    return a


def main() -> int:
    real_sleep = time.sleep
    time.sleep = lambda *_a, **_k: None
    try:
        print("== 版本比较（预发布后缀）==")
        check("1.0.6 > 1.0.6-beta1", update.is_newer("1.0.6", "1.0.6-beta1"), True)
        check("beta2 > beta1", update.is_newer("v1.0.6-beta2", "1.0.6-beta1"), True)
        check("1.0.5 不比 beta1 新", update.is_newer("1.0.5", "1.0.6-beta1"), False)
        check("同版本不更新", update.is_newer("v1.0.6-beta1", "1.0.6-beta1"), False)
        check("展示版本仍是 1.0.6", update.parse_version("v1.0.6-beta1"), (1, 0, 6))

        print("== 答案解析容错 ==")
        for raw, want in (("CHOICE B", ["B"]), ("**CHOICE**: A", ["A"]),
                          ("CHOICE = C", ["C"]), ("`VALUE`: 5", ["5"]),
                          ("CHOICE: A, C", ["A", "C"])):
            spec = prompts.parse_web_answer(raw)
            check(f"parse {raw!r}", spec["choices"] or spec["values"], want)
        check("VALUE 里的冒号不被切坏",
              prompts.parse_web_answer("VALUE: 1:30")["value"], "1:30")

        print("== 填空数量校验 ==")
        quad = {"text": "For f(x) = x^2 - 4x + 3 answer the following.",
                "inputs": [], "radios": [], "dropdowns": [],
                "fields": [{"label": "What is the vertex?"},
                           {"label": "What is the y-intercept?"}]}
        check("2 空 2 值", verify_math.verify_candidate(
            quad, {"values": ["(2,-1)", "3"]})[0], "ok")
        check("2 空 1 值", verify_math.verify_candidate(
            quad, {"values": ["(2,-1)"]})[0], "fail")

        print("== 题号状态判定 ==")
        for raw, want in (("Question 5, Correct", "correct"),
                          ("Question 5, Incorrect", "incorrect"),
                          ("Question 5, Partially correct", "partial"),
                          ("Question 5, Not answered", "blank"),
                          ("", "blank")):
            check(f"kind {raw!r}", App._web_status_kind(raw), want)

        print("== 试用重置 ==")
        check("新机给试用", lic.check_access()[0], "fresh")
        check("开试用", lic.start_trial()[0], "trial")
        settings.save({"api_key": "sk-regress", "save_key": True})
        os.remove(os.path.join(settings.config_dir(), "trial.json"))
        check("删 trial.json 后", lic.check_access()[0], "expired")

        print("== 账本柱状图 ==")
        img = usage.render_chart([(f"2026-11-{i:02d}", i * 0.1, i * 100)
                                  for i in range(1, 31)])
        check("出图尺寸", (img.width, img.height), (860, 170))

        print("== 全自动：跳过题不再打转 ==")
        a = _app()
        drv = _driver({1: "", 2: "", 3: ""}, 2)
        seen_keys = []
        for n in (1, 2):
            old = drv.cur
            drv.cur = n
            seen_keys.append(App._web_key(a, drv.state()))
            drv.cur = old
        a._web_seen.update(seen_keys)
        App._web_wait_change = staticmethod(
            lambda d, old, timeout=0: App._web_key(a, d.state()) != old)
        steps = 0
        while steps < 12:
            before = drv.cur
            cont = App._web_step(a, drv)
            steps += 1
            print(f"    第{steps:02d}步 Q{before} -> Q{drv.cur}")
            if not cont:
                break
        check("12 步内停住", steps < 12, True)
        check("跳过题被记为待人工", bool(a._web_blocked), True)

        print("== 全自动：全是 Incorrect 时的计数 ==")
        a2 = _app()
        drv2 = _driver({1: "Question 1, Incorrect", 2: "Question 2, Incorrect",
                        3: "Question 3, Incorrect"}, 3)
        cont = App._web_step(a2, drv2)
        check("判为已完成", cont, False)
        check("对 0", a2._web_ok, 0)
        check("错 3", a2._web_fail, 3)

        print("== 收工标志 ==")

        class _Var:
            def __init__(self, v=False):
                self.v = v

            def get(self):
                return self.v

            def set(self, v):
                self.v = v

        a3 = App.__new__(App)
        a3.busy = False
        a3.web_on = True
        a3.web_stop = threading.Event()
        a3.cancel = threading.Event()
        a3.auto_var = _Var(False)
        a3.web_var = _Var(True)
        a3.btn_web = type("B", (), {"configure": lambda *x, **k: None})()
        a3._refresh_action_status = lambda: None
        a3._status = lambda *x, **k: None
        a3._web_user_stop = False
        App.action_stop(a3)
        check("收工后 _web_user_stop", a3._web_user_stop, True)
        check("收工后 web_on", a3.web_on, False)
    finally:
        time.sleep = real_sleep
        shutil.rmtree(CFG, ignore_errors=True)

    if FAILED:
        print("\n失败项:")
        for f in FAILED:
            print("  -", f)
    print("\nRESULT:", "PASS" if not FAILED else "FAIL")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    raise SystemExit(main())
