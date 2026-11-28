"""把模型输出的 LaTeX 转成人能直接看的数学符号。

只做「够用就好」的转换：希腊字母、常用运算符、上下标、根号、分式、矩阵、箭头。
不追求排版完美，目标是让人在文本框里一眼看懂，而不是看到 $\\frac{a}{b}$ 这种源码。

流式场景用 MathStream：它会等一个 $...$ 收尾了才转换，避免把半个公式切坏。
"""
from __future__ import annotations
import re

GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "varpi": "ϖ", "rho": "ρ",
    "varrho": "ϱ", "sigma": "σ", "varsigma": "ς", "tau": "τ", "upsilon": "υ", "phi": "φ",
    "varphi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π",
    "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}

SYMBOLS = {
    "times": "×", "div": "÷", "cdot": "·", "ast": "*", "star": "*", "bullet": "•",
    "pm": "±", "mp": "∓", "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "ne": "≠", "neq": "≠",
    "approx": "≈", "equiv": "≡", "sim": "∼", "simeq": "≃", "propto": "∝", "cong": "≅",
    "infty": "∞", "partial": "∂", "nabla": "∇", "degree": "°", "circ": "°", "prime": "′",
    "to": "→", "rightarrow": "→", "leftarrow": "←", "Rightarrow": "⇒", "Leftarrow": "⇐",
    "leftrightarrow": "↔", "Leftrightarrow": "⇔", "mapsto": "↦", "uparrow": "↑", "downarrow": "↓",
    "in": "∈", "notin": "∉", "ni": "∋", "subset": "⊂", "subseteq": "⊆", "supset": "⊃", "supseteq": "⊇",
    "cup": "∪", "cap": "∩", "setminus": "∖", "emptyset": "∅", "varnothing": "∅",
    "forall": "∀", "exists": "∃", "neg": "¬", "land": "∧", "lor": "∨",
    "oplus": "⊕", "otimes": "⊗", "perp": "⊥", "parallel": "∥", "angle": "∠", "triangle": "△",
    "sum": "∑", "prod": "∏", "int": "∫", "iint": "∬", "iiint": "∭", "oint": "∮",
    "cdots": "…", "ldots": "…", "dots": "…", "vdots": "⋮", "ddots": "⋱",
    "langle": "⟨", "rangle": "⟩", "lceil": "⌈", "rceil": "⌉", "lfloor": "⌊", "rfloor": "⌋",
    "mid": "|", "vert": "|", "Vert": "‖", "%": "%", "&": "&", "#": "#", "_": "_", "$": "$",
    "{": "{", "}": "}", "backslash": "\\", "quad": "  ", "qquad": "    ",
    " ": " ", ",": " ", ";": " ", ":": " ", "!": "",
    "log": "log", "ln": "ln", "sin": "sin", "cos": "cos", "tan": "tan", "sec": "sec",
    "csc": "csc", "cot": "cot", "arcsin": "arcsin", "arccos": "arccos", "arctan": "arctan",
    "lim": "lim", "max": "max", "min": "min", "sup": "sup", "inf": "inf", "det": "det",
    "exp": "exp", "gcd": "gcd", "lcm": "lcm",
}

SUP = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    "+": "⁺", "-": "⁻", "=": "⁼", "(": "⁽", ")": "⁾",
    "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ", "f": "ᶠ", "g": "ᵍ", "h": "ʰ", "i": "ⁱ",
    "j": "ʲ", "k": "ᵏ", "l": "ˡ", "m": "ᵐ", "n": "ⁿ", "o": "ᵒ", "p": "ᵖ", "r": "ʳ", "s": "ˢ",
    "t": "ᵗ", "u": "ᵘ", "v": "ᵛ", "w": "ʷ", "x": "ˣ", "y": "ʸ", "z": "ᶻ",
}
SUB = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
    "+": "₊", "-": "₋", "=": "₌", "(": "₍", ")": "₎",
    "a": "ₐ", "e": "ₑ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ", "k": "ₖ", "l": "ₗ", "m": "ₘ", "n": "ₙ",
    "o": "ₒ", "p": "ₚ", "r": "ᵣ", "s": "ₛ", "t": "ₜ", "u": "ᵤ", "v": "ᵥ", "x": "ₓ",
}

_MATRIX_DELIM = {
    "pmatrix": ("(", ")"),
    "bmatrix": ("[", "]"),
    "Bmatrix": ("{", "}"),
    "vmatrix": ("|", "|"),
    "Vmatrix": ("‖", "‖"),
    "matrix": ("", ""),
    "array": ("", ""),
}


def _match(s: str, i: int) -> int:
    """s[i] == '{'，返回匹配的 '}' 下标。"""
    depth = 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(s) - 1


def _arg(s: str, i: int) -> tuple[str, int]:
    """读取一个参数：{...} 或单个字符。返回 (内容, 新位置)。"""
    while i < len(s) and s[i] in " \t":
        i += 1
    if i >= len(s):
        return "", i
    if s[i] == "{":
        j = _match(s, i)
        return s[i + 1:j], j + 1
    return s[i], i + 1


