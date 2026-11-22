"""把模型输出的 LaTeX 转成人能直接看的数学符号。

只做「够用就好」的转换：希腊字母、常用运算符、上下标、根号、分式、矩阵、箭头。
不追求排版完美，目标是让人在文本框里一眼看懂，而不是看到 $\\frac{a}{b}$ 这种源码。

流式场景用 MathStream：它会等一个 $...$ 收尾了才转换，避免把半个公式切坏。
"""
from __future__ import annotations
import re

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
        cut = -1
        for i in range(limit - 1, self.HOLD - 1, -1):
            if self.buf[i] not in self.DELIMS:
                continue
            if any(a < i < b for a, b in spans):
                continue
            cut = i + 1
            break
        if cut <= 0:
            return ""
        converted = latex_to_text(self.buf[:cut])
        delta = converted[len(self.emitted):]
        self.emitted = converted
        return delta

    def flush(self) -> str:
        converted = latex_to_text(self.buf)
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
    "infty": r"\inf", "infinity": r"\inf", "cup": r"\cup", "cap": r"\cap",
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


def _editor_frac(s: str) -> str:
    pat = re.compile(r"\\(?:d|t)?frac\{([^{}]*)\}\{([^{}]*)\}")
    while True:
        def rep(m):
            a, b = m.group(1).strip(), m.group(2).strip()
            if _SIMPLE.match(a) and _SIMPLE.match(b):
                return f"{a}/{b}"
            return f"({a})/({b})"

        new = pat.sub(rep, s)
        if new == s:
            return s
        s = new


def _editor_sqrt(s: str) -> str:
    pat = re.compile(r"\\sqrt\{([^{}]*)\}")
    while True:
        def rep(m):
            a = m.group(1).strip()
            return r"\sqrt" + a if re.match(r"^[A-Za-z0-9.]$", a) else r"\sqrt(" + a + ")"

        new = pat.sub(rep, s)
        if new == s:
            return s
        s = new


def to_editor_input(text: str) -> str:
    """把模型答案转成 Pearson 公式编辑器能识别的输入串。

    - ∞ -> \\inf，∪ -> \\cup，≤ -> <=，≠ -> <>
    - \\frac{a}{b} -> a/b（真分数），\\sqrt{3} -> \\sqrt3
    - x^{n+1} -> x^(n+1)，x^2 保持 ^ 形式
    """
    if not text:
        return ""
    s = text.strip().replace("$", "")
    s = s.replace("\\left", "").replace("\\right", "")
    s = _editor_frac(s)
    s = _editor_sqrt(s)
    s = re.sub(r"\^\{([^{}]*)\}", lambda m: "^(" + m.group(1) + ")", s)
    s = re.sub(r"_\{([^{}]*)\}", lambda m: "_(" + m.group(1) + ")", s)
    s = re.sub(r"\\([A-Za-z]+)", lambda m: _EDITOR_CMD.get(m.group(1), m.group(1)), s)
    s = re.sub(r"\\[^A-Za-z]", "", s)
    s = "".join(_EDITOR_MAP.get(ch, ch) for ch in s)
    if re.search(r"[0-9()+\-*/^<>=,]", s):
        s = re.sub(r"\s+", "", s)
    return s


_PASTE_CMD = {
    "infty": "∞", "infinity": "∞", "inf": "∞", "cup": "∪", "cap": "∩", "emptyset": "∅",
    "varnothing": "∅", "pi": "π", "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥",
    "ne": "≠", "neq": "≠", "times": "×", "div": "÷", "cdot": "·", "pm": "±",
    "in": "∈", "notin": "∉", "subset": "⊂", "land": "∧", "lor": "∨", "neg": "¬",
    "Delta": "Δ", "sum": "∑", "sqrt": "√", "alpha": "α", "beta": "β",
    "gamma": "γ", "theta": "θ", "mu": "μ", "sigma": "σ", "lambda": "λ",
    "omega": "ω", "left": "", "right": "", "quad": "", "qquad": "",
    "displaystyle": "",
}


def to_paste_input(text: str) -> str:
    """给编辑器「粘贴」用的字符串：用真正的数学符号（∞、∪、√…），不用 \\inf 这类快捷键。

    Pearson 的编辑器在粘贴时会自己解析 ^ 和 /，但不认识 \\inf 这种命令，会原样显示。
    """
    s = (text or "").strip()
    s = s.replace("−", "-").replace("–", "-").replace("—", "-")
    s = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", lambda m: f"({m.group(1)})/({m.group(2)})", s)
    s = re.sub(r"\\sqrt\{([^{}]*)\}", lambda m: "√(" + m.group(1) + ")", s)
    s = re.sub(r"\\([A-Za-z]+)", lambda m: _PASTE_CMD.get(m.group(1), ""), s)
    s = re.sub(r"\\[^A-Za-z]", "", s)
    s = re.sub(r"(?<![A-Za-z])inf(?:inity)?(?![A-Za-z])", "∞", s)
    if re.search(r"[0-9()+\-*/^<>=,]", s):
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
