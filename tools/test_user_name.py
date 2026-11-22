"""账户显示名测试。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from modules import user_name


def main() -> None:
    name = user_name.current_display_name()
    print("display:", name, "ms_hint:", user_name._has_ms_account())
    assert name and len(name) <= 32
    assert user_name._clean("LAPTOP-IQVQ9DA3\\\\16514") == "16514"
    assert user_name._clean("a@b.com") == "a"
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
