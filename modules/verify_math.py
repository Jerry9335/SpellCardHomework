"""本地数学验算：把模型答案代入题目关系，尽量不靠模型自说自话。

这里只做“能可靠判定”的验算；无法判断时返回 skip，让上层继续用投票/审核
的结果。所有函数都无副作用，方便单元测试和离线回归。
"""
from __future__ import annotations

import re
from fractions import Fraction

_NUM_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
}


def normalize_text(text: str) -> str:
    """把数学题里常见的 OCR/公式写法统一成便于解析的形式。"""
    s = str(text or "")
    s = s.replace("\u200b", "").replace("\xa0", " ")
    s = (s.replace("−", "-").replace("–", "-").replace("—", "-")
         .replace("×", "*").replace("·", "*").replace("÷", "/")
         .replace("²", "^2").replace("³", "^3"))
    s = re.sub(r"\*\*", "^", s)
    s = re.sub(r"\bnegative\s+", "-", s, flags=re.I)
    s = re.sub(r"\bminus\s+", "-", s, flags=re.I)
    s = re.sub(r"\bplus\s+", "+", s, flags=re.I)
    s = re.sub(r"\bnegative\b", "-", s, flags=re.I)
    s = re.sub(r"\bminus\b", "-", s, flags=re.I)
    s = re.sub(r"\bplus\b", "+", s, flags=re.I)
    s = re.sub(r"\bsquared\b", "^2", s, flags=re.I)
    s = re.sub(r"\bto the power of\s+2\b", "^2", s, flags=re.I)
    s = re.sub(r"\bequals?\b", "=", s, flags=re.I)
    s = re.sub(r"\btimes\b", "*", s, flags=re.I)
    # 数字单词（只在独立单词时替换，避免把 "one" 嵌进别的词）
    def _word(m):
        return str(_NUM_WORDS[m.group(1).lower()])

    s = re.sub(r"\b(" + "|".join(_NUM_WORDS) + r")\b", _word, s, flags=re.I)
    return s


def _trim_math(expr: str) -> str:
    """从一段文字里截取数学表达式部分，去掉句号/单位/后续说明。"""
    s = str(expr or "").strip()
    # 去掉题号/前缀，比如 "(a) "、"Find "
    s = re.sub(r"^[\(\[]?[a-hA-H][\)\].:]\s*", "", s)
    # 表达式允许的字符；x 是自变量，允许字母 y 只在开头标签里（已被剥离）
    start = None
    for i, ch in enumerate(s):
        if ch.isdigit() or ch in "+-.xX(":
            start = i
            break
    if start is None:
        return ""
    s = s[start:]
    out = []
    for ch in s:
        if ch in "0123456789xX+-*/().^ ":
            out.append(ch)
        else:
            break
    s = "".join(out).strip()
    # 去掉不成对的尾部运算符/括号
    s = s.rstrip("+-*/(.^ ")
    return s


