"""作者专用：生成一机一码激活码。

用法：
    python tools/license_keygen.py                     # 只看本机机器码
    python tools/license_keygen.py D6B1-411D-F9B1-414F # 生成永久激活码
    python tools/license_keygen.py D6B1-411D-F9B1-414F --days 365   # 一年有效期
    python tools/license_keygen.py D6B1-411D-F9B1-414F --check CODE # 校验一个码

把生成的激活码通过邮件发给用户即可。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from modules import license as lic  # noqa: E402
from modules import license_sign as signer  # noqa: E402


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    days = 0
    if "--days" in sys.argv:
        try:
            days = int(sys.argv[sys.argv.index("--days") + 1])
        except Exception:
            print("--days 后面要跟数字（天）")
            return 2

    if not args:
        print("本机机器码:", lic.machine_code())
        print("用法: python tools/license_keygen.py <机器码> [--days 365]")
        return 0

    machine = args[0]
    if "--check" in sys.argv:
        code = sys.argv[sys.argv.index("--check") + 1] if len(sys.argv) > sys.argv.index("--check") + 1 else ""
        ok, msg, _ = lic.verify_code(code, machine)
        print("校验:", "OK" if ok else "FAIL", "-", msg)
        return 0 if ok else 1

    key_file = sys.argv[sys.argv.index("--key") + 1] if "--key" in sys.argv else None
    code = signer.make_code(machine, days, key_file)
    ok, msg, _ = lic.verify_code(code, machine)
    print("机器码:", machine)
    print("有效期:", "永久" if days <= 0 else f"{days} 天")
    print("激活码:", code)
    print("自检:", "OK" if ok else "FAIL", "-", msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