def _read_group(s: str, i: int) -> tuple[str | None, int]:
    """帕秋莉：从 s[i] 的 '{' 读到配对的 '}'；不完整就返回 (None, i)。"""
    if i >= len(s) or s[i] != "{":
        return None, i
    depth = 0
    j = i
    while j < len(s):
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return None, i


def _read_token(s: str, i: int) -> tuple[str | None, int, bool]:
    """读一个公式参数：{...}、反斜杠命令或单个字符。

    返回 (内容, 新位置, 是否带花括号)；读不完整返回 (None, i, False)。
    """
    while i < len(s) and s[i] in " \t":
        i += 1
    if i >= len(s):
        return None, i, False
    if s[i] == "{":
        body, j = _read_group(s, i)
        return (body, j, True) if body is not None else (None, i, False)
    if s[i] == "\\":
        m = re.match(r"\\[A-Za-z]+", s[i:])
        if m:
            return m.group(0), i + len(m.group(0)), False
    return s[i], i + 1, False


def _script(text: str, table: dict[str, str]) -> str:
    text = text.strip()
    if not text:
        return ""
    if all(c in table for c in text):
        return "".join(table[c] for c in text)
    if len(text) == 1:
        return ("^" if table is SUP else "_") + text
    return ("^(" if table is SUP else "_(") + text + ")"


def _frac(a: str, b: str) -> str:
    a, b = a.strip(), b.strip()
    simple = re.compile(r"^[A-Za-z0-9\u0370-\u03ff.]+$")
    na = a if simple.match(a) else f"({a})"
    nb = b if simple.match(b) else f"({b})"
    return f"{na}/{nb}"


def _matrix(env: str, body: str) -> str:
    rows = re.split(r"\\\\", body)
    cells = [[_convert(c.strip()) for c in re.split(r"(?<!\\)&", row.strip())] for row in rows if row.strip()]
    if not cells:
        return ""
    left, right = _MATRIX_DELIM.get(env, ("", ""))
    width = max(len(c) for row in cells for c in row) if cells else 0
    lines = []
    for row in cells:
        padded = [c.ljust(width) for c in row]
        lines.append(left + "  ".join(padded).rstrip() + right)
    return "\n".join(lines)


def _convert(s: str) -> str:
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            m = re.match(r"\\([A-Za-z]+|.)", s[i:], re.S)
            if not m:
                i += 1
                continue
            cmd = m.group(1)
            i += len(m.group(0))
            if cmd in ("frac", "dfrac", "tfrac"):
                a, i = _arg(s, i)
                b, i = _arg(s, i)
                out.append(_frac(_convert(a), _convert(b)))
            elif cmd == "sqrt":
                if i < n and s[i] == "[":
                    j = s.find("]", i)
                    idx = s[i + 1:j] if j != -1 else ""
                    i = j + 1 if j != -1 else n
                    a, i = _arg(s, i)
                    out.append(_script(_convert(idx), SUP) + "√(" + _convert(a) + ")")
                else:
                    a, i = _arg(s, i)
                    out.append("√(" + _convert(a) + ")")
            elif cmd in ("text", "mathrm", "mathbf", "mathit", "operatorname", "mbox", "textrm"):
                a, i = _arg(s, i)
                out.append(_convert(a))
            elif cmd in ("begin", "end"):
                env, i = _arg(s, i)
                if cmd == "begin":
                    end_tag = "\\end{" + env.strip() + "}"
                    j = s.find(end_tag, i)
                    body = s[i:j] if j != -1 else s[i:]
                    i = (j + len(end_tag)) if j != -1 else n
                    out.append(_matrix(env.strip(), body))
            elif cmd in ("left", "right", "big", "Big", "bigg", "Bigg"):
                pass
            elif cmd in GREEK:
                out.append(GREEK[cmd])
            elif cmd in SYMBOLS:
                out.append(SYMBOLS[cmd])
            elif cmd == "\\":
                out.append("\n")
            else:
                out.append(cmd)
        elif c in "^_":
            grp, i = _arg(s, i + 1)
            out.append(_script(_convert(grp), SUP if c == "^" else SUB))
        elif c == "{":
            j = _match(s, i)
            out.append(_convert(s[i + 1:j]))
            i = j + 1
        elif c == "&":
            out.append("  ")
            i += 1
        elif c == "~":
            out.append(" ")
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


_BARE = {
    "infty": "∞", "infinity": "∞", "inf": "∞", "approx": "≈", "times": "×", "cdot": "·",
    "pm": "±", "div": "÷", "neq": "≠", "geq": "≥", "leq": "≤", "ge": "≥", "le": "≤",
    "pi": "π", "theta": "θ", "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ",
    "lambda": "λ", "mu": "μ", "sigma": "σ", "omega": "ω", "phi": "φ", "rho": "ρ",
    "tau": "τ", "epsilon": "ε", "degree": "°", "subset": "⊂", "cup": "∪", "cap": "∩",
}


