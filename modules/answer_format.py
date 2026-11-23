"""按题目要求整理答案格式（小数位、分数、有序对、百分数等）。

模型经常把数学算对、格式写错，导致 Pearson 判错。这里只做轻量、可逆的
格式整理，不改变数值本身。
"""
from __future__ import annotations

import re
from fractions import Fraction

from modules.verify_math import normalize_text, parse_number, parse_number_exact

_DECIMAL_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def infer_format(question_text: str, field_label: str = "") -> dict:
    """从题干/字段标签推断答案格式。返回 dict，format 为 ordered_pair 等。"""
    text = (str(field_label or "") + "\n" + str(question_text or ""))
    low = normalize_text(text).lower()
    fmt: dict = {"kind": "auto", "decimals": None, "percent": False}

    if re.search(r"ordered pair|\(x\s*,\s*y\)|coordinate pair|as an ordered",
                 low):
        fmt["kind"] = "ordered_pair"
    elif re.search(r"\bvertex\b", low):
        fmt["kind"] = "ordered_pair"
    elif re.search(r"\bpoint\b|\bcoordinates?\b", low):
        fmt["kind"] = "ordered_pair"

    m = re.search(r"(?:round|rounding|rounded)\s+(?:to\s+)?(?:the\s+)?"
                  r"(?:nearest\s+)?(\d+|one|two|three|four|five|six)\s+"
                  r"decimal\s+place", low)
    if not m:
        m = re.search(r"(?:to|with)\s+(\d+|one|two|three|four|five|six)\s+"
                      r"decimal\s+place", low)
    if m:
        raw = m.group(1)
        fmt["decimals"] = int(raw) if raw.isdigit() else _DECIMAL_WORDS.get(raw)
    else:
        m = re.search(r"nearest\s+(tenth|hundredth|thousandth|"
                      r"ten[- ]?thousandth)", low)
        if m:
            fmt["decimals"] = {"tenth": 1, "hundredth": 2, "thousandth": 3,
                               "ten-thousandth": 4, "ten thousandth": 4}.get(
                                   m.group(1).replace("-", " ").replace(" ", "-"),
                                   {"tenth": 1, "hundredth": 2,
                                    "thousandth": 3}.get(m.group(1)))

    # 只有题目明确要求“写成百分数”时才把小数乘 100；题面里出现 % 数据
    # （例如税率）不代表答案要转换。
    if re.search(r"(?:write|express|convert|enter|give)\b.{0,40}\bpercent\b", low) \
            or re.search(r"\b(?:as|in)\s+(?:a\s+)?percent\b", low) \
            or re.search(r"\bpercent(?:age)?\s+notation\b", low) \
            or re.search(r"\bwhat\s+percent\b", low) \
            or "%" in str(field_label or ""):
        fmt["percent"] = True

    if re.search(r"\bfraction\b|simplest form|lowest terms|mixed number", low):
        fmt["kind"] = "fraction" if fmt["kind"] == "auto" else fmt["kind"]
    if re.search(r"whole number|integer", low) and fmt["decimals"] is None:
        fmt["kind"] = "integer" if fmt["kind"] == "auto" else fmt["kind"]
    return fmt


def _fmt_num(value: float, fmt: dict) -> str:
    if fmt.get("percent"):
        value = value * 100.0
    d = fmt.get("decimals")
    if d is not None:
        s = f"{value:.{int(d)}f}"
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

    # 模型已经写成 25% 时不要再乘 100
    had_percent = s.rstrip().endswith("%")
    exact = _as_exact(s)
    if exact is not None:
        num = float(exact)
        if kind == "fraction" and exact.denominator != 1:
            # 题目要求分数时不要强行转小数
            return f"{exact.numerator}/{exact.denominator}"
        if had_percent:
            return _fmt_num(num, dict(fmt, percent=False)) + "%"
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
