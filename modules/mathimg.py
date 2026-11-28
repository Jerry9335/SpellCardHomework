"""把解答里的 LaTeX 片段誊成 PIL 图片：矩阵 / 分式 / 根号。

帕秋莉：公式写在纸上是一个样，落到符卡上又是另一个样。
这个模块只负责「誊写」——不碰 Tk，也不认识主题色；
墨色、纸色、字体都由调用方给，缓存替她收好。

对外只有两个口子：
    render(text, ...)               -> (带占位符的文字, 图片列表)
    split_placeholders(display_text)-> [("文本", None), ("", 0), ...]

占位符格式：``\\x01<序号>\\x02``（例如 ``\\x010\\x02``），序号就是 images 的下标。
调用方负责把占位符换成 ``ImageTk.PhotoImage`` 再 insert 进 Text。

约定：
- ``images`` 里的 PIL.Image 由缓存共享，**调用方不要原地修改**；
- 画不出来的构造一律退回文字，绝不吞内容（嵌套分式/矩阵、PIL 异常都会有兜底）。
"""
from __future__ import annotations

import os
import re
import tempfile
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

__all__ = ["render", "split_placeholders"]

# 帕秋莉：书架就这么大，128 格够常用的公式轮换了。
_CACHE_MAX = 128

_PLACEHOLDER_RE = re.compile(r"\x01(\d+)\x02")
_MATRIX_RE = re.compile(
    r"\\begin\{(pmatrix|bmatrix|matrix|vmatrix)\}(.*?)\\end\{\1\}", re.S)
_FRAC_CMDS = ("\\dfrac", "\\tfrac", "\\frac")
_HAS_DEEPER_RE = re.compile(r"\\(?:d|t)?frac(?=\s*\{)|\\begin\{")

# 魔理沙：中文字体先挑最像书上的，实在没有就退 Arial，最后才用 PIL 的备用字。
_FONT_CANDIDATES = ("msyh.ttc", "msyhbd.ttc", "simhei.ttf", "arial.ttf")

# 这些命令只负责“把里面的字露出来”，不是公式本身。
_GROUP_TEXT_CMDS = ("text", "mathrm", "mathbf", "mathit", "operatorname")

# 常见记号：誊抄时换成能读的字符，别把反斜杠留在符卡上。
_CMD_REPL = {
    "times": "×", "cdot": "·", "div": "÷", "pm": "±", "mp": "∓",
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠",
    "approx": "≈", "equiv": "≡", "sim": "∼", "propto": "∝",
    "infty": "∞", "pi": "π", "alpha": "α", "beta": "β", "gamma": "γ",
    "delta": "δ", "theta": "θ", "lambda": "λ", "mu": "μ", "sigma": "σ",
    "phi": "φ", "omega": "ω", "Delta": "Δ", "Sigma": "Σ", "Omega": "Ω",
    "to": "→", "rightarrow": "→", "leftarrow": "←", "Rightarrow": "⇒",
    "Leftarrow": "⇐", "leftrightarrow": "↔", "sum": "Σ", "prod": "∏",
    "int": "∫", "partial": "∂", "nabla": "∇", "because": "∵",
    "therefore": "∴", "angle": "∠", "triangle": "△", "circ": "°",
    "degree": "°", "min": "min", "max": "max", "log": "log", "ln": "ln",
    "sin": "sin", "cos": "cos", "tan": "tan", "lim": "lim",
}

_SUP_MAP = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
    "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    "+": "⁺", "-": "⁻", "n": "ⁿ", "i": "ⁱ",
}
_SUB_MAP = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄",
    "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
    "+": "₊", "-": "₋",
}


class _Nested(Exception):
    """帕秋莉：这一层里还套着更深的构造，图里画不下，只能退回文字。"""


# ------------------------------------------------------------------ 字体与量尺
def _font_dirs() -> tuple[str, ...]:
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows"
    return (os.path.join(windir, "Fonts"), "")


