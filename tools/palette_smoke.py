"""把公式调色板的按钮逐个点一遍，输出每个按钮点下去会发生什么。

不需要给每个按钮做快照，也不需要 Pearson 账号密码——但需要那个带调试端口
的答题浏览器，并且当前停在**有填空**的题目上。

用法：
    python tools/palette_smoke.py            # 完整跑一遍（会在空框里插入再清空）
    python tools/palette_smoke.py --dry      # 只列出按钮，不点

安全约束：
    - 只点调色板里的 button.toolButton，绝不点 Check answer / Submit / Save；
    - 只在**空输入框**上操作，每个按钮点完立刻清空；
    - 弹窗一律按 Esc / Cancel 关掉，不点 OK；
    - 输入框非空就拒绝运行（避免破坏已经写好的答案）。
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import web  # noqa: E402

TOOLS_JS = r"""
(() => {
  const vis = (e) => { if (!e) return false; const r = e.getBoundingClientRect();
                       return r.width > 2 && r.height > 2; };
  const sels = ['div.xlInlineMathPalette', 'div.xlKeyboardDialog',
                '[class*=KeyboardDialog]', '[data-dojo-attach-point="paletteNode"]'];
  let pals = [];
  for (const s of sels) {
    pals = [...document.querySelectorAll(s)].filter(vis);
    if (pals.length) break;
  }
  const pal = pals.length ? pals[pals.length - 1] : null;
  if (!pal) return null;
  const more = pal.querySelector('[data-dojo-attach-point="morePaletteNode"]');
  const isTool = (b) => /(^|\s)(toolButton|icon[A-Z])/.test(String(b.className || ''));
  return [...pal.querySelectorAll('button')].filter(vis).filter(isTool).map((b) => ({
    cls: String(b.className || ''),
    title: b.getAttribute('title') || '',
    text: (b.innerText || '').trim().slice(0, 24),
    more: !!(more && more.contains(b)),
  }));
})()
"""

DIALOG_JS = r"""
(() => {
  const vis = (e) => { if (!e) return false; const r = e.getBoundingClientRect();
                       return r.width > 2 && r.height > 2; };
  const pops = [...document.querySelectorAll(
      '[role=dialog], [id*=Popup], [id*=Dialog], [class*=Popup], [class*=Dialog]')]
    .filter(vis)
    .filter((p) => p.querySelector('button'));
  const last = pops.length ? pops[pops.length - 1] : null;
  if (!last) return null;
  return {
    id: last.id || '',
    cls: String(last.className || '').slice(0, 80),
    text: (last.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 60),
    buttons: [...last.querySelectorAll('button')].filter(vis)
      .map((b) => (b.innerText || '').trim()).filter(Boolean).slice(0, 8),
    inputs: [...last.querySelectorAll('input')].map((i) => ({
      id: i.id || '', cls: String(i.className || ''), value: i.value,
    })).slice(0, 4),
  };
})()
"""

SKIP_ICONS = {"iconUndo", "iconRedo", "iconLessTools", "iconMoreTools"}

INNER_JS = ("(() => { const e = document.getElementById(%s);"
            " return e ? (e.innerText || '').trim() : null; })()")


def inner_text(drv, fid: str) -> str:
    """编辑器里的真实内容（不含 aria-label 提示语）。"""
    try:
        return str(drv.js(INNER_JS % json.dumps(fid)) or "")
    except Exception:
        return ""


def field_empty(drv, fid: str) -> bool:
    """空判定：编辑器 innerText 为空就算空（aria-label 里是题面提示，不是内容）。"""
    return not inner_text(drv, fid).strip()


def icon_class(cls: str) -> str:
    for part in str(cls or "").split():
        if part.startswith("icon"):
            return part
    return ""


def dialog_open(drv) -> dict | None:
    try:
        return drv.js(DIALOG_JS)
    except Exception:
        return None


def dismiss(drv) -> None:
    """Esc 关掉当前弹窗/调色板；矩阵弹窗优先按 Cancel。"""
    try:
        drv.js(
            "(() => { const vis = (e) => { if (!e) return false;"
            " const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2; };"
            " const ps = [...document.querySelectorAll("
            "  '[role=dialog], [id*=Popup], [id*=Dialog], [class*=Popup], [class*=Dialog]')]"
            "  .filter(vis);"
            " const p = ps[ps.length - 1];"
            " if (!p) return 'none';"
            " const c = [...p.querySelectorAll('button')]"
            "   .find((b) => /^(cancel|close|×)$/i.test((b.innerText || '').trim()));"
            " if (c) { c.click(); return 'cancel'; }"
            " return 'none'; })()")
    except Exception:
        pass
    try:
        drv.key("Escape", "Escape", 27)
    except Exception:
        pass
    time.sleep(0.25)


def collect_tools(drv, fid: str) -> list[dict]:
    """把第一页和 More 第二页的工具都收一遍（只收可见的，靠展开/收回两趟）。"""
    out: list[dict] = []
    seen: set[str] = set()

    def grab() -> None:
        for t in drv.js(TOOLS_JS) or []:
            ic = icon_class(t.get("cls", ""))
            if not ic or ic in seen or ic in SKIP_ICONS:
                continue
            seen.add(ic)
            out.append({**t, "icon": ic})

    drv.focus_field(fid)
    time.sleep(0.4)
    grab()
    # 没有可点的工具 → palette_click 会去点 More 展开第二页
    drv.palette_click(fid, ("__none__",), "(?!)", allow_more=True)
    time.sleep(0.4)
    grab()
    # 再点一次（此时是 Less）收回第一页，恢复现场
    drv.palette_click(fid, ("__none__",), "(?!)", allow_more=True)
    time.sleep(0.3)
    return out


def main(argv: list[str]) -> int:
    dry = "--dry" in argv
    page = ""
    if "--page" in argv:
        i = argv.index("--page")
        if i + 1 < len(argv):
            page = argv[i + 1]
    drv = web.WebPlayer(9222, log=lambda m: None)
    drv.connect(prefer=page)
    print(f"已连接：{drv.title[:60]}")

    st = drv.state() or {}
    fields = [f for f in (st.get("fields") or []) if f.get("id")]
    if not fields:
        print("当前页面没有公式输入框（span.eqEditor）。请先打开一道有填空的题。")
        return 1

    # 找一个空框
    target = None
    for f in fields:
        fid = f["id"]
        try:
            drv.focus_field(fid)
            time.sleep(0.35)
            if field_empty(drv, fid):
                target = f
                break
        except Exception:
            continue
    if target is None:
        print("所有公式输入框都已有内容，为安全起见不操作。请清空一个空框再跑。")
        return 1

    fid = target["id"]
    print(f"使用空输入框：{fid}")
    tools = collect_tools(drv, fid)
    if not tools:
        print("没读到调色板按钮。先点一下输入框、再点 More，让调色板展开。")
        return 1
    print(f"共 {len(tools)} 个工具按钮（已跳过 Undo/Redo/More/Less）\n")
    if dry:
        for t in tools:
            print(f"  {t['icon']:24} {t['title'][:50]}")
        drv.close()
        return 0

    report = []
    for i, t in enumerate(tools, 1):
        icon, title = t["icon"], t["title"]
        drv.focus_field(fid)
        time.sleep(0.3)
        before = inner_text(drv, fid)
        res = drv.palette_click(fid, (icon,), "", allow_more=True)
        time.sleep(0.5)
        dlg = dialog_open(drv)
        cells = 0
        try:
            cells = drv.cell_ids(fid)
        except Exception:
            pass
        after = inner_text(drv, fid)

        if dlg:
            effect = "弹窗:" + (dlg.get("id") or dlg.get("cls") or "?")
        elif cells:
            effect = f"插入矩阵({cells}格)"
        elif after.strip() and after != before:
            effect = "插入:" + after.strip().replace("\n", " ")[:40]
        elif res != "ok":
            effect = f"未点中({res})"
        else:
            effect = "无变化"

        report.append({"icon": icon, "title": title, "more": bool(t.get("more")),
                       "click": res, "effect": effect, "dialog": dlg})
        print(f"[{i:02d}/{len(tools)}] {icon:22} {effect}")

        if dlg:
            dismiss(drv)
        # 清空这个框，准备下一个
        try:
            drv.focus_field(fid)
            time.sleep(0.2)
            drv.clear_field()
            time.sleep(0.2)
            if inner_text(drv, fid).strip():
                drv.clear_field()
        except Exception:
            pass

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "palette_smoke_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n报告已写入：{out}")

    dialogs = [r for r in report if r["dialog"]]
    print("\n=== 会打开弹窗的按钮 ===")
    for r in dialogs:
        d = r["dialog"]
        print(f"  {r['icon']:22} id={d.get('id') or '-'} inputs={[i['id'] for i in d.get('inputs') or []]}")
    drv.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
