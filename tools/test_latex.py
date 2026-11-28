"""LaTeX → 可读数学符号 的转换 + 流式一致性测试。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.latex import MathStream, latex_to_text, to_editor_input, to_paste_input

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
    # 根号一律写 \sqrt(...)：整段插入时，省括号的 \sqrt3 不保证把 3 收进根号
    (r"\sqrt{3}", r"\sqrt(3)"),
    (r"x^{2n+1}", "x^(2n+1)"),
    (r"x \le 3", "x<=3"),
    (r"x^-2", "x^(-2)"),
    (r"e^-x", "e^(-x)"),
    ("1/-2", "1/(-2)"),
    (r"\text{mph}", "mph"),
    # 对数：编辑器没有 \log 命令，必须写成 log_b x（无反斜杠、括号只用于分组）
    (r"\log_{6}(p)", "log_6 p"),
    (r"\log_2(8)", "log_2 8"),
    (r"\log(x)", "log x"),
    (r"\log x", "log x"),
    (r"\ln(x)", "ln x"),
    (r"\ln x", "ln x"),
    (r"\ln(2x+1)", "ln (2x+1)"),
    (r"\ln 2x", "ln 2x"),
    # 函数名后的空格不能被压掉，否则 sin2x 会变成一个变量名
    (r"\sin 2x", "sin 2x"),
    # n 次根编辑器不认，必须转成指数
    (r"\sqrt[4]{2}", "(2)^(1/4)"),
    (r"\sqrt[3]{x}", "(x)^(1/3)"),
]
editor_ok = True
for src, want in EDITOR_CASES:
    got = to_editor_input(src)
    flag = "OK " if got == want else "BAD"
    if got != want:
        editor_ok = False
    print(f"  {flag} {src!r} -> {got!r} (want {want!r})")
print("编辑器输入:", "PASS" if editor_ok else "FAIL")

print("\n=== 粘贴输入（Paste）===")
PASTE_CASES = [
    (r"x^{-2}", "x^(-2)"),
    (r"e^{-x}", "e^(-x)"),
    ("1/-2", "1/(-2)"),
    (r"\text{mph}", "mph"),
    (r"\sqrt{x+1}", "√(x+1)"),
    (r"x \ge 2", "x≥2"),
    (r"x \approx 3", "x≈3"),
    (r"x \to 0", "x→0"),
    (r"\infty", "∞"),
    (r"\int_0^1 x dx", "∫_0^1xdx"),
    (r"\sin x", "sin x"),
    (r"\ln x", "ln(x)"),
    (r"\log_{6}(p)", "log_6(p)"),
    (r"\lim_{x \to 0} x", "lim_{x→0}x"),
    (r"\dfrac{1}{2}", "(1)/(2)"),
    (r"\sqrt[3]{x}", "³√(x)"),
    (r"\textrm{mph}", "mph"),
]
paste_ok = True
for src, want in PASTE_CASES:
    got = to_paste_input(src)
    flag = "OK " if got == want else "BAD"
    if got != want:
        paste_ok = False
    print(f"  {flag} {src!r} -> {got!r} (want {want!r})")
print("粘贴输入:", "PASS" if paste_ok else "FAIL")

print("\n=== 数学输入编排（模拟结构感知 insert_math）===")
# 紫：编辑器敲下 `/` 就钻进分母、敲下 `^` 就钻进指数，得按**两下**右箭头才出得来。
# 这些用例守的就是这条：分式/指数打完先跳出去，右括号才不会被吞进分母。
from modules.web import WebPlayer as _WP

def _typed(expr: str) -> str:
    out = []
    w = _WP.__new__(_WP)
    # 关掉所有等待，测试不用真睡
    w.MATH_SETTLE = 0
    w.MATH_ARROW_WAIT = 0
    w.MATH_AFTER_ARROW = 0
    w.insert = lambda t: out.append(t)      # 整段 insertText
    w._char = lambda ch: out.append(ch)     # 逐字符（反斜杠命令走这条）
    w._arrow_right = lambda: out.append("→")
    _WP.insert_math(w, expr)
    return "".join(out)

SEQ_CASES = [
    # 分式：跳出去再落笔
    ("x^-1", "x^(-1)→→"),
    ("e^-x", "e^(-x)→→"),
    ("1/-2", "1/(-2)→→"),
    # 经典事故：5(x+3/2)^2 曾被写成 5(x+3/(2)^2)，右括号标红
    ("5(x+3/2)^(2)-29/4", "5(x+3/2→→)^(2)→→-29/4→→"),
    # 分式后面还跟着因子：必须跳出分母，x 才在外头
    ("(1)/(2)x", "(1)/(2)→→x"),
    # 对数：log_6 p（无反斜杠、无反括号）
    ("log_6 p", "log_6→→p"),
    ("ln (2x+1)", "ln (2x+1)"),
    # n 次根换成指数后，指数里的分式同样要跳
    ("(2)^(1/4)", "(2)^(1/4→→)→→"),
    ("\\sqrt(2x+1)", "\\sqrt(2x+1)→→"),
]
seq_ok = True
for src, want in SEQ_CASES:
    got = _typed(to_editor_input(src))
    if got != want:
        seq_ok = False
        print(f"  BAD {src!r} -> {got!r} (want {want!r})")
    else:
        print(f"  OK  {src!r} -> {got!r}")
print("按键序列:", "PASS" if seq_ok else "FAIL")
if not (editor_ok and paste_ok and seq_ok):
    raise SystemExit(1)