@lru_cache(maxsize=8)
def _resolve_font(font_path: str | None) -> str:
    """咲夜：先按客人指的名字找；找不到再按名录依次问过去。"""
    candidates: list[str] = []
    if font_path:
        candidates.append(str(font_path))
    candidates.extend(_FONT_CANDIDATES)
    for name in candidates:
        if os.path.isabs(name):
            paths = [name]
        else:
            paths = [os.path.join(d, name) if d else name for d in _font_dirs()]
        for path in paths:
            try:
                ImageFont.truetype(path, 16)
                return path
            except Exception:
                continue
    return ""


@lru_cache(maxsize=64)
def _load_font(path: str, size: int):
    size = max(1, int(size))
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # 老版本 Pillow 的 load_default 不接 size
        return ImageFont.load_default()


def _probe() -> ImageDraw.ImageDraw:
    return ImageDraw.Draw(Image.new("RGB", (2, 2)))


def _measure(text: str, font) -> tuple[int, int, int, int]:
    """返回 (宽, 高, 顶偏移, 左偏移)；空串给 (0, 0, 0, 0)。"""
    if not text:
        return 0, 0, 0, 0
    bb = _probe().textbbox((0, 0), text, font=font)
    return max(0, int(bb[2] - bb[0])), max(0, int(bb[3] - bb[1])), bb[1], bb[0]


def _text_image(text: str, fs: int, font_path: str, ink, bg) -> Image.Image:
    """把一行文字画成图；fs 已经是超采样后的像素字号。"""
    text = (text or "").replace("\n", " ")
    font = _load_font(font_path, fs)
    if not text:
        return Image.new("RGB", (1, 1), bg)
    w, h, top, left = _measure(text, font)
    img = Image.new("RGB", (max(1, w), max(1, h)), bg)
    ImageDraw.Draw(img).text((-left, -top), text, font=font, fill=ink)
    return img


