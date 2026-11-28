"""P0 / P1 / P2 修复的回归测试（纯逻辑，不需要浏览器）。

灵梦：修好的符卡得留个记号。不然下次谁又把它们弄坏了，还得从头查一遍。

用法：

    python tools/test_fix_regressions.py

覆盖：
- P0-5  多小问共享题干（`_web_part_text` / `_web_focus_text`）
- P1-3  回读比对用等价形态（`_fill_matches`：LaTeX / 分数 / 无穷）
- P2-28 回读比对的 token 边界（`-2` `2.5` `3/2` `√3` `x+1` 都不算命中）
- P2-19 配置里的坏数值不拖垮启动（`_cfg_float` / `_cfg_int`）
"""
from __future__ import annotations

import importlib.util
import os
import sys

# 中文 Windows 控制台默认 GBK，打印 √ ² ∞ 会直接 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# 别把测试写进真实的 %APPDATA%
os.environ.setdefault("SHINICHI_CONFIG_DIR",
                      os.path.join(os.environ.get("TEMP") or ".", "sch_test_fix"))

fails: list[str] = []


def check(ok: bool, label: str, detail: str = "") -> None:
    if not ok:
        fails.append(label)
    print(f"  {'OK ' if ok else 'BAD'} {label}{('  ' + detail) if detail else ''}")


