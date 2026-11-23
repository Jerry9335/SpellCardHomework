"""扫描 SingleFile 存下来的 Pearson 页面，把公式调色板的按钮清单打出来。

用途：确认矩阵/向量/分段这些结构模板在 More 第二页里的真实 class / title，
再补进 modules/web.py 的 palette_click 规则。

用法：
    python tools/scan_palette_html.py "D:\\path\\saved.htm"

说明：SingleFile 存下来的页面里 HTML 标签可能不平衡（还有大段 CSS 里也出现
xlInlineMathPalette 字样），所以这里用“标签级正则 + attach-point 位置切分”
而不是 HTMLParser，避免整段被当成 style/script 吞掉。
"""
from __future__ import annotations

import html
import json
import re
import sys

PALETTE_RE = re.compile(
    r'<div\b[^>]*?\bclass\s*=\s*'
    r'(?:"[^"]*xlInlineMathPalette[^"]*"|\'[^\']*xlInlineMathPalette[^\']*\'|[^\s>]*xlInlineMathPalette[^\s>]*)'
    r'[^>]*>',
    re.I | re.S,
)
BUTTON_RE = re.compile(r'<button\b[^>]*>', re.I | re.S)
ATTR_RE = re.compile(
    r'([\w:-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))', re.S)
EQ_RE = re.compile(r'<span\b[^>]*?\beqEditor\b', re.I | re.S)


def unescape_all(s: str, times: int = 2) -> str:
    for _ in range(times):
        s = html.unescape(s)
    return s


def attrs_of(tag: str) -> dict:
    out = {}
    for m in ATTR_RE.finditer(tag):
        val = m.group(2) if m.group(2) is not None else (
            m.group(3) if m.group(3) is not None else m.group(4))
        out[m.group(1).lower()] = val or ""
    return out


def button_text(text: str, end: int) -> str:
    close = text.find("</button>", end)
    if close < 0:
        return ""
    raw = re.sub(r"<[^>]+>", " ", text[end:close])
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()[:24]


def scan(path: str) -> int:
    raw = open(path, encoding="utf-8", errors="replace").read()
    text = unescape_all(raw)

    fields = len(EQ_RE.findall(text))
    print(f"公式输入框 span.eqEditor: {fields}")
    if not fields:
        print("→ 这题没有公式输入框（判断题/选择题之类），调色板不会被创建。")
        print("  请在「有填空」的题上：点一下空 → 点 More → 再保存页面。")
        return 1

    starts = list(PALETTE_RE.finditer(text))
    if not starts:
        print("→ 没找到 div.xlInlineMathPalette：题面可能还没渲染就保存了。")
        return 1

    for idx, m in enumerate(starts, 1):
        end = starts[idx].start() if idx < len(starts) else min(len(text), m.end() + 300000)
        block = text[m.end():end]
        head = attrs_of(m.group(0))
        more_pos = block.find("morePaletteNode")
        print(f"\n===== 调色板 {idx}  id={head.get('id', '(无)')} =====")

        buckets = {"keyRow": [], "more": []}
        others = 0
        for b in BUTTON_RE.finditer(block):
            a = attrs_of(b.group(0))
            cls = a.get("class", "")
            if "toolButton" not in cls:
                others += 1          # Check answer / Help me solve 之类的页面控件
                continue
            item = {"cls": cls, "title": a.get("title", ""),
                    "label": a.get("aria-label", ""),
                    "text": button_text(block, b.end())}
            buckets["more" if more_pos >= 0 and b.start() > more_pos else "keyRow"].append(item)

        for name, key in (("第一页 keyRow", "keyRow"), ("More 第二页", "more")):
            print(f"  -- {name}（{len(buckets[key])} 个按钮）")
            for item in buckets[key]:
                print("     " + json.dumps(item, ensure_ascii=False))
        if others:
            print(f"  （另有 {others} 个非调色板按钮，如 Check answer / Help me solve，已忽略）")

    pops = re.findall(r'id\s*=\s*"([^"]*(?:MatrixSizePopup|MatrixPopup)[^"]*)"', text)
    print("\n矩阵尺寸弹窗 id:", pops or "(未找到，页面里还没展开过矩阵)")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    return scan(argv[1])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
