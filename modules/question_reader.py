"""把 WebPlayer.state() 转成求解引擎使用的 QuestionPacket。

这一层不碰页面，只负责“模型到底看到了什么、要答哪些控件”。保留原始
text 和每个控件的 label，后续 verify_math / answer_engine 才能把答案和
题目关系对应起来。
"""
from __future__ import annotations

import re


def _int_part(value) -> tuple[int, int]:
    try:
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            return int(value[0] or 0), int(value[1] or 0)
    except Exception:
        pass
    return 0, 0


def build_packet(st: dict, text: str | None = None,
                 part_text: str | None = None) -> dict:
    """生成 QuestionPacket。所有字段都来自当前页面快照。"""
    st = st or {}
    part_n, part_m = _int_part(st.get("part"))
    body = (text if text is not None else st.get("text") or "").strip()
    fields = [dict(x) for x in (st.get("fields") or [])
              if isinstance(x, dict) and not x.get("disabled") and not x.get("readonly")]
    inputs = [dict(x) for x in (st.get("inputs") or [])
              if isinstance(x, dict) and not x.get("disabled") and not x.get("readonly")]
    radios = [dict(x) for x in (st.get("radios") or []) if isinstance(x, dict)]
    checks = [dict(x) for x in (st.get("checks") or []) if isinstance(x, dict)]
    dropdowns = [dict(x) for x in (st.get("dropdowns") or []) if isinstance(x, dict)]
    selects = [dict(x) for x in (st.get("selects") or []) if isinstance(x, dict)]

    hint_lines = []
    if part_n and part_m and "当前是第" not in body:
        hint_lines.append(f"当前是第 {part_n} 小问（共 {part_m} 问），只回答这一小问。")
    if part_text and "当前小问" not in body:
        hint_lines.append("当前小问：" + re.sub(r"\s+", " ", part_text).strip()[:600])
    if hint_lines:
        body = "\n".join(hint_lines) + "\n\n" + body

    return {
        "text": body,
        "qno": int(st.get("qno") or 0),
        "part": [part_n, part_m],
        "part_n": part_n,
        "part_m": part_m,
        "fields": fields,
        "inputs": inputs,
        "radios": radios,
        "checks": checks,
        "dropdowns": dropdowns,
        "selects": selects,
        "graph": dict(st.get("graph") or {}),
        "has_graph": bool(st.get("graph")),
        "has_choices": bool(radios or checks),
        "has_inputs": bool(fields or inputs or selects or dropdowns),
        "labels": [str(x.get("label") or "") for x in fields + inputs],
    }