def load_app():
    spec = importlib.util.spec_from_file_location(
        "sch_app_under_test", os.path.join(HERE, "app.pyw"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    appmod = load_app()
    App = appmod.App

    print("=== P0-5 多小问：共享题干不能丢 ===")
    raw = ("Solve the following.\n"
           "Part 1 of 3: Find f(2).\n"
           "Part 2 of 3: Find the derivative f'(x).\n"
           "Part 3 of 3: Sketch the graph.\n")
    seg2 = App._web_part_text(raw, 2)
    check("of 3:" not in seg2, "第 2 小问不带「of 3:」尾巴", repr(seg2[:40]))
    focus2 = App._web_focus_text(raw, 2)
    check("Solve the following." in focus2, "第 2 小问带上了共享题干")
    check("Find the derivative" in focus2, "第 2 小问问句在")
    check("Find f(2)" not in focus2, "没有混进第 1 小问的正文")
    focus3 = App._web_focus_text(raw, 3)
    check("Solve the following." in focus3 and "Sketch the graph" in focus3,
          "第 3 小问同样正常")
    check(App._web_focus_text("plain", 0) == "plain", "单问文本原样返回")
    check(App._web_part_text("没有小问标记", 2) == "没有小问标记", "没有 Part 标记时不乱切")

    print()
    print("=== P1-3 跨小问题干不应压过单问 ===")
    check(App._web_focus_text("Part 1 of 2: A\nPart 2 of 2: B\n", 1).count("A") == 1,
          "第 1 小问正文只出现一次")

    print()
    print("=== P1-3 / P2-28 回读比对 ===")
    want_true = [
        (r"\frac{1}{2}", "(1)/(2)", "LaTeX 分数 vs 编辑器回读"),
        ("1/2", "(1)/(2)", "去括号等价"),
        (r"x^{-2}", "x^(-2)", "负指数按键形态"),
        ("(3,+\\infty)", "(3,+∞)", "无穷号两种写法"),
        ("2", "(2)", "括号包一个数"),
        ("3", "3.0", "3.0 等于 3"),
        ("5", "5", "完全相同"),
    ]
    for exp, got, note in want_true:
        check(App._fill_matches(exp, got), f"应通过：{note}", f"{exp!r} vs {got!r}")

    want_false = [
        ("2", "12", "12 不是 2"),
        ("2", "-2", "-2 不是 2"),
        ("2", "2.5", "2.5 不是 2"),
        ("2", "3/2", "3/2 不是 2"),
        ("3", "√3", "√3 不是 3"),
        ("3", "3√2", "3√2 不是 3"),
        ("x", "x+1", "x+1 不是 x"),
        ("2", "x^2", "x^2 不是 2"),
    ]
    for exp, got, note in want_false:
        check(not App._fill_matches(exp, got), f"应拒绝：{note}", f"{exp!r} vs {got!r}")

    print()
    print("=== P2-19 坏配置不拖垮启动 ===")
    for value, default in (("abc", 0.2), (None, 0.2), ("", 0.2), ([1, 2], 0.2)):
        check(appmod._cfg_float(value, default) == default,
              f"_cfg_float({value!r}) 退回默认 {default}")
    check(appmod._cfg_float("1.5", 0.2) == 1.5, "_cfg_float 正常值照收")
    for value, default in (("abc", 9222), (None, 9222)):
        check(appmod._cfg_int(value, default) == default,
              f"_cfg_int({value!r}) 退回默认 {default}")
    check(appmod._cfg_int("8080", 9222) == 8080, "_cfg_int 正常值照收")

    print()
    print("=== 页面状态模型：只填该填的空 ===")
    # `_web_targets` 只用到快照 st，不碰 self，所以拿个空壳当 self 就行
    class _Stub:
        pass

    def targets(st):
        return [b["id"] for b in App._web_targets(_Stub(), st, 0)]

    # 判过分的 Part 会锁住（disabled），不许再往里写
    check(targets({"fields": [{"id": "a", "label": "x =", "filled": True,
                               "disabled": True},
                              {"id": "b", "label": "y =", "filled": False}],
                   "inputs": [], "radios": []}) == ["b"],
          "已判分锁住的空被跳过")
    # 但「填着内容、还能编辑」的框必须留下：那是上一轮填错的答案，要清掉重写
    check(targets({"fields": [{"id": "c", "label": "", "filled": True,
                               "disabled": False}],
                   "inputs": [], "radios": []}) == ["c"],
          "填着错答案但仍可编辑的框要留下重填")

    check(targets({"fields": [{"id": "optA", "label": "", "in_opt": "unchecked"},
                              {"id": "optB", "label": "", "in_opt": "checked"},
                              {"id": "body", "label": "", "in_opt": ""}],
                   "inputs": [],
                   "radios": [{"id": "r1", "checked": True}]}) == ["optB", "body"],
          "未选中选项里的空跳过、题干正文空保留")

    # 关键回归：Pearson 把「选中的那个选项」里的空也起名 Decoy1，
    # 按名字过滤会把该填的空跳过 → Check 一直灰着。
    check(targets({"fields": [{"id": "Decoy1", "label": "",
                               "in_opt": "checked", "decoy": True}],
                   "inputs": [],
                   "radios": [{"id": "r1", "checked": True}]}) == ["Decoy1"],
          "选中的选项里名字带 Decoy 的空照样要填")

    check(targets({"fields": [{"id": "optA", "label": "", "in_opt": "unchecked"}],
                   "inputs": [],
                   "radios": [{"id": "r1", "checked": False}]}) == ["optA"],
          "还没选选项时不做选项内过滤")

    print()
    print("=== 模型只回一个答案时的兜底解析 ===")
    from modules import prompts as _p

    for raw, want in [
        ("12.7", "12.7"),
        ("44.94", "44.94"),
        ("x=5", "x=5"),
        ("(3, 9)", "(3, 9)"),
        ("log_6 p", "log_6 p"),
        # 英文句子不能被当成答案（否则会整句填进输入框）
        ("The projected population is 12.7 million.", ""),
        ("the answer is 5", ""),
    ]:
        got = str(_p.parse_web_answer(raw).get("value") or "")
        check(got == want, f"parse_web_answer({raw!r}) -> {got!r}（期望 {want!r}）")
    check(_p.parse_web_answer("B").get("choice") == "B", "裸字母按选项解析")

    print()
    print("=== 左右分栏题干不能只读右半边 ===")
    from modules import web as _web

    js = _web._STATE_JS
    check("contentHolderleft" in js and "contentHolderright" in js,
          "快照同时引用左右分栏容器")
    check("holderEls" in js and "[leftEl, rightEl, topEl, bottomEl]" in js,
          "按左→右、上→下的顺序拼接题干")

    print()
    if fails:
        print(f"RESULT: FAIL（{len(fails)} 项）")
        for f in fails:
            print("  -", f)
        return 1
    print("RESULT: PASS（灵梦：退治辛苦了，这批符卡都收好了。）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