def _bare_commands(text: str) -> str:
    """模型有时漏掉反斜杠：把 sqrt{x}、xge 3、+infty 这类也转掉。"""
    text = re.sub(r"(?<![A-Za-z\\])sqrt\s*\{([^{}]*)\}", lambda m: "√(" + m.group(1) + ")", text)
    text = re.sub(r"(?<![A-Za-z\\])sqrt\s*\(([^()]*)\)", lambda m: "√(" + m.group(1) + ")", text)
    text = re.sub(r"(?<![A-Za-z\\])frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}",
                  lambda m: _frac(m.group(1), m.group(2)), text)
    # 紧跟在数字后面的运营商（"x-3ge 0"）
    text = re.sub(r"(?<=\d)\s*(geq|leq|neq|ge|le|approx|times|cdot|pm)\b",
                  lambda m: " " + _BARE[m.group(1)] + " ", text)
    # 单字母变量 + 裸运算符（"xge 3"），排除 page / large 这类单词
    text = re.sub(r"(?<![A-Za-z])([A-Za-z])(geq|leq|neq|ge|le)\b",
                  lambda m: m.group(1) + " " + _BARE[m.group(2)] + " ", text)
    # 独立的裸命令
    for name, sym in _BARE.items():
        text = re.sub(r"(?<![A-Za-z\\])\b" + name + r"\b(?!\{)", sym, text)
    # 裸花括号上下标：^{1/2}、_{n}
    text = re.sub(r"\^\{([^{}]*)\}", lambda m: _script(m.group(1), SUP), text)
    text = re.sub(r"_\{([^{}]*)\}", lambda m: _script(m.group(1), SUB), text)
    # 纯数字上标：x^2、n^10
    text = re.sub(r"\^(-?\d+)", lambda m: _script(m.group(1), SUP), text)
    text = re.sub(r" {2,}", " ", text)
    return text


def latex_to_text(text: str) -> str:
    """把一段可能含 LaTeX 的文本转成可读的 Unicode。"""
    if not text or "\\" not in text and "$" not in text:
        return _bare_commands(text) if text else text

    text = re.sub(r"\\\[(.*?)\\\]", lambda m: "\n" + _convert(m.group(1)) + "\n", text, flags=re.S)
    text = re.sub(r"\\\((.*?)\\\)", lambda m: _convert(m.group(1)), text, flags=re.S)
    text = re.sub(r"\$\$(.*?)\$\$", lambda m: _convert(m.group(1)), text, flags=re.S)
    text = re.sub(r"(?<!\\)\$(.*?)(?<!\\)\$", lambda m: _convert(m.group(1)), text, flags=re.S)
    if "\\" in text:
        text = _convert(text)
    return _bare_commands(text)


def _prefix_ready(s: str) -> bool:
    """咲夜：这个前缀是否已经是一个能独立转换的完整公式片段。

    不完整的花括号、frac/sqrt 参数、begin/end 环境都先扣着，别急着说出去，
    否则后续文字一到，前面说出去的话就改不回来了。
    """
    depth = 0
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth < 0:
                return False
        i += 1
    if depth:
        return False
    if (len(re.findall(r"\\begin\s*\{", s))
            != len(re.findall(r"\\end\s*\{", s))):
        return False
    for m in re.finditer(r"\\(?:d|t)?frac", s):
        i = m.end()
        for _ in range(2):
            a, i, _bra = _read_token(s, i)
            if a is None:
                return False
    for m in re.finditer(r"\\sqrt", s):
        i = m.end()
        if s[i:i + 1] == "[":
            j = s.find("]", i)
            if j < 0:
                return False
            i = j + 1
        a, i, _bra = _read_token(s, i)
        if a is None:
            return False
    # 模型漏写反斜杠的伪 LaTeX（sqrt{...}/frac{...}）先扣着，等它长成真命令。
    if ("\\" not in s and "$" not in s
            and re.search(r"(?<![A-Za-z])(?:frac|sqrt)\s*\{", s)):
        return False
    return True


class MathStream:
    """流式转换：按「分隔符」切段，整段转换后只吐出新增部分。

    这样既不会把 $...$ 或 sqrt{...} 切成两半，也不会重复输出。
    """

    HOLD = 12
    DELIMS = set(" \n\t，。；：、！？,.;:!?)]}")

    def __init__(self) -> None:
        self.buf = ""
        self.emitted = ""

    @staticmethod
    def _open_dollar(s: str) -> int | None:
        count = 0
        last = -1
        i = 0
        while i < len(s):
            if s[i] == "\\":
                i += 2
                continue
            if s[i] == "$":
                count += 1
                last = i
            i += 1
        return last if count % 2 == 1 else None

    @staticmethod
    def _spans(s: str) -> list[tuple[int, int]]:
        """closed $...$ 的区间，切分时不能切在里面。"""
        spans: list[tuple[int, int]] = []
        i = 0
        open_at = -1
        while i < len(s):
            if s[i] == "\\":
                i += 2
                continue
            if s[i] == "$":
                if open_at < 0:
                    open_at = i
                else:
                    spans.append((open_at, i))
                    open_at = -1
            i += 1
        return spans

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self.buf += chunk
        idx = self._open_dollar(self.buf)
        limit = len(self.buf) if idx is None else idx
        if limit <= self.HOLD:
            return ""
        spans = self._spans(self.buf[:limit])
        full = latex_to_text(self.buf)
        cut = -1
        for i in range(limit - 1, self.HOLD - 1, -1):
            if self.buf[i] not in self.DELIMS:
                continue
            if any(a < i < b for a, b in spans):
                continue
            cand = i + 1
            prefix = self.buf[:cand]
            # 咲夜：只把“完整且当前全文确实是它延长”的那段先说出来。
            if not _prefix_ready(prefix):
                continue
            converted = latex_to_text(prefix)
            if not full.startswith(converted):
                continue
            cut = cand
            break
        if cut <= 0:
            return ""
        converted = latex_to_text(self.buf[:cut])
        if not converted.startswith(self.emitted):
            return ""
        delta = converted[len(self.emitted):]
        self.emitted = converted
        return delta

    def flush(self) -> str:
        converted = latex_to_text(self.buf)
        if not converted.startswith(self.emitted):
            # 已经吐出去的话收不回来；宁可不再补错字，等下次读题重来。
            self.buf = ""
            return ""
        delta = converted[len(self.emitted):]
        self.emitted = converted
        self.buf = ""
        return delta




