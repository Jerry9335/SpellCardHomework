"""choice_match 回归：移植 Auto-Pearson choiceIndex 的核心行为。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from modules.choice_match import choice_index, match_choice  # noqa: E402


def eq(got, want):
    assert got == want, f"got {got!r}, want {want!r}"


def main() -> int:
    # 标准 A/B/C 前缀
    choices = ["A. Find the value that x+2 over x-5 approaches", "B. Solve x - 5 = 0", "C. Simplify", "D. None"]
    eq(choice_index("B", choices), 1)
    eq(choice_index("B.", choices), 1)
    eq(choice_index("B) Solve x - 5 = 0", choices), 1)
    eq(choice_index("Option B: Solve x - 5 = 0", choices), 1)
    eq(choice_index("Solve x - 5 = 0", choices), 1)
    eq(choice_index("b", choices), 1)

    # 百分比 / 数字 / 图片选项
    pct = ["A. 50%", "B. 75%", "C. 90%"]
    eq(choice_index("75%", pct), 1)
    eq(choice_index("B. 75%", pct), 1)
    eq(choice_index("B) 75%", pct), 1)
    eq(choice_index("D", pct), None)  # 越界字母
    eq(choice_index("80%", pct), None)  # 不存在的值

    # 图片/图形选项：标签本身没有字母，按字母顺序
    imgs = ["graph rising line", "graph falling line", "graph circle"]
    eq(choice_index("A", imgs), 0)
    eq(choice_index("C", imgs), 2)
    # 图片选项给完整文本也能匹配
    eq(choice_index("graph circle", imgs), 2)

    # 歧义：两个相同标签不能猜
    dup = ["A. Yes", "B. Yes"]
    m = match_choice("Yes", dup)
    eq(m.ok, False)
    eq(m.ambiguous, True)
    # 但带字母仍能唯一定位
    eq(choice_index("A", dup), 0)
    eq(choice_index("B", dup), 1)

    # 字母与正文冲突：正文唯一匹配另一个选项时，按正文纠正
    conflict = ["A. 50%", "B. 75%", "C. 90%"]
    eq(choice_index("A. 90%", conflict), 2)
    # 字母不存在、正文也不存在 -> None
    eq(choice_index("D. 10%", conflict), None)

    # 数字序号
    nums = ["1. 10", "2. 20", "3. 30"]
    eq(choice_index("2", nums), 1)
    eq(choice_index("3. 30", nums), 2)
    eq(choice_index("4", nums), None)

    # 空答案 / 空选项
    eq(choice_index("", choices), None)
    eq(choice_index("A", []), None)
    print("choice_match OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
