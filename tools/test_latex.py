"""LaTeX → 可读数学符号 的转换 + 流式一致性测试。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.latex import MathStream, latex_to_text, to_editor_input

SAMPLES = [
    r"f(x) = $\sqrt{361 - x^2}$",
    r"A. $x^2 > 361$",
    r"答案：$\frac{1}{2}x + \frac{\sqrt{3}}{3}$",
    r"矩阵 $\begin{pmatrix} 1 & 2 \\ 3 & 4 \end{pmatrix}$ 的逆",
    r"区间 $[-19, 19]$，$\theta \in [0, \pi]$",
    r"$x^{2n+1}$, $a_1$, $\sum_{i=1}^{n} i^2$",
    r"所以 $x^2 \le 361$，即 $-19 \le x \le 19$。",
    r"$\lim_{x \to 0} \frac{\sin x}{x} = 1$",
    r"$\int_0^1 x^2\,dx = \frac{1}{3}$",
    r"$\begin{cases} x + y = 3 \\ x - y = 1 \end{cases}$",
    r"$|x| \ge 2$ 且 $x \ne 0$",
    # 模型偶尔会漏掉反斜杠的伪 LaTeX
    r"f(x)=(x-3)^(1/2)",
    r"【答案】(3,+infty)",
    r"(f(x)=(x-3)^{1/2}=sqrt{x-3})，偶次根号内必须非负，所以 (x-3ge 0)，即 (xge 3)。",
    r"frac{1}{2} 和 pi/theta",
]

for s in SAMPLES:
    print("IN :", s)
    print("OUT:", latex_to_text(s))
    print()

print("=== 流式一致性（整段转换 vs 分块流式）===")
TEXTS = [
    "【答案】(3,+infty)\n【解析】f(x)=(x-3)^{1/2}=sqrt{x-3}，所以 x-3ge 0，即 xge 3。",
    r"于是 $f(x)=\sqrt{361-x^2}$，答案 $x^2 \le 361$。",
    "这道题的定义域是 $[3,+\\infty)$，因为根号内必须非负。",
]
all_ok = True
for text in TEXTS:
    expect = latex_to_text(text)
    for size in (1, 2, 3, 5, 7, 13, 40):
        st = MathStream()
        out = ""
        for i in range(0, len(text), size):
            out += st.feed(text[i:i + size])
        out += st.flush()
        ok = out == expect
        all_ok &= ok
        if not ok:
            print(f"  [FAIL] size={size}")
            print("   expect:", expect.replace("\n", " | "))
            print("   got   :", out.replace("\n", " | "))
    print(f"  size 1/2/3/5/7/13/40 -> {'OK' if all_ok else 'FAIL'}")
    print("   ", expect.replace("\n", " | "))
    all_ok = True

print("\nRESULT:", "PASS" if all_ok else "FAIL")

print("=== 编辑器输入（Pearson 快捷命令）===")
EDITOR_CASES = [
    (r"(3,+\infty)", r"(3,+\inf)"),
    ("(-\u221e,-2)\u222a(-2,2)\u222a(2,\u221e)", r"(-\inf,-2)\cup(-2,2)\cup(2,\inf)"),
    (r"\frac{1}{2}", "1/2"),
    (r"\frac{x+1}{x-1}", "(x+1)/(x-1)"),
    (r"\sqrt{3}", r"\sqrt3"),
    (r"x^{2n+1}", "x^(2n+1)"),
    (r"x \le 3", "x<=3"),
]
editor_ok = True
for src, want in EDITOR_CASES:
    got = to_editor_input(src)
    flag = "OK " if got == want else "BAD"
    if got != want:
        editor_ok = False
    print(f"  {flag} {src!r} -> {got!r} (want {want!r})")
print("编辑器输入:", "PASS" if editor_ok else "FAIL")
