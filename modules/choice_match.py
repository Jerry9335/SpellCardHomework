"""选项匹配（移植自 Auto-Pearson 的 choiceIndex 思路）。

Pearson 的选项标签格式很杂：
- ``A. 90%`` / ``B) 1/2`` / ``Option C: x=5``；
- 图片/图形选项只有 ``A``、``B`` 或 ``Graph A``；
- 题干里常带 ``StartFraction`` 等 LaTeX 文本，不能拿整段做匹配。

这个模块只负责“把模型给的答案映射到第几个选项”，不碰 DOM。
匹配不到或存在歧义时返回 ``None``，绝不按位置瞎猜。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_LETTER = re.compile(r"^\s*(?:option|choice|answer)?\s*[:\-]?\s*([A-H])\s*(?:[.):\]\-–—]\s*|\s+|$)(.*)$",
                     re.I | re.S)
_ORDINAL = re.compile(r"^\s*(?:#|no\.?\s*)?(\d{1,2})\s*[.):\]\-–—]\s*(.*)$", re.I | re.S)
_OPTION_PREFIX = re.compile(r"^\s*(?:option|choice|answer)\s*[:\-]?\s*", re.I)


def _clean(s: str) -> str:
    s = unicodedata.normalize("NFKC", str(s or ""))
    s = (s.replace("\u2212", "-").replace("−", "-")
         .replace("–", "-").replace("—", "-")
         .replace("’", "'").replace("‘", "'")
         .replace("“", '"').replace("”", '"')
         .replace("×", "x"))
    s = s.replace("\u200b", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _norm(s: str) -> str:
    s = _clean(s).lower()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[.,;:!?]+$", "", s)
    return s


def _split_label(label: str) -> tuple[str, str, int | None]:
    """拆分 ``B. 90%`` / ``2) x=5`` / ``Graph A``。返回 (letter, body, ordinal)。"""
    raw = _clean(label)
    m = _LETTER.match(raw)
    if m:
        return m.group(1).upper(), m.group(2).strip(), None
    m = _ORDINAL.match(raw)
    if m:
        return "", m.group(2).strip(), int(m.group(1))
    return "", raw, None


def _split_value(value: str) -> tuple[str, str, int | None]:
    raw = _clean(_OPTION_PREFIX.sub("", _clean(value)))
    m = _LETTER.match(raw)
    if m:
        return m.group(1).upper(), m.group(2).strip(), None
    m = _ORDINAL.match(raw)
    if m:
        return "", m.group(2).strip(), int(m.group(1))
    return "", raw, None


def _compatible(a: str, b: str) -> bool:
    """两个选项正文是否可视为同一答案。"""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # 百分比/小数写法：90% 与 90、0.90 与 .90
    if na.rstrip("%") == nb.rstrip("%") and len(na.rstrip("%")) >= 1:
        return True
    # 完整文本包含：至少 3 个字符，避免 "x" 这种单字符误伤
    if len(na) >= 3 and len(nb) >= 3 and (na in nb or nb in na):
        return True
    return False


@dataclass(frozen=True)
class ChoiceMatch:
    index: int | None
    method: str
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.index is not None

    @property
    def ambiguous(self) -> bool:
        return self.reason.startswith("ambiguous")


def match_choice(value: str, choices: list[str]) -> ChoiceMatch:
    """把答案映射到 ``choices`` 的下标。

    - 纯字母：优先找带该字母的选项；选项本身没有字母时才按 A/B/C 顺序；
    - 字母 + 文本：字母与文本互相印证；冲突或重复标签时返回歧义；
    - 纯文本：完整/包含匹配，必须唯一。
    """
    labels = [_clean(c) for c in (choices or [])]
    if not labels:
        return ChoiceMatch(None, "empty", "no choices")
    parsed = [_split_label(x) for x in labels]
    letter, body, ordinal = _split_value(value or "")
    nbody = _norm(body)

    # 1) 模型给的是纯字母
    if letter and not nbody:
        same = [i for i, (l, _b, _o) in enumerate(parsed) if l == letter]
        if len(same) == 1:
            return ChoiceMatch(same[0], "letter")
        if len(same) > 1:
            return ChoiceMatch(None, "letter", "ambiguous duplicate letter")
        # 选项没有字母前缀（Yes/No、图片选项）才允许按字母顺序
        if not any(l for l, _b, _o in parsed):
            idx = ord(letter) - ord("A")
            if 0 <= idx < len(labels):
                return ChoiceMatch(idx, "letter-index")
        return ChoiceMatch(None, "letter", "no option with this letter")

    # 2) 模型给的是「字母 + 文本」，例如 B. 90%
    if letter and nbody:
        same = [i for i, (l, _b, _o) in enumerate(parsed) if l == letter]
        if same:
            exact = [i for i in same if _compatible(body, parsed[i][1])]
            if len(exact) == 1:
                return ChoiceMatch(exact[0], "letter-text")
            if len(exact) > 1:
                return ChoiceMatch(None, "letter-text", "ambiguous duplicate labels")
            # 字母在，但正文对不上：如果正文能唯一匹配另一个选项，说明字母和正文冲突
            text_hits = [i for i, (_l, b, _o) in enumerate(parsed)
                         if _compatible(body, b)]
            if len(text_hits) == 1:
                return ChoiceMatch(text_hits[0], "text-after-letter")
            return ChoiceMatch(None, "letter-text", "letter/text conflict or no match")
        # 选项没有字母前缀，正文匹配；否则再按字母顺序
        text_hits = [i for i, (_l, b, _o) in enumerate(parsed) if _compatible(body, b)]
        if len(text_hits) == 1:
            return ChoiceMatch(text_hits[0], "text")
        if len(text_hits) > 1:
            return ChoiceMatch(None, "text", "ambiguous duplicate labels")
        if not any(l for l, _b, _o in parsed):
            idx = ord(letter) - ord("A")
            if 0 <= idx < len(labels):
                return ChoiceMatch(idx, "letter-index")
        return ChoiceMatch(None, "letter-text", "no match")

    # 3) 纯数字序号：1 / 2) ...
    if ordinal is None and nbody.isdigit() and len(nbody) <= 2:
        ordinal = int(nbody)
    if ordinal is not None:
        if 1 <= ordinal <= len(labels):
            # 只有选项本身也带序号时才按序号，否则仍需文本印证
            if any(o == ordinal for _l, _b, o in parsed):
                return ChoiceMatch(ordinal - 1, "ordinal")

    # 4) 纯文本：优先完全相等，再唯一包含
    if not nbody:
        return ChoiceMatch(None, "empty", "empty answer")
    exact = [i for i, (_l, b, _o) in enumerate(parsed) if _norm(b) == nbody]
    if len(exact) == 1:
        return ChoiceMatch(exact[0], "text-exact")
    if len(exact) > 1:
        return ChoiceMatch(None, "text-exact", "ambiguous duplicate labels")
    hits = [i for i, (_l, b, _o) in enumerate(parsed) if _compatible(body, b)]
    if len(hits) == 1:
        return ChoiceMatch(hits[0], "text")
    if len(hits) > 1:
        # 选最短/最接近的，但只有明显唯一时才接受
        ranked = sorted(hits, key=lambda i: abs(len(_norm(parsed[i][1])) - len(nbody)))
        if len(ranked) == 1 or (len(ranked) > 1
                                and len(_norm(parsed[ranked[0]][1]))
                                != len(_norm(parsed[ranked[1]][1]))):
            return ChoiceMatch(ranked[0], "text-best")
        return ChoiceMatch(None, "text", "ambiguous multiple labels")
    return ChoiceMatch(None, "text", "no match")


def choice_index(value: str, choices: list[str]) -> int | None:
    """便捷函数：匹配不到/歧义时返回 None。"""
    m = match_choice(value, choices)
    return m.index if m.ok else None


def choice_letter(index: int) -> str:
    return chr(ord("A") + int(index)) if 0 <= int(index) < 26 else "?"
