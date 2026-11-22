"""自动答题解析/归一化回归测试（不依赖浏览器）。"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from modules import latex, prompts  # noqa: E402


def main() -> None:
    cases = [
        ("CHOICE: A and C", ["A", "C"]),
        ("CHOICE: A, C", ["A", "C"]),
        ("CHOICE: AC", ["A", "C"]),
        ("CHOICE: B", ["B"]),
        ("CHOICE: none of these", []),
        ("CHOICE: A、C", ["A", "C"]),
    ]
    for raw, want in cases:
        got = prompts.parse_web_answer(raw)["choices"]
        assert got == want, (raw, got, want)
        print(f"  OK  {raw!r} -> {got}")

    drops = [
        ("DROPDOWN: 1; 2", [1, 2]),
        ("DROPDOWN: 1) 3", [3]),
        ("DROPDOWN: 1、2、3", [1, 2, 3]),
    ]
    for raw, want in drops:
        got = prompts.parse_web_answer(raw)["drops"]
        assert got == want, (raw, got, want)
        print(f"  OK  {raw!r} -> {got}")

    norm = [
        ("x = 3", "3"), ("3.0", "3"), ("−5", "-5"), (" 1 / 2 ", "1/2"),
    ]
    for raw, want in norm:
        got = latex.normalize_answer(raw)
        assert got == want, (raw, got, want)
        print(f"  OK  normalize {raw!r} -> {got!r}")

    print("RESULT: PASS")


if __name__ == "__main__":
    main()
