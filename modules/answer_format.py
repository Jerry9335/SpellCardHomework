"""按题目要求整理答案格式（小数位、分数、有序对、百分数等）。

模型经常把数学算对、格式写错，导致 Pearson 判错。这里只做轻量、可逆的
格式整理，不改变数值本身。
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from fractions import Fraction

from modules.verify_math import normalize_text, parse_number, parse_number_exact

_DECIMAL_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def infer_format(question_text: str, field_label: str = "") -> dict:
    """咲夜：从题干/字段标签推断答案格式，时间要花在刀刃上。"""
    text = (str(field_label or "") + "\n" + str(question_text or ""))
    # 小数位必须看原文：normalize_text 会把 ten 换成 10，ten-thousandth 会失踪。
    plain = text.lower()
    low = normalize_text(text).lower()
    fmt: dict = {"kind": "auto", "decimals": None, "percent": False,
                 "percent_scale": False, "decimal_required": False,
                 "fraction_preferred": False, "no_simplify": False}

    if re.search(r"ordered pair|\(x\s*,\s*y\)|coordinate pair|as an ordered",
                 low):
        fmt["kind"] = "ordered_pair"
    elif re.search(r"\bvertex\b", low):
        fmt["kind"] = "ordered_pair"
    elif re.search(r"\bpoint\b|\bcoordinates?\b", low):
        fmt["kind"] = "ordered_pair"

    m = re.search(r"(?:round|rounding|rounded)\s+(?:to\s+)?(?:the\s+)?"
                  r"(?:nearest\s+)?(\d+|one|two|three|four|five|six)\s+"
                  r"decimal\s+place", plain)
    if not m:
        m = re.search(r"(?:to|with)\s+(\d+|one|two|three|four|five|six)\s+"
                      r"decimal\s+place", plain)
    if m:
        raw = m.group(1)
        fmt["decimals"] = int(raw) if raw.isdigit() else _DECIMAL_WORDS.get(raw)
    else:
        m = re.search(r"nearest\s+(tenth|hundredth|thousandth|"
                      r"ten[- ]?thousandth)", plain)
        if m:
            fmt["decimals"] = {"tenth": 1, "hundredth": 2, "thousandth": 3,
                               "ten-thousandth": 4, "ten thousandth": 4}.get(
                                   m.group(1).replace("-", " ").replace(" ", "-"),
                                   {"tenth": 1, "hundredth": 2,
                                    "thousandth": 3}.get(m.group(1)))

    # 咲夜：只有“把小数写成百分数”才需要 ×100；题目问 what percent 时，
    # 式神给的 25 就是 25%，再乘就把答案写成 2500 了。
    scale_phrase = bool(
        re.search(r"(?:write|express|convert|enter|give)\b.{0,40}\bpercent\b", plain)
        or re.search(r"\b(?:as|in)\s+(?:a\s+)?percent\b", plain)
        or re.search(r"\bpercent(?:age)?\s+notation\b", plain))
    ask_percent = bool(re.search(r"\bwhat\s+percent\b", plain))
    label_percent = "%" in str(field_label or "")
    fmt["percent"] = bool(scale_phrase or ask_percent or label_percent)
    fmt["percent_scale"] = bool(scale_phrase and not ask_percent)
    # “as a decimal / decimal form / decimal answer” 才强制转小数；
    # 只有 “Simplify your answer” 时，Pearson 往往要精确分数（Q15 实测 2/3）。
    fmt["decimal_required"] = bool(re.search(
        r"\b(?:as|in)\s+(?:a\s+)?decimal\b|\bdecimal\s+(?:form|answer|approximation|number)\b",
        plain))
    fmt["no_simplify"] = bool(re.search(
        r"do\s+not\s+simplify|don'?t\s+simplify|not\s+to\s+simplify|"
        r"不化简|不要化简|不用化简", plain))
    fmt["fraction_preferred"] = bool(
        re.search(r"\bsimplif(?:y|ied)\b|\bexact\b|\bfraction\b|\bsimplest form\b", plain)
        and not fmt["decimal_required"] and not fmt["no_simplify"])

    if re.search(r"\bfraction\b|simplest form|lowest terms|mixed number", plain):
        fmt["kind"] = "fraction" if fmt["kind"] == "auto" else fmt["kind"]
    if re.search(r"whole number|integer", plain) and fmt["decimals"] is None:
        fmt["kind"] = "integer" if fmt["kind"] == "auto" else fmt["kind"]
    return fmt


def _fmt_num(value: float, fmt: dict) -> str:
    # 咲夜：只有“无量纲小数/分数且量级在 [0,1]”才当作比例乘 100。
    if fmt.get("percent") and fmt.get("percent_scale") and abs(value) <= 1.0 + 1e-12:
        value = value * 100.0
    d = fmt.get("decimals")
    if d is not None:
        d = int(d)
        try:
            step = Decimal(1).scaleb(-d) if d else Decimal(1)
            dec = Decimal(str(value)).quantize(step, rounding=ROUND_HALF_UP)
            s = format(dec, "f")
        except (InvalidOperation, ValueError):
            s = f"{value:.{d}f}"
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s or "0"
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    # 保留一个合理精度，避免 float 噪声
    s = f"{value:.10f}".rstrip("0").rstrip(".")
    return s or "0"


def _as_exact(value):
    exact = parse_number_exact(value)
    if exact is not None:
        return exact
    return None


def format_value(value, fmt: dict) -> str:
    """格式化单个值。无法识别时原样返回。"""
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    kind = (fmt or {}).get("kind", "auto")

    if kind == "ordered_pair":
        s = s.strip().strip("()[]{} ")
        s = re.sub(r"^(?:x|y)\s*=\s*", "", s, flags=re.I)
        parts = [p.strip() for p in re.split(r"[,;]", s) if p.strip()]
        if len(parts) == 2:
            a = parse_number(parts[0])
            b = parse_number(parts[1])
            if a is not None and b is not None:
                return f"({_fmt_num(a, fmt)},{_fmt_num(b, fmt)})"

    # 题目明确说 Do not simplify 时，保留原始分数写法（5/10 不要约成 1/2）。
    if fmt.get("no_simplify"):
        m_frac = re.fullmatch(r"\s*([+-]?\d+)\s*/\s*([+-]?\d+)\s*", s)
        if m_frac:
            return f"{int(m_frac.group(1))}/{int(m_frac.group(2))}"

    # 模型已经写成 25% 时不要再乘 100
    had_percent = s.rstrip().endswith("%")
    exact = _as_exact(s)
    if exact is not None:
        num = float(exact)
        if had_percent:
            return _fmt_num(num, dict(fmt, percent=False)) + "%"
        _keep_fraction = (
            exact.denominator != 1
            and kind != "integer"
            and fmt.get("decimals") is None
            and not fmt.get("decimal_required")
            and not fmt.get("percent_scale")
            and ("/" in s or fmt.get("fraction_preferred"))
        )
        if _keep_fraction:
            # 题目没有明确要小数时保留精确分数（2/3 不要写成 0.6666666667）。
            # 模型如果给的是 0.6666666667，先尝试收成 2/3；收不成再退回小数，
            # 免得把 0.123456789 写成 123456789/1000000000 这种怪分数。
            if "/" not in s:
                simp = exact.limit_denominator(1000)
                if abs(float(simp) - num) <= 1e-9:
                    exact = simp
                else:
                    return _fmt_num(num, fmt)
            return f"{exact.numerator}/{exact.denominator}"
        if kind == "fraction" and exact.denominator != 1:
            return f"{exact.numerator}/{exact.denominator}"
        return _fmt_num(num, fmt)

    # 已经是表达式/带单位的答案：只清理多余空格和句号
    s = normalize_text(s)
    s = re.sub(r"\s*([,;])\s*", r"\1 ", s).strip()
    return s.rstrip("。.")


def format_values(values: list, question_text: str,
                  labels: list[str] | None = None) -> list[str]:
    out = []
    labels = labels or []
    for i, v in enumerate(values or []):
        label = labels[i] if i < len(labels) else (labels[0] if len(labels) == 1 else "")
        fmt = infer_format(question_text, label)
        out.append(format_value(v, fmt))
    return out


def format_ordered_pair(value) -> str:
    return str(format_value(value, {"kind": "ordered_pair", "decimals": None,
                                    "percent": False}))


def fraction_text(value) -> str:
    exact = parse_number_exact(value)
    if exact is not None and exact.denominator != 1:
        return f"{exact.numerator}/{exact.denominator}"
    return str(value)
