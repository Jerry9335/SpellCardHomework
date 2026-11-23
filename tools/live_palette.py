"""只读探针：dump 当前 Pearson 页面的公式调色板结构。

用途：矩阵、向量、分段函数这些结构模板在 Pearson 里到底叫什么 class / title，
以及它们在「More」第二页里的真实标记。拿到结果后补进
modules/web.py 的 palette_click 规则即可。

用法：
    1. 用「启动答题浏览器.bat」打开答题浏览器，进到有填空的题；
    2. python tools/live_palette.py
    3. 把输出里 more.buttons 的 cls / title 贴回来。
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import web  # noqa: E402

DUMP_JS = r"""
(() => {
  const vis = (e) => { if (!e) return false; const r = e.getBoundingClientRect();
                       return r.width > 2 && r.height > 2; };
  const btn = (b) => ({cls: String(b.className || ''),
                       title: b.getAttribute('title') || '',
                       label: b.getAttribute('aria-label') || '',
                       text: (b.innerText || '').trim().slice(0, 24),
                       visible: vis(b)});
  const pals = [...document.querySelectorAll('div.xlInlineMathPalette')].map((p) => {
    const more = p.querySelector('[data-dojo-attach-point="morePaletteNode"]');
    return {
      id: p.id,
      visible: vis(p),
      keyRow: [...p.querySelectorAll('div.keyRow button')].map(btn),
      more: more ? {
        hidden: more.classList.contains('hidden'),
        visible: vis(more),
        buttons: [...more.querySelectorAll('button')].map(btn),
      } : null,
    };
  });
  const fields = [...document.querySelectorAll('span.eqEditor')].map((f) => ({
    id: f.id,
    label: (f.getAttribute('aria-label') || '').slice(0, 80),
    rect: (() => {
      const r = f.getBoundingClientRect();
      return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)];
    })(),
  }));
  const pops = [...document.querySelectorAll('[id*=MatrixSizePopup], [id*=MatrixPopup]')]
    .map((p) => ({id: p.id, visible: vis(p),
                  inputs: [...p.querySelectorAll('input')].map((i) => i.id)}));
  return {url: location.href, fields: fields, palettes: pals, matrix_popups: pops};
})()
"""


def main() -> int:
    drv = web.WebPlayer(9222, log=lambda m: None)
    drv.connect()
    try:
        st = drv.state() or {}
        fields = st.get("fields") or []
        print(f"页面上有 {len(fields)} 个公式输入框")
        for f in fields[:4]:
            fid = f.get("id") or ""
            if not fid:
                continue
            try:
                drv.focus_field(fid)
                time.sleep(0.35)
                # 只展开 More（没给 class/title 时不会误点任何工具）
                drv.palette_click(fid, (), "", allow_more=True)
                time.sleep(0.35)
                data = drv.js(DUMP_JS)
                print(f"\n===== 输入框 {fid} =====")
                print(json.dumps(data, ensure_ascii=False, indent=2))
            except Exception as e:
                print(f"输入框 {fid} 探测失败：{e}")
            finally:
                drv.close_palette()
        if not fields:
            print(json.dumps(drv.js(DUMP_JS), ensure_ascii=False, indent=2))
    finally:
        drv.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