def parse_number(value) -> float | None:
    """解析数字/分数/百分数；解析失败返回 None。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    s = normalize_text(s)
    s = s.replace(",", "").replace("$", "").replace("%", "")
    s = re.sub(r"^(?:x|y|f\s*\(\s*x\s*\)|g\s*\(\s*x\s*\))\s*=\s*", "", s,
               flags=re.I).strip()
    s = s.strip("()[]{} ")
    # 带分数：1 1/2
    m = re.fullmatch(r"([+-]?\d+)\s+(\d+)\s*/\s*(\d+)", s)
    if m:
        try:
            whole = int(m.group(1))
            frac = Fraction(int(m.group(2)), int(m.group(3)))
            return float(whole + (frac if whole >= 0 else -frac))
        except Exception:
            return None
    # 分数 a/b
    m = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*/\s*([+-]?\d+(?:\.\d+)?)", s)
    if m:
        try:
            den = float(m.group(2))
            return float(m.group(1)) / den if den else None
        except Exception:
            return None
    # 普通数字（允许尾随单位/说明）
    m = re.match(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))", s)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            return None
    return None


def parse_number_exact(value) -> Fraction | None:
    """尽量保留分数的精确值，用于投票归一化和精确验算。"""
    if value is None:
        return None
    if isinstance(value, (int, Fraction)):
        return Fraction(value)
    if isinstance(value, float):
        return Fraction(value).limit_denominator(10 ** 6)
    s = normalize_text(str(value)).strip()
    s = s.replace(",", "").replace("$", "").replace("%", "")
    s = re.sub(r"^(?:x|y|f\s*\(\s*x\s*\))\s*=\s*", "", s, flags=re.I).strip()
    s = s.strip("()[]{} ")
    m = re.fullmatch(r"([+-]?\d+)\s+(\d+)\s*/\s*(\d+)", s)
    if m:
        whole = int(m.group(1))
        frac = Fraction(int(m.group(2)), int(m.group(3)))
        return whole + (frac if whole >= 0 else -frac)
    m = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)\s*/\s*([+-]?\d+(?:\.\d+)?)", s)
    if m:
        try:
            return Fraction(m.group(1)) / Fraction(m.group(2))
        except Exception:
            return None
    m = re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", s)
    if m:
        try:
            return Fraction(s)
        except Exception:
            return None
    return None


def parse_poly(expr: str):
    """解析一次/二次多项式，返回 (a, b, c)，ax^2+bx+c。

    支持缺失项、负系数、分数、``squared``/``minus`` 等写法；失败返回 None。
    """
    s = normalize_text(expr)
    # 去掉 y= / R(x)= / f(x)= 等标签；只取等号右边
    if "=" in s:
        s = s.split("=")[-1]
    s = _trim_math(s)
    if not s:
        return None
    s = re.sub(r"\s+", "", s).replace("*", "")
    s = s.replace("^2", "²")
    if "^" in s:
        return None
    s = re.sub(r"([a-zA-Z])2\b", r"\1²", s)  # OCR 的 x2 -> x²
    s = s.replace("x2", "x²")
    if any(ch not in "0123456789xX²+-/." for ch in s):
        return None
    def _coef(text: str):
        text = text.strip()
        if text in ("", "+"):
            return 1.0
        if text == "-":
            return -1.0
        try:
            return float(Fraction(text))
        except Exception:
            return None

    # 拆成项：把所有减号变成 +-，再按 + 切
    parts = s.replace("-", "+-").split("+")
    a = b = c = 0.0
    for raw in parts:
        term = raw.strip()
        if not term:
            continue
        if "x²" in term:
            coef = _coef(term.replace("x²", ""))
            if coef is None:
                return None
            a += coef
        elif "x" in term:
            coef = _coef(term.replace("x", ""))
            if coef is None:
                return None
            b += coef
        else:
            try:
                c += float(Fraction(term))
            except Exception:
                return None
    return a, b, c


def poly_eval(poly, x: float) -> float:
    a, b, c = poly
    return a * x * x + b * x + c


def poly_features(poly) -> dict:
    """返回二次/一次函数的顶点、截距、根、斜率等特征。"""
    a, b, c = poly
    out = {"a": a, "b": b, "c": c, "vertex": None, "y_intercept": (0.0, c),
           "x_intercepts": [], "slope": b}
    if abs(a) > 1e-12:
        vx = -b / (2 * a)
        out["vertex"] = (vx, poly_eval(poly, vx))
        disc = b * b - 4 * a * c
        if disc >= -1e-9:
            disc = max(0.0, disc)
            r = disc ** 0.5
            out["x_intercepts"] = [(-b - r) / (2 * a), (-b + r) / (2 * a)]
    else:
        if abs(b) > 1e-12:
            out["x_intercepts"] = [-c / b]
    return out


def extract_functions(text: str) -> list[dict]:
    """从题干中提取 f(x)= / R(x)= / y= 等函数定义。"""
    t = normalize_text(text)
    out: list[dict] = []
    seen = set()

    def add(name: str, expr: str):
        poly = parse_poly(expr)
        if not poly:
            return
        key = (round(poly[0], 9), round(poly[1], 9), round(poly[2], 9))
        if key in seen:
            return
        seen.add(key)
        out.append({"name": name.upper(), "expr": expr.strip(), "poly": poly})

    # 先找带名字的 R(x)= / C(x)= / f(x)=；表达式到逗号、分号、and/or、句号或换行为止
    for m in re.finditer(
            r"([A-Za-z])\s*\(\s*x\s*\)\s*=\s*([^,;\n]+?)"
            r"(?=\s*(?:[,;]|\n|$|\s+(?:and|or)\s+|\.(?!\d)(?:\s|$)))",
            t, flags=re.I):
        add(m.group(1), m.group(2))
    # 再找 y=
    for m in re.finditer(
            r"(?<![A-Za-z])y\s*=\s*([^,;\n]+?)"
            r"(?=\s*(?:[,;]|\n|$|\s+(?:and|or)\s+|\.(?!\d)(?:\s|$)))",
            t, flags=re.I):
        add("y", m.group(1))
    return out


def _pick_function(functions: list[dict], label: str) -> dict | None:
    if not functions:
        return None
    m = re.search(r"\b([A-Za-z])\s*\(\s*x\s*\)", label or "")
    if m:
        want = m.group(1).upper()
        for f in functions:
            if f["name"] == want:
                return f
    # 优先二次，再线性
    for f in functions:
        if abs(f["poly"][0]) > 1e-12:
            return f
    return functions[0]


def _parse_pair(value) -> tuple[float, float] | None:
    s = normalize_text(str(value or ""))
    s = s.strip().strip("()[]{} ")
    s = re.sub(r"^(?:x|y)\s*=\s*", "", s, flags=re.I)
    parts = [p.strip() for p in re.split(r"[,;]", s) if p.strip()]
    if len(parts) != 2:
        return None
    a, b = parse_number(parts[0]), parse_number(parts[1])
    if a is None or b is None:
        return None
    return a, b


def _close(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(a)), abs(float(b)))


def verify_graph_objects(objects: list[dict], functions: list[dict]) -> tuple[str, str]:
    """验证作图对象是否落在题干函数上。"""
    if not objects or not functions:
        return "skip", "没有可验证的图形/函数"
    polys = [f["poly"] for f in functions]
    checked = 0
    for obj in objects:
        if obj.get("objectType") not in ("quadratic", "line"):
            continue
        pts = obj.get("points") or []
        if len(pts) < 2:
            return "fail", "图形点数不足"
        # 对每个函数尝试全部点；只要有一个函数能拟合全部点就算对
        fit = False
        for poly in polys:
            if all(
                _close(poly_eval(poly, float(p.get("x", 0))), float(p.get("y", 0)),
                       1e-3)
                for p in pts
            ):
                fit = True
                break
        if not fit:
            return "fail", "图形上的点不满足题干函数"
        checked += 1
    if not checked:
        return "skip", "图形对象类型未知"
    return "ok", f"已验证 {checked} 个图形对象"


def verify_candidate(packet: dict, spec: dict) -> tuple[str, str]:
    """对模型答案做本地验算。

    返回 (status, detail)，status 为 ok/fail/skip。只验证能确定的项；无法
    判断时 skip，不把“不知道”误判为错。
    """
    text = str(packet.get("text") or "")
    functions = extract_functions(text)
    fields = list(packet.get("fields") or []) + list(packet.get("inputs") or [])
    radios = list(packet.get("radios") or [])
    drops = list(packet.get("dropdowns") or [])
    choices = list(spec.get("choices") or ([] if not spec.get("choice")
                                           else [spec["choice"]]))
    values = list(spec.get("values") or ([] if not spec.get("value")
                                         else [spec["value"]]))
    matrix = spec.get("matrix")

    # 控件完整性：模型漏答必须判失败
    if radios and not choices:
        return "fail", "题目有选项，但答案没有 CHOICE"
    if drops and not spec.get("drops"):
        return "fail", "题目有下拉框，但答案没有 DROPDOWN"
    if fields and not (values or matrix):
        return "fail", "题目有填空，但答案没有 VALUE/MATRIX"
    if fields and values and not matrix and len(values) < len(fields):
        return "fail", f"题目有 {len(fields)} 个填空，答案只给了 {len(values)} 个"

    checked = 0
    problems = []
    for i, v in enumerate(values):
        label = ""
        if i < len(fields):
            label = str(fields[i].get("label") or "")
        if not label and len(fields) == 1:
            label = str(fields[0].get("label") or "")
        low = label.lower()
        fn = _pick_function(functions, label)
        if not fn:
            continue

        poly = fn["poly"]
        feat = poly_features(poly)
        if "vertex" in low and feat.get("vertex"):
            pair = _parse_pair(v)
            if pair is None:
                problems.append(f"{label}: 不是有序对")
            elif not (_close(pair[0], feat["vertex"][0])
                      and _close(pair[1], feat["vertex"][1])):
                problems.append(f"{label}: 顶点应为 {feat['vertex']}")
            else:
                checked += 1
            continue
        if ("y-intercept" in low or "y intercept" in low
                or "initial value" in low):
            num = parse_number(v)
            if num is None:
                problems.append(f"{label}: 不是数字")
            elif not _close(num, feat["y_intercept"][1]):
                problems.append(f"{label}: y 截距应为 {feat['y_intercept'][1]}")
            else:
                checked += 1
            continue
        if ("x-intercept" in low or "x intercept" in low
                or "zero of" in low or "zeros of" in low):
            nums = [parse_number(x) for x in re.split(r"[,;]", str(v))]
            nums = [x for x in nums if x is not None]
            want = feat.get("x_intercepts") or []
            if not nums:
                problems.append(f"{label}: 不是数字")
            elif not all(any(_close(x, w) for w in want) for x in nums):
                problems.append(f"{label}: x 截距应为 {want}")
            else:
                checked += 1
            continue
        if "slope" in low:
            num = parse_number(v)
            if num is None:
                problems.append(f"{label}: 不是数字")
            elif not _close(num, feat["slope"]):
                problems.append(f"{label}: 斜率应为 {feat['slope']}")
            else:
                checked += 1
            continue
        # f(3) / R(5) 这种代入求值
        m = re.search(r"\b([A-Za-z])\s*\(\s*([+-]?\d+(?:\.\d+)?)\s*\)",
                      label)
        if m and m.group(1).upper() == fn["name"]:
            x = float(m.group(2))
            num = parse_number(v)
            if num is None:
                problems.append(f"{label}: 不是数字")
            elif not _close(num, poly_eval(poly, x)):
                problems.append(f"{label}: 应等于 {poly_eval(poly, x)}")
            else:
                checked += 1
            continue
        # 只有一个二次函数、问函数值时，允许按 label 里的 "value" 等模糊验证
        if ("value" in low or "evaluate" in low) and len(functions) == 1:
            # 没有明确的 x 时不做逻辑验算，避免误判
            continue

    if problems:
        return "fail", "；".join(problems[:3])
    if checked:
        return "ok", f"已验算 {checked} 项"
    return "skip", "没有可本地验算的关系"


def canonical_value(value) -> str:
    """把答案归一化成投票 key。"""
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    # 有序对必须先于数字判断，否则 "(5,25)" 会被去掉逗号变成 525
    if "," in s or ";" in s:
        pair = _parse_pair(s)
        if pair is not None:
            return f"({canonical_value(pair[0])},{canonical_value(pair[1])})"
    exact = parse_number_exact(s)
    if exact is not None:
        # 分母为 1 时统一成整数写法
        if exact.denominator == 1:
            return str(exact.numerator)
        return f"{exact.numerator}/{exact.denominator}"
    s = normalize_text(s)
    s = re.sub(r"\s+", "", s).lower()
    return s.strip("。.;；,，")