# ---------------------------------------------------------------- 编辑器输入
# Pearson 公式编辑器的快捷命令（从符号栏按钮的 title 里整理出来）
_EDITOR_MAP = {
    "∞": r"\inf", "∪": r"\cup", "∩": r"\cap", "∅": r"\empty",
    "π": r"\pi", "≤": "<=", "≥": ">=", "≠": "<>",
    "×": r"\times", "÷": r"\divide", "∈": r"\element", "∉": r"\nelement",
    "⊂": r"\subset", "∧": r"\and", "∨": r"\or", "¬": r"\not",
    "Δ": r"\cdelta", "√": r"\sqrt",
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "θ": r"\theta",
    "μ": r"\mu", "σ": r"\sigma", "λ": r"\lambda", "ω": r"\omega",
    "∑": r"\sum", "−": "-", "–": "-", "—": "-", "⋅": "*",
}

_EDITOR_CMD = {
    "infty": r"\inf", "infinity": r"\inf", "inf": r"\inf",
    "cup": r"\cup", "cap": r"\cap",
    "emptyset": r"\empty", "varnothing": r"\empty", "pi": r"\pi",
    "le": "<=", "leq": "<=", "ge": ">=", "geq": ">=", "ne": "<>", "neq": "<>",
    "times": r"\times", "div": r"\divide", "cdot": "*", "pm": "+-",
    "in": r"\element", "notin": r"\nelement", "subset": r"\subset",
    "land": r"\and", "lor": r"\or", "neg": r"\not",
    "Delta": r"\cdelta", "sum": r"\sum", "abs": r"\abs", "sqrt": r"\sqrt",
    "alpha": r"\alpha", "beta": r"\beta", "gamma": r"\gamma", "theta": r"\theta",
    "mu": r"\mu", "sigma": r"\sigma", "lambda": r"\lambda", "omega": r"\omega",
    "left": "", "right": "", "quad": "", "qquad": "", "displaystyle": "",
}

_SIMPLE = re.compile(r"^[A-Za-z0-9.]+$")

# 函数名后面那个空格是**语义分隔**，不能跟着空白一起被删掉。
# 帕秋莉：`sin 2x` 去掉空格就成了 `sin2x`，编辑器会把它读成一个变量名 ——
# 一个空格之差，函数就变成了未知符号。所以先换成哨兵，最后再还回来。
_FUNC_GAP = "\x00"

# 会被「去空白」误伤的函数名（它们后面那个空格是语义分隔）
_FUNC_NAME_RE = re.compile(
    r"(?<![A-Za-z\\])(sin|cos|tan|cot|sec|csc|arcsin|arccos|arctan|"
    r"sinh|cosh|tanh|log|ln|lim|max|min|det|gcd|lcm|exp)"
    r"(?![A-Za-z])([ \t]+)?"
)


def _protect_func_gap(s: str) -> str:
    """把函数名后面的空格换成哨兵，等去完空白再还原。

    帕秋莉：`sin 2x` 一旦被压成 `sin2x`，编辑器会当成一个变量名，
    函数就凭空消失了。这种「一个空格之差」的错最难查。
    """
    return _FUNC_NAME_RE.sub(
        lambda m: m.group(1) + (_FUNC_GAP if m.group(2) else ""), s)

# `\log` / `\ln`：编辑器里**没有这两个命令**。
# 写 `\log` 会插进一个字面反斜杠（真页面 A/B 实测过），括号还会被当成乘号。
# 唯一正确的写法是 `log_6 p`（无反斜杠、括号只用于分组）。
# （灵梦：叫人家名字的时候别带口音，不然对面听不懂你是谁。）
_LOG_PAT = re.compile(r"\\(log|ln)(?![A-Za-z])[ \t]*")

# n 次根：编辑器不认 `\sqrt[4]{2}`，会填成「对 [4] 开平方再乘 (2)」——
# 看着像根号，其实整题全错。一律改写成指数 `(2)^(1/4)`。
_NTH_ROOT_PAT = re.compile(r"\\sqrt[ \t]*\[[ \t]*([^\]]*?)[ \t]*\][ \t]*")