def _hstack(parts: list[Image.Image], bg, gap: int = 0) -> Image.Image:
    """把几块图横向拼起来，垂直居中；每块之间留 gap 像素。"""
    parts = [p for p in parts if p is not None]
    if not parts:
        return Image.new("RGB", (1, 1), bg)
    width = sum(p.width for p in parts) + gap * (len(parts) - 1)
    height = max(p.height for p in parts)
    img = Image.new("RGB", (max(1, width), max(1, height)), bg)
    x = 0
    for part in parts:
        img.paste(part, (x, (height - part.height) // 2))
        x += part.width + gap
    return img


def _finalize(img: Image.Image, scale: int) -> Image.Image:
    """咲夜：超采样画完，按拍子缩回原尺寸；边缘才干净。"""
    scale = max(1, int(scale))
    if scale <= 1:
        return img
    w = max(1, img.width // scale)
    h = max(1, img.height // scale)
    return img.resize((w, h), Image.LANCZOS)


# ------------------------------------------------------------------ 括号与命令解析
def _read_group(s: str, i: int):
    """s[i] 是 '{'，返回 (内容, 右括号后一位)；配不上返回 None。"""
    if i < 0 or i >= len(s) or s[i] != "{":
        return None
    depth = 0
    j = i
    n = len(s)
    while j < n:
        ch = s[j]
        if ch == "\\":
            j += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return None


def _skip_space(s: str, i: int) -> int:
    while i < len(s) and s[i].isspace():
        i += 1
    return i


def _parse_frac(s: str, i: int):
    """找 \\frac / \\dfrac / \\tfrac，返回 (分子, 分母, 结束位置)。"""
    for cmd in _FRAC_CMDS:
        if not s.startswith(cmd, i):
            continue
        j = _skip_space(s, i + len(cmd))
        first = _read_group(s, j)
        if first is None:
            return None
        num, j = first
        j = _skip_space(s, j)
        second = _read_group(s, j)
        if second is None:
            return None
        den, end = second
        return num, den, end
    return None


def _parse_sqrt(s: str, i: int):
    """找 \\sqrt[n]{x} / \\sqrt{x}，返回 (次数或 None, 被开方, 结束位置)。"""
    if not s.startswith("\\sqrt", i):
        return None
    j = _skip_space(s, i + len("\\sqrt"))
    degree = None
    if j < len(s) and s[j] == "[":
        close = s.find("]", j + 1)
        if close < 0:
            return None
        degree = s[j + 1:close]
        j = _skip_space(s, close + 1)
    group = _read_group(s, j)
    if group is None:
        return None
    body, end = group
    return degree, body, end


def _has_deeper(s: str) -> bool:
    return bool(_HAS_DEEPER_RE.search(s or ""))


def _parse_matrix(body: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for chunk in re.split(r"\\\\", body):
        chunk = chunk.strip().strip("\n").strip()
        if not chunk:
            continue
        rows.append([cell.strip() for cell in chunk.split("&")])
    if not rows:
        raise ValueError("empty matrix")
    ncol = max(len(row) for row in rows)
    return [row + [""] * (ncol - len(row)) for row in rows]


# ------------------------------------------------------------------ 纯文字誊抄
def _strip_text_commands(s: str) -> str:
    """把 \\text{...} / \\mathrm{...} 的外壳剥掉，只留里面的字。"""
    for name in _GROUP_TEXT_CMDS:
        token = "\\" + name
        out: list[str] = []
        i = 0
        while i < len(s):
            if s.startswith(token, i):
                j = _skip_space(s, i + len(token))
                group = _read_group(s, j)
                if group is not None:
                    out.append(_inline_text(group[0]))
                    i = group[1]
                    continue
            out.append(s[i])
            i += 1
        s = "".join(out)
    return s


def _inline_fracs(s: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(s):
        parsed = _parse_frac(s, i)
        if parsed is None:
            out.append(s[i])
            i += 1
            continue
        num, den, end = parsed
        out.append(f"({_inline_text(num) or ' '})/({_inline_text(den) or ' '})")
        i = end
    return "".join(out)


def _inline_sqrts(s: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(s):
        parsed = _parse_sqrt(s, i)
        if parsed is None:
            out.append(s[i])
            i += 1
            continue
        degree, body, end = parsed
        inner = _inline_text(body)
        prefix = "√" + (f"[{_inline_text(degree)}]" if degree else "")
        out.append(prefix + (inner if len(inner) <= 1 else f"({inner})"))
        i = end
    return "".join(out)


def _scripts(s: str) -> str:
    def sup(m):
        body = m.group(1) if m.group(1) is not None else m.group(2)
        if not body:
            return "^"
        if all(ch in _SUP_MAP for ch in body):
            return "".join(_SUP_MAP[ch] for ch in body)
        return "^" + (f"({body})" if len(body) > 1 else body)

    def sub(m):
        body = m.group(1) if m.group(1) is not None else m.group(2)
        if not body:
            return "_"
        if all(ch in _SUB_MAP for ch in body):
            return "".join(_SUB_MAP[ch] for ch in body)
        return "_" + (f"({body})" if len(body) > 1 else body)

    s = re.sub(r"\^\{([^{}]*)\}|\^(\w)", sup, s)
    s = re.sub(r"_\{([^{}]*)\}|_(\w)", sub, s)
    return s


def _inline_text(raw) -> str:
    """把一小段 LaTeX 揉成能画进图中的纯文字（分式/根号退成线性写法）。"""
    s = str(raw or "")
    s = s.replace("$$", "").replace("$", "")
    for token in ("\\(", "\\)", "\\[", "\\]"):
        s = s.replace(token, "")
    # 字面花括号先藏起来，免得后面统一去壳时被误删。
    s = s.replace("\\{", "\x00LBRACE").replace("\\}", "\x00RBRACE")
    s = _strip_text_commands(s)
    s = _inline_fracs(s)
    s = _inline_sqrts(s)
    # \left / \right 只是排版记号；但别误伤 \leftarrow / \rightarrow。
    s = re.sub(r"\\left(?![A-Za-z])", "", s)
    s = re.sub(r"\\right(?![A-Za-z])", "", s)
    for token in ("\\bigl", "\\bigr", "\\Bigl", "\\Bigr"):
        s = s.replace(token, "")
    s = re.sub(r"\\([A-Za-z]+)", lambda m: _CMD_REPL.get(m.group(1), m.group(0)), s)
    for token, repl in (("\\%", "%"), ("\\&", "&"), ("\\#", "#"),
                        ("\\_", "_"), ("\\$", "$"), ("\\,", " "),
                        ("\\;", " "), ("\\:", " "), ("\\!", ""), ("\\ ", " ")):
        s = s.replace(token, repl)
    s = s.replace("\\\\", " ").replace("&", " ")
    # 退回文字时，矩阵外壳只剩噪音；留下单元格里的字就够了。
    s = re.sub(r"\\begin\{[^}]*\}", " ", s)
    s = re.sub(r"\\end\{[^}]*\}", " ", s)
    s = _scripts(s)
    s = s.replace("{", "").replace("}", "")
    s = s.replace("\x00LBRACE", "{").replace("\x00RBRACE", "}")
    return re.sub(r"\s+", " ", s).strip()


def _frac_text(num: str, den: str) -> str:
    """画不了的分式退回 (a)/(b)，至少不糊成一行。"""
    return f"({_inline_text(num) or ' '})/({_inline_text(den) or ' '})"


def _sqrt_text(degree, body: str) -> str:
    """画不了的根号退回 √(...) 文字。"""
    prefix = "√" + (f"[{_inline_text(degree)}]" if degree else "")
    inner = _inline_text(body) or " "
    return prefix + (inner if len(inner) <= 1 else f"({inner})")


# ------------------------------------------------------------------ 分式
def _fraction_image(num: str, den: str, fs: int, font_path: str, ink, bg) -> Image.Image:
    num_text = _inline_text(num) or " "
    den_text = _inline_text(den) or " "
    font = _load_font(font_path, fs)
    wn, hn, top_n, left_n = _measure(num_text, font)
    wd, hd, top_d, left_d = _measure(den_text, font)

    pad = max(1, int(fs * 0.22))
    gap = max(1, int(fs * 0.16))
    bar = max(2, int(fs * 0.06))
    bottom = max(1, int(fs * 0.28))  # 帕秋莉：底下留白，公式在行内才会“提”起来。

    width = max(wn, wd) + pad * 2
    height = hn + hd + gap * 2 + bar + bottom
    img = Image.new("RGB", (max(1, width), max(1, height)), bg)
    draw = ImageDraw.Draw(img)
    draw.text(((width - wn) / 2 - left_n, -top_n), num_text, font=font, fill=ink)
    y_bar = hn + gap
    draw.line((pad * 0.3, y_bar, width - pad * 0.3, y_bar), fill=ink, width=bar)
    draw.text(((width - wd) / 2 - left_d, y_bar + bar + gap - top_d), den_text,
              font=font, fill=ink)
    return img


# ------------------------------------------------------------------ 根号
def _sqrt_image(degree, body: str, fs: int, font_path: str, ink, bg) -> Image.Image:
    parts = _inline_parts(body, fs, font_path, ink, bg)
    content = _hstack(parts, bg, gap=2)
    cw, ch = content.size

    pad = max(1, int(fs * 0.18))
    hook_w = max(1, int(fs * 0.52))
    bar = max(2, int(fs * 0.07))
    gap = max(1, int(fs * 0.16))
    lw = max(2, int(fs * 0.075))

    idx_img = None
    if degree:
        idx_fs = max(1, int(fs * 0.55))
        idx_img = _text_image(_inline_text(degree) or " ", idx_fs, font_path, ink, bg)
    idx_w = idx_img.width if idx_img is not None else 0
    idx_gap = max(1, int(fs * 0.05)) if idx_img is not None else 0
    shift = idx_w + idx_gap

    width = shift + hook_w + cw + pad * 2
    height = ch + gap + bar + max(1, int(fs * 0.18))
    if idx_img is not None:
        height = max(height, idx_img.height + bar)
    img = Image.new("RGB", (max(1, width), max(1, height)), bg)
    draw = ImageDraw.Draw(img)
    if idx_img is not None:
        img.paste(idx_img, (0, 0))

    top = bar + 1
    img.paste(content, (shift + hook_w + pad, top + gap))
    x0 = shift + max(1, pad // 2)
    tip_y = height - int(fs * 0.30)
    mid_y = int(height * 0.62)
    points = [
        (x0, mid_y),
        (x0 + int(hook_w * 0.42), tip_y),
        (shift + hook_w + pad - int(fs * 0.06), top),
        (width - 1, top),
    ]
    draw.line(points, fill=ink, width=lw, joint="curve")
    return img


# ------------------------------------------------------------------ 矩阵
def _inline_parts(raw: str, fs: int, font_path: str, ink, bg) -> list[Image.Image]:
    """把一个单元格/根号内容拆成「文字块 + 分式块」，供横向拼接。"""
    parts: list[Image.Image] = []
    buf: list[str] = []
    i = 0

    def flush() -> None:
        if not buf:
            return
        text = _inline_text("".join(buf))
        buf.clear()
        if text:
            parts.append(_text_image(text, fs, font_path, ink, bg))

    while i < len(raw):
        parsed = _parse_frac(raw, i)
        if parsed is None:
            buf.append(raw[i])
            i += 1
            continue
        flush()
        num, den, end = parsed
        if _has_deeper(num) or _has_deeper(den):
            parts.append(_text_image(_frac_text(num, den), fs, font_path, ink, bg))
        else:
            parts.append(_fraction_image(num, den, fs, font_path, ink, bg))
        i = end
    flush()
    if not parts:
        parts.append(_text_image(" ", fs, font_path, ink, bg))
    return parts


def _matrix_image(env: str, body: str, fs: int, font_path: str, ink, bg) -> Image.Image:
    rows = _parse_matrix(body)
    cells: list[list[tuple[Image.Image, int, int]]] = []
    for row in rows:
        line: list[tuple[Image.Image, int, int]] = []
        for cell in row:
            if "\\begin{" in cell:
                raise _Nested
            parts = _inline_parts(cell, fs, font_path, ink, bg)
            cell_img = _hstack(parts, bg, gap=0)
            line.append((
                cell_img,
                max(cell_img.width, max(1, int(fs * 0.35))),
                max(cell_img.height, max(1, int(fs * 0.5))),
            ))
        cells.append(line)

    nrow = len(cells)
    ncol = len(cells[0])
    colw = [max(cells[i][j][1] for i in range(nrow)) for j in range(ncol)]
    rowh = [max(cells[i][j][2] for j in range(ncol)) for i in range(nrow)]
    pad_x = max(1, int(fs * 0.60))
    pad_y = max(1, int(fs * 0.40))
    br = max(1, int(fs * 0.28))
    gap = max(1, int(fs * 0.20))
    inner_w = sum(colw) + pad_x * (ncol + 1)
    inner_h = sum(rowh) + pad_y * (nrow + 1)
    width = inner_w + 2 * (br + gap)
    height = inner_h
    img = Image.new("RGB", (max(1, width), max(1, height)), bg)

    y = pad_y
    for i in range(nrow):
        x = br + gap + pad_x
        for j in range(ncol):
            cell_img, _cw, _ch = cells[i][j]
            px = x + (colw[j] - cell_img.width) / 2
            py = y + (rowh[i] - cell_img.height) / 2
            img.paste(cell_img, (int(round(px)), int(round(py))))
            x += colw[j] + pad_x
        y += rowh[i] + pad_y

    draw = ImageDraw.Draw(img)
    lw = max(2, int(fs * 0.065))
    top = int(height * 0.03)
    bottom = int(height * 0.97)
    if env == "bmatrix":
        tick = int(br * 0.5)
        for x0, sign in ((br, 1), (width - br, -1)):
            draw.line((x0, top, x0, bottom), fill=ink, width=lw)
            draw.line((x0, top, x0 + sign * tick, top), fill=ink, width=lw)
            draw.line((x0, bottom, x0 + sign * tick, bottom), fill=ink, width=lw)
    elif env == "vmatrix":
        for x0 in (br, width - br):
            draw.line((x0, top, x0, bottom), fill=ink, width=lw)
    elif env == "matrix":
        pass
    else:  # pmatrix：左右两段圆弧
        for x0, a0, a1 in ((br, 90, 270), (width - br, -90, 90)):
            draw.arc((x0 - br, top, x0 + br, bottom), a0, a1, fill=ink, width=lw)
    return img


# ------------------------------------------------------------------ 顶层扫描
def _scan(text: str, fs: int, font_path: str, ink, bg, scale: int):
    """紫：沿着境界的缝隙走一遍，能画的画成图，画不动的原样留在字里。"""
    out_text: list[str] = []
    images: list[Image.Image] = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("\\begin{", i):
            match = _MATRIX_RE.match(text, i)
            if match is not None:
                img = None
                try:
                    img = _matrix_image(match.group(1), match.group(2),
                                        fs, font_path, ink, bg)
                except _Nested:
                    img = None
                except Exception:
                    img = None
                if img is not None:
                    out_text.append(_placeholder(len(images)))
                    images.append(_finalize(img, scale))
                    i = match.end()
                    continue
                # 套了矩阵的矩阵、或画的时候出了岔子：整段按原文留着。
                out_text.append(match.group(0))
                i = match.end()
                continue

        if text.startswith("\\sqrt", i):
            parsed = _parse_sqrt(text, i)
            if parsed is not None:
                degree, body, end = parsed
                if "\\begin{" in body:
                    out_text.append(_sqrt_text(degree, body))
                    i = end
                    continue
                img = None
                try:
                    img = _sqrt_image(degree, body, fs, font_path, ink, bg)
                except Exception:
                    img = None
                if img is not None:
                    out_text.append(_placeholder(len(images)))
                    images.append(_finalize(img, scale))
                    i = end
                    continue
                out_text.append(text[i:end])
                i = end
                continue

        parsed = _parse_frac(text, i)
        if parsed is not None:
            num, den, end = parsed
            if _has_deeper(num) or _has_deeper(den):
                # 帕秋莉：分式里再套分式/矩阵，图上排不下，退回 (a)/(b) 文字。
                out_text.append(_frac_text(num, den))
                i = end
                continue
            img = None
            try:
                img = _fraction_image(num, den, fs, font_path, ink, bg)
            except Exception:
                img = None
            if img is not None:
                out_text.append(_placeholder(len(images)))
                images.append(_finalize(img, scale))
                i = end
                continue
            out_text.append(text[i:end])
            i = end
            continue

        out_text.append(text[i])
        i += 1
    return "".join(out_text), images


def _placeholder(index: int) -> str:
    return f"\x01{index}\x02"


@lru_cache(maxsize=_CACHE_MAX)
def _render_cached(text: str, font_px: int, ink: str, bg: str, scale: int,
                   font_path: str):
    """缓存键里带上解析后的字体路径：换了字体不能拿旧图充数。"""
    fs = max(1, int(font_px)) * max(1, int(scale))
    display, images = _scan(text, fs, font_path, ink, bg, scale)
    return display, tuple(images)


def render(text: str, *, font_px: int, ink: str, bg: str,
           font_path: str | None = None, scale: int = 2) -> tuple[str, list]:
    """把 text 里的矩阵 / 分式 / 根号替换成占位符。

    ``font_px`` 是**最终**像素字号；内部按 ``scale`` 倍放大绘制，再用 LANCZOS
    缩回原尺寸，边缘才干净（默认 2 倍超采样）。

    返回 ``(display_text, images)``：
      - display_text 里的占位符是 ``\\x01<序号>\\x02``，其余文字原样保留；
      - images 是 PIL.Image 列表，按占位符序号排列（缓存共享，请勿原地修改）。
    """
    source = "" if text is None else str(text)
    try:
        size = int(round(float(font_px)))
    except (TypeError, ValueError):
        size = 16
    if size < 6:
        size = 16
    try:
        factor = int(scale)
    except (TypeError, ValueError):
        factor = 2
    factor = max(1, min(4, factor))

    font_path_key = _resolve_font(str(font_path) if font_path else None)
    try:
        display, images = _render_cached(source, size, ink, bg, factor, font_path_key)
    except Exception:
        # 紫：连纸和墨都配不齐的时候，至少别把原文弄丢。
        return source, []
    return display, list(images)


def split_placeholders(display_text: str) -> list[tuple[str, int | None]]:
    """把 display_text 切成 [("文本", None), ("", 0), ("文本", None), ...]。

    图片段用空字符串占位，第二项是 images 的下标；方便调用方逐段 insert。
    """
    text = "" if display_text is None else str(display_text)
    pieces: list[tuple[str, int | None]] = []
    pos = 0
    for match in _PLACEHOLDER_RE.finditer(text):
        if match.start() > pos:
            pieces.append((text[pos:match.start()], None))
        pieces.append(("", int(match.group(1))))
        pos = match.end()
    if pos < len(text):
        pieces.append((text[pos:], None))
    return pieces


# ------------------------------------------------------------------ demo
def demo() -> None:
    """帕秋莉：把这几张符卡誊一遍，收进临时书架，自己翻着看。"""
    cases = [
        ("普通分式", r"答案：\frac{1}{2}"),
        ("二次公式", r"\frac{-b+\sqrt{b^2-4ac}}{2a}"),
        ("圆括号矩阵", r"\begin{pmatrix} 1 & 2 \\ 3 & 4 \end{pmatrix}"),
        ("立方根", r"\sqrt[3]{x}"),
        ("嵌套分式（应退文字）", r"\frac{\frac{1}{2}}{3}"),
        ("带分式的矩阵",
         r"\begin{pmatrix} \frac{1}{2} & 3 \\ 4 & \frac{5}{6} \end{pmatrix}"),
        ("方括号矩阵", r"\begin{bmatrix} a & b \\ c & d \end{bmatrix}"),
        ("行列式", r"\begin{vmatrix} 1 & 2 \\ 3 & 4 \end{vmatrix}"),
        ("无括号矩阵", r"\begin{matrix} 1 & 2 \\ 3 & 4 \end{matrix}"),
        ("不支持的原样文字", r"\sum_{i=1}^{n} i^2"),
    ]
    out_dir = tempfile.mkdtemp(prefix="sch_mathimg_")
    font_key = _resolve_font(None)
    print("帕秋莉：这一批符卡，我按书上的定式誊好了。")
    print(f"  用的笔迹：{font_key or '（PIL 备用字，中文可能是豆腐）'}")
    print(f"  临时书架：{out_dir}")
    for case_index, (label, source) in enumerate(cases, start=1):
        display, images = render(source, font_px=32, ink="#fffaf6",
                                 bg="#1c1830", scale=2)
        print(f"\n[{case_index}] {label}")
        print(f"  原符卡：{source}")
        print(f"  誊写后的题面：{display!r}")
        print(f"  按段切开：{split_placeholders(display)}")
        if not images:
            print("  帕秋莉：这一幅画不了，整段退回文字。")
            continue
        for image_index, image in enumerate(images):
            path = os.path.join(out_dir, f"case{case_index}_{image_index}.png")
            image.save(path, "PNG")
            print(f"  第 {image_index} 幅：{image.size[0]}x{image.size[1]} -> {path}")
    print("\n帕秋莉：誊完了。剩下的退治，就交给灵梦吧。")


if __name__ == "__main__":
    try:
        import sys

        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    demo()