def _editor_nth_root(s: str) -> str:
    """\\sqrt[n]{x} → (x)^(1/n)。

    帕秋莉：四次根不是「根号里写个 4」，那是「先对 4 开平方、再乘后面的东西」。
    既然编辑器不认 n 次根，就用指数写法把这层意思说清楚。
    """
    out: list[str] = []
    pos = 0
    while True:
        m = _NTH_ROOT_PAT.search(s, pos)
        if not m:
            out.append(s[pos:])
            break
        out.append(s[pos:m.start()])
        idx = (m.group(1) or "").strip() or "2"
        a, p, _bra = _read_token(s, m.end())
        if a is None:
            out.append(m.group(0))
            pos = m.end()
            continue
        aa = _editor_nth_root(a)
        out.append("(" + aa + ")^(1/" + idx + ")")
        pos = p
    return "".join(out)


def _editor_log(s: str) -> str:
    """把 \\log / \\ln 改写成编辑器认的 `log_6 p` / `ln x` 形式。

    规则（都是真页面实测换来的）：
    - 底数用下划线：`\\log_{6}(p)` → `log_6 p`；
    - 参数是单个字符时直接跟空格：`ln x`；
    - 参数是括号/花括号包起来的，保留括号分组：`ln (2x+1)`；
    - 参数是裸写的一串（`\\ln 2x`），原样跟空格 —— 千万别给它加括号，
      编辑器会把括号当乘号；
    - 函数名和参数之间那个空格用哨兵占住，别让后面的去空白步骤吃掉。
    """
    out: list[str] = []
    pos = 0
    while True:
        m = _LOG_PAT.search(s, pos)
        if not m:
            out.append(s[pos:])
            break
        out.append(s[pos:m.start()])
        name = m.group(1)
        i = m.end()
        sub = ""
        if s[i:i + 1] == "_":
            i += 1
            if s[i:i + 1] == "{":
                j = s.find("}", i)
                if j < 0:
                    out.append(m.group(0))
                    pos = m.end()
                    continue
                sub = s[i + 1:j].strip()
                i = j + 1
            elif s[i:i + 1] == "(":
                j = s.find(")", i)
                if j < 0:
                    out.append(m.group(0))
                    pos = m.end()
                    continue
                sub = s[i + 1:j].strip()
                i = j + 1
            else:
                j = i
                while j < len(s) and s[j].isalnum():
                    j += 1
                sub = s[i:j]
                i = j
        while i < len(s) and s[i] in " \t":
            i += 1
        grouped = False
        expr = ""
        if i < len(s) and s[i] in "({":
            opener, closer = s[i], ("}" if s[i] == "{" else ")")
            depth = 0
            j = i
            while j < len(s):
                if s[j] == opener:
                    depth += 1
                elif s[j] == closer:
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if j >= len(s):
                out.append(m.group(0))
                pos = m.end()
                continue
            grouped = True
            expr = s[i + 1:j]
            i = j + 1
        elif i < len(s):
            j = i
            while j < len(s) and s[j] not in " \t+-*/^=,;":
                j += 1
            expr = s[i:j]
            i = j
        head = name + (("_" + sub) if sub else "")
        if not expr:
            out.append(head)
            pos = i
            continue
        if len(expr) == 1 and expr.isalnum():
            arg = expr
        elif grouped:
            arg = "(" + expr + ")"
        elif re.search(r"[\\^_/]", expr):
            # 裸写的参数里有命令/分式，必须包起来才不歧义
            arg = "(" + expr + ")"
        else:
            arg = expr
        out.append(head + _FUNC_GAP + arg)
        pos = i
    return "".join(out)


def _paste_log(s: str) -> str:
    """粘贴层的 log/ln：写成常规数学写法 `log_6(p)`，不要留反斜杠。"""
    out: list[str] = []
    pos = 0
    while True:
        m = _LOG_PAT.search(s, pos)
        if not m:
            out.append(s[pos:])
            break
        out.append(s[pos:m.start()])
        name = m.group(1)
        i = m.end()
        sub = ""
        if s[i:i + 1] == "_":
            i += 1
            if s[i:i + 1] == "{":
                j = s.find("}", i)
                if j < 0:
                    out.append(m.group(0))
                    pos = m.end()
                    continue
                sub = s[i + 1:j].strip()
                i = j + 1
            else:
                j = i
                while j < len(s) and s[j].isalnum():
                    j += 1
                sub = s[i:j]
                i = j
        while i < len(s) and s[i] in " \t":
            i += 1
        expr = ""
        if i < len(s) and s[i] in "({":
            opener, closer = s[i], ("}" if s[i] == "{" else ")")
            depth = 0
            j = i
            while j < len(s):
                if s[j] == opener:
                    depth += 1
                elif s[j] == closer:
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            if j >= len(s):
                out.append(m.group(0))
                pos = m.end()
                continue
            expr = s[i + 1:j]
            i = j + 1
        elif i < len(s):
            j = i
            while j < len(s) and s[j] not in " \t+-*/^=,;":
                j += 1
            expr = s[i:j]
            i = j
        head = name + (("_" + sub) if sub else "")
        out.append(head + "(" + expr + ")" if expr else head)
        pos = i
    return "".join(out)


def _editor_frac(s: str) -> str:
    """咲夜：把公式书里的 frac 拆成 Pearson 编辑器认得的 a/b。

    参数用括号配对扫描，不再用 [^{}]*；这样 \\frac{x^{2}}{2} 这类嵌套也能
    正确拆开。分数后面紧跟字母/数字时加括号，避免 1/2x 被读成 1/(2x)。
    """
    pat = re.compile(r"\\(?:d|t)?frac\s*")
    out: list[str] = []
    pos = 0
    while True:
        m = pat.search(s, pos)
        if not m:
            out.append(s[pos:])
            break
        out.append(s[pos:m.start()])
        a, p, _bra = _read_token(s, m.end())
        b = None
        if a is not None:
            b, p, _bra2 = _read_token(s, p)
        if a is None or b is None:
            out.append(m.group(0))
            pos = m.end()
            continue
        aa = _editor_frac(a)
        bb = _editor_frac(b)
        na = aa if _SIMPLE.match(aa) else f"({aa})"
        nb = bb if _SIMPLE.match(bb) else f"({bb})"
        nxt = s[p:p + 1]
        if nxt and (nxt.isalnum() or nxt in "\\("):
            out.append(f"({aa})/({bb})")
        else:
            out.append(f"{na}/{nb}")
        pos = p
    return "".join(out)


def _read_paren(s: str, i: int) -> tuple[str | None, int]:
    """读一个括号参数 `(...)`：返回 (内容, 新位置)；不配对返回 (None, i)。

    帕秋莉：`_read_token` 只认花括号和单字符。可 log/n 次根这些规则会把参数
    写成圆括号，回头再进分式/根号就没人接得住了。
    """
    while i < len(s) and s[i] in " \t":
        i += 1
    if i >= len(s) or s[i] != "(":
        return None, i
    depth = 0
    j = i
    while j < len(s):
        if s[j] == "(":
            depth += 1
        elif s[j] == ")":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return None, i


def _editor_sqrt(s: str) -> str:
    """咲夜：\\sqrt{...} 转成编辑器命令；参数同样用括号配对扫描。"""
    pat = re.compile(r"\\sqrt\s*")
    out: list[str] = []
    pos = 0
    while True:
        m = pat.search(s, pos)
        if not m:
            out.append(s[pos:])
            break
        out.append(s[pos:m.start()])
        i = m.end()
        if s[i:i + 1] == "[":
            # n 次根已经在上一步被换成指数写法了；真的漏到这里就原样留着
            out.append(m.group(0))
            pos = i
            continue
        # 参数可能是 `{...}`（LaTeX 写法），也可能是 `(...)`（我们自己上一步写出来的）
        a = None
        p = i
        if s[i:i + 1] == "(":
            a, p = _read_paren(s, i)
        if a is None:
            a, p, _bra = _read_token(s, i)
        if a is None:
            out.append(m.group(0))
            pos = i
            continue
        aa = _editor_sqrt(a)
        # 一律写成 `\sqrt(...)`：这是真页面验证过的形式。
        # 帕秋莉：`\sqrt3` 这种省括号的写法只在逐字敲的时候成立；整段插进去时
        # 编辑器不一定把 3 收进根号里，宁可多写一对括号。
        out.append(r"\sqrt(" + aa + ")")
        pos = p
    return "".join(out)


def _fix_log_base(text: str) -> str:
    """把 `log7(5)` 修成编辑器认的 `log_7(5)`。

    模型经常省掉下划线；Pearson 的公式编辑器会把 `log7` 解释成
    “log × 7”，于是 `log7(5)+log7(k)` 看起来对、Check 却判错
    （2026-11-28 Q10 Part 2 实测）。只处理“log + 数字 + 左括号”，
    不动已经带下划线、或 `log(x)` 这种无底数写法。
    """
    return re.sub(r"\b(log)\s*(\d+)\s*(?=\()", r"\1_\2", text, flags=re.I)


def to_editor_input(text: str) -> str:
    """把模型答案转成 Pearson 公式编辑器能识别的输入串。

    - ∞ -> \\inf，∪ -> \\cup，≤ -> <=，≠ -> <>
    - \\log_{b}(x) -> log_b x（编辑器没有 \\log 命令，见 `_editor_log`）
    - \\sqrt[n]{x} -> (x)^(1/n)（编辑器不认 n 次根）
    - \\frac{a}{b} -> a/b（真分数），\\sqrt{3} -> \\sqrt(3)
    - x^{n+1} -> x^(n+1)，x^2 保持 ^ 形式
    """
    if not text:
        return ""
    s = text.strip().replace("$", "")
    s = s.replace("−", "-").replace("–", "-").replace("—", "-")
    s = s.replace("\\left", "").replace("\\right", "")
    s = _fix_log_base(s)
    # 咲夜：先处理 log/ln 和 n 次根——它们的参数里可能还套着分式，顺序反了就拆不开。
    s = _editor_log(s)
    s = _editor_nth_root(s)
    # 咲夜：再把上标/下标拆成括号，然后处理根号和分式，嵌套才不会互相绊脚。
    s = re.sub(r"\^\{([^{}]*)\}", lambda m: "^(" + m.group(1) + ")", s)
    s = re.sub(r"_\{([^{}]*)\}", lambda m: "_(" + m.group(1) + ")", s)
    s = _editor_sqrt(s)
    s = _editor_frac(s)
    # 分式/根号内部可能还有一层上标，再补一次。
    s = re.sub(r"\^\{([^{}]*)\}", lambda m: "^(" + m.group(1) + ")", s)
    # 负指数/负分母必须加括号；指数只吃一个 token，不能跨过隐式乘法。
    s = re.sub(r"\^(-)(\d+(?:\.\d+)?|[A-Za-z])", r"^(-\2)", s)
    s = re.sub(r"/(-)(\d+(?:\.\d+)?|[A-Za-z])", r"/(-\2)", s)
    s = re.sub(r"\\(?:text|textrm|mathrm|operatorname|mbox)\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\([A-Za-z]+)", lambda m: _EDITOR_CMD.get(m.group(1), m.group(1)), s)
    s = re.sub(r"\\[^A-Za-z]", "", s)
    s = "".join(_EDITOR_MAP.get(ch, ch) for ch in s)
    # 函数名后面那个空格是语义分隔，先换成哨兵，别让去空白步骤吃掉。
    s = _protect_func_gap(s)
    if re.search(r"[0-9()+\-*/^<>=,]", s):
        s = re.sub(r"\s+", "", s)
    return s.replace(_FUNC_GAP, " ")


_PASTE_CMD = {
    "infty": "∞", "infinity": "∞", "inf": "∞", "cup": "∪", "cap": "∩", "emptyset": "∅",
    "varnothing": "∅", "pi": "π", "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥",
    "ne": "≠", "neq": "≠", "approx": "≈", "equiv": "≡", "sim": "∼", "propto": "∝",
    "times": "×", "div": "÷", "cdot": "·", "pm": "±",
    "in": "∈", "notin": "∉", "subset": "⊂", "subseteq": "⊆", "supset": "⊃",
    "land": "∧", "lor": "∨", "neg": "¬",
    "Delta": "Δ", "sum": "∑", "prod": "∏", "int": "∫", "sqrt": "√",
    "partial": "∂", "nabla": "∇", "angle": "∠", "perp": "⊥", "parallel": "∥",
    "to": "→", "rightarrow": "→", "leftarrow": "←", "Rightarrow": "⇒",
    "leftrightarrow": "↔", "mapsto": "↦",
    "cdots": "⋯", "ldots": "…", "dots": "…",
    "sin": "sin", "cos": "cos", "tan": "tan", "sec": "sec", "csc": "csc",
    "cot": "cot", "arcsin": "arcsin", "arccos": "arccos", "arctan": "arctan",
    "log": "log", "ln": "ln", "lim": "lim", "max": "max", "min": "min",
    "sup": "sup", "det": "det", "exp": "exp", "gcd": "gcd", "lcm": "lcm",
    "alpha": "α", "beta": "β", "gamma": "γ", "theta": "θ", "mu": "μ",
    "sigma": "σ", "lambda": "λ", "omega": "ω", "phi": "φ", "rho": "ρ",
    "tau": "τ", "epsilon": "ε",
    "left": "", "right": "", "quad": "", "qquad": "", "displaystyle": "",
}


def _paste_sqrt(s: str) -> str:
    """咲夜：粘贴层用的根号转换，支持 n 次根，参数用括号配对扫描。"""
    pat = re.compile(r"\\sqrt\s*")
    out: list[str] = []
    pos = 0
    while True:
        m = pat.search(s, pos)
        if not m:
            out.append(s[pos:])
            break
        out.append(s[pos:m.start()])
        i = m.end()
        idx = ""
        if s[i:i + 1] == "[":
            j = s.find("]", i)
            if j < 0:
                out.append(m.group(0))
                pos = i
                continue
            idx = s[i + 1:j]
            i = j + 1
        a, p, _bra = _read_token(s, i)
        if a is None:
            out.append(m.group(0))
            pos = i
            continue
        aa = _paste_sqrt(a)
        out.append((_script(idx, SUP) if idx else "") + "√(" + aa + ")")
        pos = p
    return "".join(out)


def _paste_frac(s: str) -> str:
    """咲夜：粘贴层的 \\frac{a}{b} → (a)/(b)；无花括号的 \\frac12 → 1/2。"""
    pat = re.compile(r"\\(?:d|t)?frac\s*")
    out: list[str] = []
    pos = 0
    while True:
        m = pat.search(s, pos)
        if not m:
            out.append(s[pos:])
            break
        out.append(s[pos:m.start()])
        a, p, bra_a = _read_token(s, m.end())
        b = None
        bra_b = False
        if a is not None:
            b, p, bra_b = _read_token(s, p)
        if a is None or b is None:
            out.append(m.group(0))
            pos = m.end()
            continue
        aa = _paste_frac(a)
        bb = _paste_frac(b)
        if bra_a and bra_b:
            out.append(f"({aa})/({bb})")
        else:
            out.append(f"{aa}/{bb}")
        pos = p
    return "".join(out)


def to_paste_input(text: str) -> str:
    """给编辑器「粘贴」用的字符串：用真正的数学符号（∞、∪、√…），不用 \\inf 这类快捷键。

    Pearson 的编辑器在粘贴时会自己解析 ^ 和 /，但不认识 \\inf 这种命令，会原样显示。
    """
    s = (text or "").strip().replace("$", "")
    s = s.replace("−", "-").replace("–", "-").replace("—", "-")
    s = s.replace("\\left", "").replace("\\right", "")
    s = _fix_log_base(s)
    # 咲夜：先收 log/ln，参数里可能还套着分式，顺序反了就拆不开。
    s = _paste_log(s)
    # 咲夜：先上标、再根号、最后分式；嵌套的根号和分式才不会被拆坏。
    s = re.sub(r"\^\{([^{}]*)\}", r"^(\1)", s)
    s = _paste_sqrt(s)
    s = _paste_frac(s)
    # 分式/根号内部可能还有一层上标，再补一次。
    s = re.sub(r"\^\{([^{}]*)\}", r"^(\1)", s)
    # 负指数/负分母必须加括号；指数只吃一个 token，不跨过隐式乘法。
    s = re.sub(r"\^(-)(\d+(?:\.\d+)?|[A-Za-z])", r"^(-\2)", s)
    s = re.sub(r"/(-)(\d+(?:\.\d+)?|[A-Za-z])", r"/(-\2)", s)
    s = re.sub(r"\\(?:text|textrm|mathrm|operatorname|mbox)\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\([A-Za-z]+)", lambda m: _PASTE_CMD.get(m.group(1), ""), s)
    s = re.sub(r"\\[^A-Za-z]", "", s)
    s = re.sub(r"(?<![A-Za-z])inf(?:inity)?(?![A-Za-z])", "∞", s)
    # 函数名后的空格同样要保住（粘贴时压成 sin2x 也会被读成变量名）
    s = _protect_func_gap(s)
    if re.search(r"[0-9()+\-*/^<>=,]", s):
        s = re.sub(r"\s+", "", s)
    return s.replace(_FUNC_GAP, " ")

def aria_to_plain(text: str) -> str:
    """把 Pearson 的「朗读式」文本翻回数学写法。

    帕秋莉：编辑器回读给我的不是公式，是**念出来的句子**——
    `6500 equals 5000 left parenthesis 1 plus StartFraction r Over m EndFraction
    right parenthesis Superscript left parenthesis 6 m right parenthesis`。
    拿它跟原文比对永远不相等，于是明明填对了也会被判「没填进去」，
    再退回粘贴、把结构搞坏。所以先翻译再比。
    """
    s = str(text or "").replace("\u200b", "")
    # 分式：`StartFraction a Over b EndFraction` → `(a)/(b)`（多跑几轮，尽量吃掉嵌套）
    for _ in range(3):
        new = re.sub(r"StartFraction\s*(.*?)\s*Over\s*(.*?)\s*EndFraction",
                     lambda m: "(" + m.group(1) + ")/(" + m.group(2) + ")",
                     s, flags=re.S)
        if new == s:
            break
        s = new
    # 有些回读会把 EndFraction 省掉（分式正好在右括号前结束时就是这样）：
    # `StartFraction r Over m right parenthesis` → `(r)/(m)` 后面跟着 `)`。
    s = re.sub(r"StartFraction\s*(.*?)\s*Over\s*(.*?)"
               r"(?=\s*(?:EndFraction|right parenthesis|Superscript|Subscript|$))",
               lambda m: "(" + m.group(1) + ")/(" + m.group(2) + ")",
               s, flags=re.S)
    s = re.sub(r"\bSuperscript\s*(?:Baseline\s*)?", "^", s)
    s = re.sub(r"\bSubscript\s*", "_", s)
    s = re.sub(r"\bBaseline\b", "", s)
    s = re.sub(r"\bleft parenthesis\b", "(", s)
    s = re.sub(r"\bright parenthesis\b", ")", s)
    s = re.sub(r"\bleft bracket\b", "[", s)
    s = re.sub(r"\bright bracket\b", "]", s)
    s = re.sub(r"\bnegative\s+", "-", s)
    s = re.sub(r"\bpositive\s+", "", s)
    s = re.sub(r"\bdivided by\b", "/", s)
    s = re.sub(r"\btimes\b", "*", s)
    s = re.sub(r"\bequals\b", "=", s)
    s = re.sub(r"\bplus\b", "+", s)
    s = re.sub(r"\bminus\b", "-", s)
    s = re.sub(r"\bsquared\b", "^2", s)
    s = re.sub(r"\bcubed\b", "^3", s)
    s = re.sub(r"\bcomma\b", ",", s)
    s = re.sub(r"\binfinity\b", "∞", s)
    s = re.sub(r"\bpi\b", "π", s)
    s = re.sub(r"\s+", "", s)
    return s


def normalize_answer(text: str) -> str:
    """把答案归一化后用于比较（不改变真正填进去的内容）。

    - 去空白、去 "$"
    - 统一 Unicode 负号
    - 去掉 "x=" / "y=" 之类的变量前缀
    - 去掉末尾的 ".0"
    """
    s = (text or "").strip().replace("$", "")
    s = s.replace("−", "-").replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", "", s).lower()
    s = re.sub(r"^[a-z]\s*=\s*", "", s)
    if re.fullmatch(r"-?\d+\.0+", s):
        s = s.rstrip("0").rstrip(".")
    return s
