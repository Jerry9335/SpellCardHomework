"""网页模式：通过 CDP（Chrome DevTools Protocol）直连浏览器，读 DOM、填答案、点交卷。

原理（学自参考实现「作业侠客」）：
1. 用 --remote-debugging-port 启动一个独立浏览器窗口；
2. 访问 http://127.0.0.1:<port>/json/list 拿到页面，连上 WebSocket；
3. 在题目所在 frame 里创建隔离执行环境，用 JS 读题干 / 单选框 / 输入框；
4. 把题干交给模型，要它回 CHOICE / MATRIX / VALUE 三行；
5. 用合成鼠标事件点选项、点输入框，Input.insertText 填值，矩阵走弹窗设置尺寸再逐格填；
6. 点 Check answer，读判分弹窗，答对点 Next，答错/异常就停。
"""
from __future__ import annotations

import base64
import json
import os
import re
import socket
import struct
import time
import urllib.parse
import urllib.request

from modules.choice_match import match_choice

DEFAULT_PORT = 9222


class CDPError(RuntimeError):
    pass


def cdp_pages(port: int = DEFAULT_PORT, timeout: float = 4.0) -> list[dict]:
    url = f"http://127.0.0.1:{port}/json/list"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        raise CDPError(f"连不上调试端口 {port}（用『启动答题浏览器.bat』打开浏览器）") from e
    return [p for p in data if p.get("type") == "page" and p.get("webSocketDebuggerUrl")]


class CDP:
    """够用就行的 WebSocket 客户端（只为本机调试端口写）。"""

    def __init__(self, url: str, timeout: float = 20.0) -> None:
        u = urllib.parse.urlsplit(url)
        self.sock = socket.create_connection((u.hostname, u.port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise CDPError("WebSocket 握手失败")
            buf += chunk
        if b" 101 " not in buf.split(b"\r\n", 1)[0]:
            raise CDPError("调试端口拒绝了 WebSocket")
        self.buf = buf.split(b"\r\n\r\n", 1)[1]
        self.mid = 0
        self.timeout = timeout
        self.events: list[dict] = []

    def _recv(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise CDPError("连接断了")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def _frame(self):
        h = self._recv(2)
        op = h[0] & 0x0F
        masked = h[1] & 0x80
        ln = h[1] & 0x7F
        if ln == 126:
            ln = struct.unpack(">H", self._recv(2))[0]
        elif ln == 127:
            ln = struct.unpack(">Q", self._recv(8))[0]
        mask = self._recv(4) if masked else b"\0\0\0\0"
        data = self._recv(ln) if ln else b""
        if masked:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        return op, data

    def _send(self, obj: dict) -> None:
        data = json.dumps(obj).encode("utf-8")
        mask = os.urandom(4)
        n = len(data)
        if n < 126:
            head = bytes([0x81, 0x80 | n])
        elif n < 65536:
            head = bytes([0x81, 0x80 | 126]) + struct.pack(">H", n)
        else:
            head = bytes([0x81, 0x80 | 127]) + struct.pack(">Q", n)
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def call(self, method: str, params: dict | None = None, timeout: float | None = None):
        self.mid += 1
        mid = self.mid
        self._send({"id": mid, "method": method, "params": params or {}})
        deadline = time.time() + (timeout or self.timeout)
        while time.time() < deadline:
            op, data = self._frame()
            if op != 1:
                continue
            try:
                msg = json.loads(data.decode("utf-8", "replace"))
            except Exception:
                continue
            if msg.get("id") == mid:
                if "error" in msg:
                    raise CDPError(str(msg["error"])[:160])
                return msg.get("result", {})
            if "method" in msg:
                self.events.append(msg)
                if len(self.events) > 800:
                    self.events = self.events[-500:]
        raise CDPError(f"{method} 超时")

    def close(self) -> None:
        try:
            self.sock.close()
        except Exception:
            pass


_CLICK_JS = (
    "(() => { const el = %s; if (!el) return 'no';"
    " const r = el.getBoundingClientRect();"
    " const o = {bubbles:true, cancelable:true, clientX:r.x+4, clientY:r.y+r.height/2, button:0};"
    " for (const t of ['pointerdown','mousedown','pointerup','mouseup','click'])"
    " el.dispatchEvent(new MouseEvent(t, o));"
    " return 'ok'; })()"
)

_STATE_JS = r"""
(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2; };
  const dlgs = [...document.querySelectorAll('[id*=ResizableDialog]')].filter(vis);
  const dlg = dlgs.length ? dlgs[dlgs.length - 1] : null;
  // 严格答题区根节点（学自 study-assistant）：
  //   .playerViewer > .contentPanel > .contentHolder
  // 找不到时回退旧的 contentHolder/top，再回退 body，保证旧 mock/旧 Pearson 仍可用。
  const playerRoot = document.querySelector('.playerViewer');
  let contentRoot = null;
  if (playerRoot) {
    const cp = playerRoot.querySelector('.contentPanel') || playerRoot;
    const cand = cp.querySelector('.contentHolder') || cp;
    // 只有这个根节点里真的有答题控件时才采用，避免某些布局把控件放在
    // playerViewer 外面（旧 mock / 特殊页面）导致快照变空。
    if (cand.querySelector('span.eqEditor, input[type=radio], input[type=checkbox], ' +
                           'input[type=text], input[type=number], select, .xlFillinItem')) {
      contentRoot = cand;
    }
  }
  if (!contentRoot) {
    contentRoot = document.getElementById('contentHolderbottom')
      || document.getElementById('contentHoldertop')
      || document.querySelector('.contentPanel .contentHolder')
      || document.body;
  }
  const scope = dlg || contentRoot;
  const clean = (s) => (s || '').replace(/\u200b/g, '').replace(/[ \t]+/g, ' ')
                      .replace(/ ?\n ?/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
  // 给每个答题控件一个页内唯一 UID，并记住对应的 DOM element。
  // 读题后页面换题/旧控件被替换时 UID 会变化；即使 Pearson 保留了旧属性，
  // __schElements 里“同一个 element”校验也能发现快照已过期。
  const uidOf = (el) => {
    let u = el.getAttribute && el.getAttribute('data-sch-uid');
    if (!u) {
      window.__schUidSeq = (window.__schUidSeq || 0) + 1;
      u = 'u' + window.__schUidSeq + '_' + Math.random().toString(36).slice(2, 8);
      try { el.setAttribute('data-sch-uid', u); } catch (e) {}
    }
    try {
      window.__schElements = window.__schElements || new Map();
      window.__schElements.set(u, el);
    } catch (e) {}
    return u;
  };
  const fields = [...scope.querySelectorAll('span.eqEditor')].filter(vis).map((el) => {
    const cs = getComputedStyle(el);
    const off = el.getAttribute('aria-disabled') === 'true'
      || /(^|\s)disabled(\s|$)/i.test(el.className || '')
      || !!el.closest('.disabled, [aria-disabled="true"]')
      || parseFloat(cs.opacity || '1') < 0.9;
    return {
      id: el.id, uid: uidOf(el), label: clean(el.getAttribute('aria-label')).slice(0, 120),
      readonly: /true/i.test(el.getAttribute('aria-readonly') || ''),
      disabled: off };
  });
  const radiosAll = [...scope.querySelectorAll('input[type=radio]')].filter(vis).map((el) => ({
    id: el.id, uid: uidOf(el), label: clean(el.getAttribute('aria-label')).slice(0, 160),
    checked: !!el.checked,
    disabled: !!el.disabled || /Disabled/.test(el.parentElement ? el.parentElement.className : '') }));
  // 只把「当前小问」的选项给模型/选择用；已答过的旧选项通常 disabled，会打乱字母对应
  const radios = radiosAll.filter((r) => !r.disabled);
  const radiosDisabled = radiosAll.length - radios.length;
  const inputs = [...scope.querySelectorAll('input[type=text], input[type=number], input[type=email]')]
      .filter(vis).filter((el) => !el.closest('span.eqEditor')).map((el) => ({
        id: el.id, uid: uidOf(el), label: clean(el.getAttribute('aria-label')).slice(0, 120),
        value: (el.value || '').slice(0, 200), disabled: !!el.disabled }));
  const checks = [...scope.querySelectorAll('input[type=checkbox]')].filter(vis).map((el) => ({
    id: el.id, uid: uidOf(el), label: clean(el.getAttribute('aria-label')).slice(0, 160),
    checked: !!el.checked, disabled: !!el.disabled }));
  const selects = [...scope.querySelectorAll('select')].filter(vis).map((el) => ({
    id: el.id, uid: uidOf(el), label: clean(el.getAttribute('aria-label')).slice(0, 120),
    value: el.value, options: [...el.options].map((o) => o.text.trim()).slice(0, 20) }));
  const sx = window.scrollX || 0, sy = window.scrollY || 0;
  const imgs = [...scope.querySelectorAll('img, canvas, svg')].filter((el) => {
    const r = el.getBoundingClientRect();
    return r.width > 60 && r.height > 60;
  }).map((el) => {
    const r = el.getBoundingClientRect();
    return { tag: el.tagName, x: r.x + sx, y: r.y + sy, w: r.width, h: r.height };
  });
  // 题目正文：只取内容区，选项分行，去掉判分提示和坐标轴刻度噪声
  // Pearson 会给图形一段无障碍描述（"A coordinate system has ..."），读数比看图准
  const descs = [...document.querySelectorAll('#contentHoldertop .rvParagraph, .rvParagraph')]
    .map((p) => clean(p.innerText))
    .filter((t) => t.length > 80 && /coordinate system|plotted point|axis labeled|curve (begins|rises|falls)/i.test(t));
  const desc = descs.slice(0, 2).join('\n');

  // 题干：整个 contentHoldertop（函数定义常在这里，不能只取第一段）
  const topEl = document.getElementById('contentHoldertop');
  let stem = topEl ? clean(topEl.innerText) : '';
  stem = stem.split('\n').filter((ln) => !/^(?:[-−–]?\d+(?:\.\d+)?\s+){6,}/.test(ln.trim())).join('\n');
  if (desc) stem = stem.split(desc).join(' ');
  stem = clean(stem).slice(0, 1200);

  const holder = document.getElementById('contentHolderbottom')
              || document.getElementById('contentHoldertop') || scope;
  let raw = clean(holder.innerText);
  if (stem && raw.indexOf(stem.slice(0, 24)) < 0) raw = stem + '\n\n' + raw;
  if (desc && raw.indexOf(desc.slice(0, 40)) < 0) raw = '【图注】' + desc + '\n\n' + raw;

  // 去掉判分提示
  raw = raw.replace(/Your answer is (correct|incorrect)\.?/gi, ' ');
  // 选项分行：在 "A. " "B. " ... 前面断行
  raw = raw.replace(/\s+(?=(?:[A-H][.)]\s))/g, '\n');
  // 去掉坐标轴刻度那种 "−10 −8 −6 ..." 噪声行
  raw = raw.split('\n').filter((ln) => !/^(?:[-−–]?\d+(?:\.\d+)?\s+){6,}/.test(ln.trim())).join('\n');
  // 选项字母和内容合到一行："A." + 换行 + 内容
  raw = raw.replace(/([A-H][.)])\s*\n\s*/g, '$1 ');
  // 去掉「读法 + 符号」重复行（如 7 紧接着 7x，或完全相同的两行）
  {
    const ls = raw.split('\n');
    const out = [];
    for (let i = 0; i < ls.length; i++) {
      const cur = ls[i].trim();
      const nxt = (ls[i + 1] || '').trim();
      const c = cur.replace(/\s+/g, '');
      const n = nxt.replace(/\s+/g, '');
      if (cur && nxt && (c === n || (n.startsWith(c) && n.length > c.length))) continue;
      out.push(ls[i]);
    }
    raw = out.join('\n');
  }
  // 空答案框的占位文字换成下划线
  raw = raw.replace(/enter your response here/gi, '____');
  // 压缩空行
  raw = raw.replace(/\n{3,}/g, '\n\n');
  // 选项没有 A/B 前缀（例如只有 No / Yes）时，补一份带字母的清单给模型
  if (radios.length && !radios.some((r) => /^[A-Z][.)]\s/.test(r.label))) {
    raw += '\n\n选项：\n' + radios.map((r, i) =>
      String.fromCharCode(65 + i) + '. ' + r.label).join('\n');
  }
  const text = clean(raw).slice(0, 4000);

  // 去重指纹：只跟题干/选项/控件有关，判分和弹窗不影响
  const qkey = [
    clean(raw).slice(0, 300),
    radios.map((r) => r.label).join('|').slice(0, 800),
    checks.map((c) => c.label).join('|').slice(0, 400),
    fields.map((f) => f.id).join(','),
    inputs.map((i) => i.id).join(','),
    selects.map((s) => s.id).join(','),
  ].join('#');
  const btn = (re) => [...document.querySelectorAll('button')].some((b) => {
    if (!vis(b)) return false;
    // 分字段判断：按钮的 innerText 和 title 常常一模一样，拼起来会变成 "X X"
    return [b.innerText, b.getAttribute('aria-label'), b.getAttribute('title')]
      .some((x) => x && re.test(x.trim()));
  });
  const btnEnabled = (re) => [...document.querySelectorAll('button')].some((b) => {
    if (!vis(b) || b.disabled || b.getAttribute('aria-disabled') === 'true') return false;
    return [b.innerText, b.getAttribute('aria-label'), b.getAttribute('title')]
      .some((x) => x && re.test(x.trim()));
  });
  // 当前做到第几小问（Pearson 顶部有 .progressText = "Part 2 of 5"）
  let partN = 0, partM = 0;
  const pt = document.querySelector('.progressText');
  if (pt) {
    const mm = /Part\s+(\d+)\s+of\s+(\d+)/i.exec(pt.innerText || '');
    if (mm) { partN = parseInt(mm[1], 10); partM = parseInt(mm[2], 10); }
  }

  // 题目区域（用于文字太乱时截图给视觉模型）
  let qrect = null;
  const holders = ['contentHoldertop', 'contentHolderbottom']
    .map((id) => document.getElementById(id)).filter(Boolean);
  if (holders.length) {
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    for (const e of holders) {
      const r = e.getBoundingClientRect();
      x0 = Math.min(x0, r.x); y0 = Math.min(y0, r.y);
      x1 = Math.max(x1, r.right); y1 = Math.max(y1, r.bottom);
    }
    if (x1 > x0 && y1 > y0) qrect = { x: x0 + sx, y: y0 + sy, w: x1 - x0, h: y1 - y0 };
  }

  const dropdowns = [...scope.querySelectorAll('.xlFillinItem')].filter(vis).map((el) => ({
    id: el.id, uid: uidOf(el), label: clean(el.getAttribute('aria-label') || '').slice(0, 200) }));

  // 字段 inventory：页面渲染出来的答题控件数量，必须和快照实际捕获的数量一致。
  // 少一个就说明还有控件没被识别（例如 Q14 的诱饵框/自定义控件），此时绝不让
  // 模型盲答；宁可刷新/记录待人工，也不能漏字段提交。
  const renderedEls = [...contentRoot.querySelectorAll(
      'span.eqEditor, input[type=text], input[type=number], input[type=email], ' +
      'input[type=radio], input[type=checkbox], select, .xlFillinItem')]
    .filter(vis)
    .filter((el) => !(el.matches('input[type=text], input[type=number], input[type=email]')
                      && el.closest('span.eqEditor')))
    .filter((el) => !(el.matches('select') && el.closest('.xlFillinItem')));
  const capturedCount = fields.length + inputs.length + radiosAll.length
                      + checks.length + selects.length + dropdowns.length;
  const missingGroups = [...contentRoot.querySelectorAll('.xlMultipleChoice')]
    .filter(vis)
    .filter((g) => ![...g.querySelectorAll('input[type=radio], input[type=checkbox]')]
      .some(vis)).length;
  const inventory = {
    rendered: renderedEls.length,
    captured: capturedCount,
    missing: Math.max(0, renderedEls.length - capturedCount) + missingGroups,
    groups: missingGroups,
    root: String(contentRoot.id || contentRoot.className || contentRoot.tagName || '')
      .slice(0, 80),
  };
  const incomplete = inventory.missing > 0;

  // Pearson 左侧题号列表：aria-label = "Question N, Correct / Partially correct"
  const questions = [...document.querySelectorAll('a.questionLabel')].map((a) => {
    const m = /Question\s+(\d+)/i.exec(a.innerText || '');
    return { n: m ? parseInt(m[1], 10) : 0,
             status: clean(a.getAttribute('aria-label') || ''),
             selected: !!(a.closest('li.selected')) };
  }).filter((x) => x.n > 0);
  const selectedQ = questions.find((x) => x.selected);
  const qno = selectedQ ? selectedQ.n : 0;

  // 内嵌图形题：返回图形控件和坐标轴映射，供自动绘图使用
  let graph = null;
  const gEl = document.querySelector('.graphControl .xygraph, .xygraph');
  if (gEl) {
    const gr = gEl.getBoundingClientRect();
    if (gr.width > 80 && gr.height > 80) {
      let xmin = -6, xmax = 6, ymin = -20, ymax = 10;
      for (const d of [...gEl.querySelectorAll('[data-dojo-props]')]) {
        const p = d.getAttribute('data-dojo-props') || '';
        const mm = /minimum:\s*(-?\d+(?:\.\d+)?).*?maximum:\s*(-?\d+(?:\.\d+)?)/.exec(p);
        if (!mm) continue;
        if (/orientation:\s*(?:&quot;|"|')?horizontal/i.test(p)) {
          xmin = parseFloat(mm[1]); xmax = parseFloat(mm[2]);
        } else if (/orientation:\s*(?:&quot;|"|')?vertical/i.test(p)) {
          ymin = parseFloat(mm[1]); ymax = parseFloat(mm[2]);
        }
      }
      let x0 = gr.left + 18, x1 = gr.right - 18;
      let y0 = gr.top + 20, y1 = gr.bottom - 20;
      for (const ln of [...gEl.querySelectorAll('line')]) {
        const rr = ln.getBoundingClientRect();
        if (rr.width > 200 && rr.height < 2) { x0 = rr.left; x1 = rr.right; }
        if (rr.width < 2 && rr.height > 150) { y0 = rr.top; y1 = rr.bottom; }
      }
      graph = { x: gr.x, y: gr.y, w: gr.width, h: gr.height,
                x0: x0, x1: x1, y0: y0, y1: y1,
                xmin: xmin, xmax: xmax, ymin: ymin, ymax: ymax };
    }
  }

  // 唯一 Check 候选：避免页面上同时存在旧 Check/新 Check 时点错。
  // 只认可见、且文字/aria-label/title 精确等于 Pearson 的三种 Check 文案。
  const checkCandidates = [...document.querySelectorAll(
      'button, input[type=submit], input[type=button], [role="button"]')]
    .filter(vis)
    .map((el) => {
      const labels = [el.innerText, el.value,
                      el.getAttribute?.('aria-label'), el.getAttribute?.('title')]
        .map((x) => clean(x || '').replace(/\s+/g, ' ')).filter(Boolean);
      const hit = labels.find((x) => /^(?:check answer|check my answer|final check)$/i.test(x));
      if (!hit) return null;
      return {
        id: el.id, uid: uidOf(el),
        enabled: !el.disabled && el.getAttribute('aria-disabled') !== 'true',
        label: hit.slice(0, 80),
      };
    })
    .filter(Boolean);

  // 题目身份 / 字段身份：供 app.pyw 在“模型思考期间页面换题”时丢弃旧答案。
  const identity = clean((document.querySelector('.playerViewer h3') || {}).innerText || '');
  const problemKey = [identity, text.slice(0, 800)].join('|');
  const signature = JSON.stringify([
    identity,
    text.slice(0, 1200),
    fields.map((f) => [f.uid, f.id, f.label, !!f.disabled]),
    radios.map((r) => [r.uid, r.id, r.label, !!r.checked]),
    checks.map((c) => [c.uid, c.id, c.label, !!c.checked]),
    inputs.map((i) => [i.uid, i.id, i.label, i.value || '', !!i.disabled]),
    selects.map((s) => [s.uid, s.id, s.value, s.options]),
    dropdowns.map((d) => [d.uid, d.id, d.label]),
  ]);

  const checkUnique = checkCandidates.length === 1 && checkCandidates[0].enabled;
  return { text: text, qkey: qkey, rect: qrect, part: [partN, partM], fields: fields, radios: radios,
           dropdowns: dropdowns, questions: questions, qno: qno, graph: graph,
           radios_disabled: radiosDisabled, inputs: inputs,
           checks: checks, selects: selects, imgs: imgs,
           identity: identity, problemKey: problemKey, signature: signature,
           inventory: inventory, incomplete: incomplete,
           checkCandidates: checkCandidates,
           hasCheck: checkCandidates.length > 0 || btn(/^(check answer|final check)$/i),
           canCheck: checkUnique,
           hasNext: btn(/^(next|next question)$/i),
           inDialog: !!dlg };
})()
"""

_PALETTE_CLICK_JS = r"""
(() => {
  const vis = (e) => { if (!e) return false; const r = e.getBoundingClientRect();
                       return r.width > 2 && r.height > 2; };
  let pals = [...document.querySelectorAll('div.xlInlineMathPalette')].filter(vis);
  if (!pals.length) {
    // 有的题目输入框弹出的是底部宽键盘面板（xlKeyboardDialog），不是内联调色板
    pals = [...document.querySelectorAll(
        'div.xlKeyboardDialog, [class*=KeyboardDialog], [data-dojo-attach-point="paletteNode"]')]
      .filter((p) => vis(p) && p.querySelector('button'));
  }
  if (!pals.length) return 'no-palette';
  const field = document.getElementById(%s);
  let pal = pals[pals.length - 1];
  if (field) {
    // 多空题每个空各挂一个调色板：取离目标输入框最近的那个
    const fr = field.getBoundingClientRect();
    let bd = 1e9;
    for (const p of pals) {
      const r = p.getBoundingClientRect();
      const d = Math.abs(r.top - fr.top) + Math.abs(r.left - fr.left);
      if (d < bd) { bd = d; pal = p; }
    }
  }
  const classes = %s;
  const titleRe = new RegExp(%s || '(?!)', 'i');
  const buttons = () => [...pal.querySelectorAll('button')].filter(vis);
  const labelsOf = (b) => [(b.getAttribute('title') || '').trim(),
                           (b.getAttribute('aria-label') || '').trim(),
                           (b.textContent || '').trim()];
  const matches = (b) => {
    const cls = String(b.className || '').split(/\s+/);
    if (classes.some((c) => cls.indexOf(c) >= 0)) return true;
    return labelsOf(b).some((t) => t && titleRe.test(t));
  };
  const btn = buttons().find(matches);
  if (btn) { btn.click(); return 'ok'; }
  if (%s) {
    const more = buttons().find((b) => labelsOf(b).some((t) => /more|更多/i.test(t)));
    if (more) { more.click(); return 'more-opened'; }
    // 已经停在第二页时，工具不在这一页就得点 Less 回第一页再找一次
    const less = buttons().find((b) => labelsOf(b).some((t) => /^(less|back)$/i.test(t)));
    if (less) { less.click(); return 'less-opened'; }
    return 'no-tool';
  }
  return 'no-tool';
})()
"""



_PLAYER_STATE_JS = r"""
(() => {
  const out = {ok: false, correctness: null, feedbackOpen: false, resultPosted: 0,
               controls: 0, answered: 0, correct: 0, partial: 0, error: ''};
  try {
    // 真实 Pearson 不保证有全局 dijit；它通常暴露 AMD require。
    // 先用已缓存的 registry；没有就异步加载一次并缓存，下一次调用即可用。
    let d = window.dijit || window.__schDijitRegistry;
    if (!d && typeof window.require === 'function'
            && !window.__schDijitLoading && !window.__schDijitError) {
      window.__schDijitLoading = true;
      try {
        window.require(['dijit/registry'], (registry) => {
          window.__schDijitRegistry = registry;
          window.__schDijitLoading = false;
        }, (err) => {
          window.__schDijitLoading = false;
          window.__schDijitError = String((err && err.message) || err || 'require failed');
        });
      } catch (e) {
        window.__schDijitLoading = false;
        window.__schDijitError = String((e && e.message) || e);
      }
    }
    if (!d) {
      out.error = window.__schDijitError || (window.__schDijitLoading ? 'loading' : 'no-dijit');
      return out;
    }
    const byNode = (el) => {
      try {
        if (typeof d.byNode === 'function') return d.byNode(el);
        if (typeof d.getEnclosingWidget === 'function') return d.getEnclosingWidget(el);
        if (typeof d.byId === 'function' && el && el.id) return d.byId(el.id);
        if (el && el.__widget) return el.__widget;
      } catch (e) {}
      return null;
    };
    const pvEl = document.querySelector('.playerViewer');
    const pv = pvEl ? byNode(pvEl) : null;
    if (pv) {
      if (pv._correctness !== undefined && pv._correctness !== null) {
        out.correctness = pv._correctness;
      } else if (pv.correctness !== undefined && pv.correctness !== null) {
        out.correctness = pv.correctness;
      }
      out.feedbackOpen = !!(pv.feedbackOpened || pv.feedbackOpen);
      const rp = pv.resultsposted;
      out.resultPosted = (typeof rp === 'number') ? rp : (rp ? 1 : 0);
    }
    const controls = [...document.querySelectorAll('.inputField, .xlMultipleChoice')];
    out.controls = controls.length;
    for (const el of controls) {
      const w = byNode(el);
      if (!w) continue;
      if (w.isAnswered) out.answered++;
      if (w.isCorrect === true) out.correct++;
      if (w.isCorrect === 'partial' || w.isCorrect === 'partially') out.partial++;
      const states = w.answeredStates;
      if (states && typeof states === 'object') {
        try {
          const vals = Array.isArray(states) ? states : Object.values(states);
          for (const v of vals) {
            if (v === true || v === 'correct' || v === 'Correct') out.correct++;
            if (v === 'partial' || v === 'Partial' ||
                v === 'partially correct' || v === 'Partially correct') out.partial++;
          }
        } catch (e) {}
      }
    }
    out.ok = true;
    return out;
  } catch (e) {
    out.error = String((e && e.message) || e);
    return out;
  }
})()
"""

_MATH_JS = r"""
(() => {
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const vis = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const scope = document.getElementById('contentHoldertop')
             || document.getElementById('contentHolderbottom') || document.body;
  const out = [], seen = new Set();
  const add = (s) => {
    s = clean(s);
    if (!s || s.length > 500 || seen.has(s)) return;
    seen.add(s); out.push(s);
  };
  for (const el of scope.querySelectorAll('math, mjx-container, .MathJax, .katex, [data-latex], annotation[encoding*="tex" i]')) {
    if (!vis(el)) continue;
    add(el.getAttribute('data-latex') || el.getAttribute('aria-label')
        || el.getAttribute('alt') || el.textContent || '');
  }
  return out.slice(0, 20);
})()
"""

_COMPLETION_JS = r"""
(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2; };
  const clean = (s) => (s || '').replace(/\u200b/g, '').replace(/\s+/g, ' ').trim();
  const good = /\b(well done|good job|good work|nice job|fantastic|correct|great job|nice work|excellent|way to go|perfect|that'?s right|right answer|you got it)\b/i;
  const bad = /\b(incorrect|not quite|not correct|try again|not right|sorry|almost|check your work)\b/i;
  const finished = /\b(homework (is )?complete|you have completed|assignment complete|all done)\b/i;
  const leave = /(leave this question|not completed this question|continue without checking|are you sure you want to (leave|continue))/i;

  const cands = [...document.querySelectorAll(
      '[role=dialog], [id*=Dialog], [class*=Dialog], [class*=feedback], ' +
      '[class*=Feedback], [id*=Popup], [class*=Popup]')]
    .filter(vis)
    .map((el) => {
      const text = clean(el.innerText);
      const buttons = [...el.querySelectorAll('button, a, [role=button]')]
        .filter(vis).map((b) => ({
          id: b.id || '',
          text: clean(b.innerText || b.getAttribute('aria-label') || b.getAttribute('title')),
          disabled: !!(b.disabled || b.getAttribute('aria-disabled') === 'true'),
        })).filter((b) => b.text);
      return { id: el.id || '', text, buttons };
    })
    .filter((c) => c.text && c.text.length <= 800 && c.buttons.length);

  const kindOf = (t) => {
    if (leave.test(t)) return 'leave';
    if (bad.test(t)) return 'incorrect';
    if (finished.test(t)) return 'finished';
    if (good.test(t)) return 'correct';
    return '';
  };
  const ranked = cands.map((c) => ({ ...c, kind: kindOf(c.text) }))
    .filter((c) => c.kind)
    .map((c, i) => ({ ...c, i }));
  // 最后一个（最上层）优先
  const hit = ranked.length ? ranked[ranked.length - 1] : null;

  const btnText = (b) => (b.text || '').trim();
  const okBtn = hit ? hit.buttons.find((b) => /^(ok|continue|got it|close|dismiss)$/i.test(btnText(b))) : null;
  const nextBtn = hit ? hit.buttons.find((b) => /^(next( question)?|go to next.*)$/i.test(btnText(b))) : null;

  const btnInfo = (re) => [...document.querySelectorAll('button')].filter(vis).map((b) => ({
    id: b.id || '',
    text: clean(b.innerText || b.getAttribute('aria-label') || b.getAttribute('title')),
    disabled: !!(b.disabled || b.getAttribute('aria-disabled') === 'true'),
  })).find((b) => re.test(b.text));
  const check = btnInfo(/^(check answer|final check)$/i);
  const next = btnInfo(/^(next|next question)$/i);

  return {
    kind: hit ? hit.kind : 'none',
    text: hit ? hit.text : '',
    dialogId: hit ? hit.id : '',
    hasOk: !!okBtn,
    hasNext: !!nextBtn,
    okId: okBtn ? okBtn.id : '',
    nextId: nextBtn ? nextBtn.id : '',
    buttons: hit ? hit.buttons : [],
    checkVisible: !!check,
    checkEnabled: !!(check && !check.disabled),
    nextVisible: !!next,
  };
})()
"""

_FEEDBACK_JS = r"""
(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2; };
  const good = /\b(well done|good job|good work|nice job|fantastic|correct|great|nice work|excellent|way to go|perfect|that'?s right|right answer|you got it)\b/i;
  const bad = /\b(incorrect|not quite|try again|not right|sorry|almost|check your work|no\.)\b/i;
  const cands = [...document.querySelectorAll('[role=dialog], [id*=Dialog], [class*=feedback]')]
      .filter(vis);
  for (const d of cands.reverse()) {
    const hasOk = [...d.querySelectorAll('button')].some(
        (b) => /^\s*ok\s*$/i.test((b.innerText || '').trim()));
    const t = (d.innerText || '').replace(/\s+/g, ' ').trim();
    if (!t || t.length > 200) continue;
    if (bad.test(t)) return 'incorrect';
    if (hasOk || good.test(t)) return 'correct';
  }
  return '';
})()
"""


class WebPlayer:
    """连着答题浏览器：读题、填答案、点交卷。"""

    def __init__(self, port: int = DEFAULT_PORT, log=None) -> None:
        self.port = port
        self.ws: CDP | None = None
        self.ctx = None
        self.title = ""
        self.log = log or (lambda _m: None)

    # ---- 连接
    def connect(self) -> "WebPlayer":
        pages = cdp_pages(self.port)
        # 只挑真正的网页：跳过 edge://sync-confirmation-dialog、about:blank 这类
        pages = [p for p in pages if (p.get("url") or "").startswith(("http://", "https://"))]
        hit = [p for p in pages if "PlayerHomework" in p.get("url", "")
               or "Player.aspx" in p.get("url", "")]
        # 多个 Player 页时取最近打开的那个（列表末尾），避免连到旧标签页
        page = (hit[-1] if hit else (pages[-1] if pages else None))
        if not page:
            raise CDPError("浏览器里没有页面")
        self.ws = CDP(page["webSocketDebuggerUrl"])
        self.ws.call("Page.enable")
        self.ws.call("Runtime.enable")
        self.title = page.get("title", "")
        self.ctx = None
        self.player_frame = ""
        try:
            tree = self.ws.call("Page.getFrameTree")["frameTree"]

            def walk(node):
                f = node["frame"]
                if "Player/Player.aspx" in (f.get("url") or ""):
                    self.player_frame = f["id"]
                for c in node.get("childFrames", []):
                    walk(c)

            walk(tree)
        except Exception:
            self.player_frame = ""
        # 不再注入主世界 Agent：全部操作走隔离世界 DOM 与一次性主世界求值。
        self.log(f"已连接：{self.title[:60] or page.get('url', '')[:60]}")
        return self

    def close(self) -> None:
        if self.ws:
            self.ws.close()
            self.ws = None

    # ---- 基础
    def _player_ctx(self) -> int:
        tree = self.ws.call("Page.getFrameTree")["frameTree"]
        hit: list[str] = []

        def walk(node):
            f = node["frame"]
            if "Player/Player.aspx" in f.get("url", ""):
                hit.append(f["id"])
            for c in node.get("childFrames", []):
                walk(c)

        walk(tree)
        frame_id = hit[0] if hit else tree["frame"]["id"]
        r = self.ws.call("Page.createIsolatedWorld", {"frameId": frame_id, "worldName": "shinichi"})
        return r["executionContextId"]

    def js(self, expr: str, timeout: float = 20.0):
        for attempt in (1, 2):
            if self.ctx is None:
                self.ctx = self._player_ctx()
            try:
                r = self.ws.call("Runtime.evaluate",
                                 {"expression": expr, "contextId": self.ctx, "returnByValue": True},
                                 timeout=timeout)
            except CDPError as e:
                # 页面换题/跳转会让执行上下文失效，重建一次再试
                if attempt == 1 and "context" in str(e).lower():
                    self.ctx = None
                    time.sleep(0.4)
                    continue
                raise
            if "exceptionDetails" in r:
                raise CDPError("页面脚本出错：" + str(r["exceptionDetails"].get("text"))[:120])
            return r["result"].get("value")

    def insert(self, text: str) -> None:
        self.ws.call("Input.insertText", {"text": text})

    def key(self, k: str, code: str, vk: int, mods: int = 0) -> None:
        for t in ("keyDown", "keyUp"):
            self.ws.call("Input.dispatchKeyEvent",
                         {"type": t, "key": k, "code": code,
                          "windowsVirtualKeyCode": vk, "modifiers": mods})

    def main_context_id(self) -> int | None:
        """Player iframe 的 main world 上下文；Dojo 全局只在这里可见。"""
        frame = getattr(self, "player_frame", "")
        for msg in getattr(self.ws, "events", []):
            if msg.get("method") != "Runtime.executionContextCreated":
                continue
            c = msg.get("params", {}).get("context", {})
            aux = c.get("auxData") or {}
            if aux.get("isDefault") and (not frame or aux.get("frameId") == frame):
                return int(c.get("id"))
        return None

    def eval_main(self, expr: str):
        cid = self.main_context_id()
        if cid is None:
            return None
        r = self.ws.call("Runtime.evaluate",
                         {"expression": expr, "contextId": cid, "returnByValue": True})
        if "exceptionDetails" in r:
            raise CDPError(str(r["exceptionDetails"].get("text"))[:160])
        return r.get("result", {}).get("value")

    _GRAPH_POPUP = (
        "(() => {const ps=[...document.querySelectorAll('[id*=GraphZoomPopup]')];"
        "return !!ps.find(e=>{const r=e.getBoundingClientRect();"
        "return r.width>200 && r.height>150 && getComputedStyle(e).display!=='none';});})()"
    )

    def graph_modal_open(self) -> bool:
        try:
            return bool(self.js(self._GRAPH_POPUP))
        except Exception:
            return False

    def open_graph_modal(self) -> bool:
        if self.graph_modal_open():
            return True
        try:
            got = self.js(
                "(() => {const b=[...document.querySelectorAll('button')]"
                ".find(x => (x.innerText||'').toLowerCase().includes('enlarge'));"
                "if (!b) return 'no'; b.click(); return 'ok';})()")
        except Exception:
            got = "no"
        if got != "ok":
            return False
        for _ in range(8):
            time.sleep(0.35)
            if self.graph_modal_open():
                return True
        return False

    def draw_quadratic(self, points: list[tuple[float, float]]) -> str:
        """在放大图形框里用 Dojo GraphControl API 画二次函数。"""
        if not self.open_graph_modal():
            return "no-modal"
        pts = [[float(x), float(y)] for x, y in points]
        js = """(() => {
  const ps = [...document.querySelectorAll('[id*=GraphZoomPopup]')];
  const pop = ps.find(e => {const r=e.getBoundingClientRect();
      return r.width>200 && r.height>150 && getComputedStyle(e).display!=='none'
             && e.querySelector('.xygraph');});
  if (!pop) return 'no-popup';
  const el = pop.querySelector('.xygraph');
  if (!el) return 'no-graph';
  const gw = dijit.byId(el.id);
  if (!gw) return 'no-widget';
  const ctl = gw._graphControl;
  const m = ctl.getGraphManager();
  try { m.clearGraphObjects(); } catch (e) {}
  ctl._paletteToolSelected({cmd: 'quadratic'});
  const t = m.getCurrentTool();
  if (!t) return 'no-tool';
  const pts = %s;
  for (const p of pts) t.addPoint({x: p[0], y: p[1]});
  m.completeTool();
  ctl.getGraph().validateGraph();
  return 'ok';
})()""" % json.dumps(pts)
        try:
            got = self.eval_main(js)
        except Exception:
            return "draw-error"
        if got != "ok":
            return str(got or "draw-failed")
        # 点放大框自己的 Save（不要点页面顶部那个 Save）
        try:
            saved = self.eval_main(
                "(() => {const ps=[...document.querySelectorAll('[id*=GraphZoomPopup]')];"
                "const pop=ps.find(e=>{const r=e.getBoundingClientRect();"
                "return r.width>200&&r.height>150&&getComputedStyle(e).display!=='none'"
                "&&e.querySelector('.xygraph');});"
                "if(!pop)return 'no-popup';"
                "const b=[...pop.querySelectorAll('button')]"
                ".find(x=>(x.innerText||'').trim()==='Save');"
                "if(!b)return 'no-save';"
                "const w=dijit.byId(b.id);"
                "if(w&&w.onClick)w.onClick();else b.click();"
                "return 'ok';})()")
        except Exception:
            saved = "save-error"
        time.sleep(0.8)
        if self.graph_modal_open():
            # 有些 Pearson 弹窗会叠多层；Save 已把图形写回，隐藏残余弹窗
            try:
                self.eval_main(
                    "(() => {for(const e of [...document.querySelectorAll('[id*=GraphZoomPopup]')]){"
                    "const w=dijit.byId(e.id);if(w&&w.hide)w.hide();}"
                    "return 'ok';})()")
            except Exception:
                pass
            time.sleep(0.5)
        if self.graph_modal_open():
            return "save-not-closed"
        return str(saved or "saved")

    def add_graph_objects(self, objects: list[dict]) -> str:
        """在放大图形框里直接写入多个 GraphControl 对象（line/quadratic）。"""
        if not self.open_graph_modal():
            return "no-modal"
        js = """(() => {
  const ps = [...document.querySelectorAll('[id*=GraphZoomPopup]')];
  const pop = ps.find(e => {const r=e.getBoundingClientRect();
      return r.width>200 && r.height>150 && getComputedStyle(e).display!=='none'
             && e.querySelector('.xygraph');});
  if (!pop) return 'no-popup';
  const el = pop.querySelector('.xygraph');
  const gw = dijit.byId(el.id);
  if (!gw) return 'no-widget';
  const ctl = gw._graphControl;
  const m = ctl.getGraphManager();
  m.clearGraphObjects();
  m.initGraphObjects(%s, -1);
  ctl.getGraph().validateGraph();
  return 'ok';
})()""" % json.dumps(objects)
        try:
            got = self.eval_main(js)
        except Exception:
            return "draw-error"
        if got != "ok":
            return str(got or "draw-failed")
        try:
            saved = self.eval_main(
                "(() => {const ps=[...document.querySelectorAll('[id*=GraphZoomPopup]')];"
                "const pop=ps.find(e=>{const r=e.getBoundingClientRect();"
                "return r.width>200&&r.height>150&&getComputedStyle(e).display!=='none'"
                "&&e.querySelector('.xygraph');});"
                "if(!pop)return 'no-popup';"
                "const b=[...pop.querySelectorAll('button')]"
                ".find(x=>(x.innerText||'').trim()==='Save');"
                "if(!b)return 'no-save';"
                "const w=dijit.byId(b.id);"
                "if(w&&w.onClick)w.onClick();else b.click();"
                "return 'ok';})()")
        except Exception:
            saved = "save-error"
        time.sleep(0.8)
        if self.graph_modal_open():
            try:
                self.eval_main(
                    "(() => {for(const e of [...document.querySelectorAll('[id*=GraphZoomPopup]')]){"
                    "const w=dijit.byId(e.id);if(w&&w.hide)w.hide();}return 'ok';})()")
            except Exception:
                pass
            time.sleep(0.5)
        if self.graph_modal_open():
            return "save-not-closed"
        return str(saved or "saved")

    def add_graph_objects_inline(self, objects: list[dict]) -> str:
        """优先操作页面内嵌图（不进放大弹窗）。只写入图形模型，不点页面顶部 Save。"""
        js = """(() => {
  const el = document.querySelector('.graphControl .xygraph') ||
             document.querySelector('.xygraph');
  if (!el) return 'no-inline';
  const gw = dijit.byId(el.id);
  if (!gw || !gw._graphControl) return 'no-widget';
  const ctl = gw._graphControl;
  const m = ctl.getGraphManager();
  try { m.clearGraphObjects(); } catch (e) {}
  m.initGraphObjects(%s, -1);
  ctl.getGraph().validateGraph();
  return 'ok';
})()""" % json.dumps(objects)
        try:
            got = self.eval_main(js)
        except Exception:
            got = "error"
        if got != "ok":
            return str(got or "inline-failed")
        time.sleep(0.5)
        return "ok"

    # ---- 读
    def state(self) -> dict:
        try:
            v = self.eval_main(_STATE_JS)
            if isinstance(v, dict) and (v.get("questions") or v.get("text")):
                return v
        except Exception:
            pass
        return self.js(_STATE_JS) or {}

    def player_state(self) -> dict:
        """读 Pearson Dojo player 的内部判分状态（学自 study-assistant player-bridge）。

        `_correctness` / `feedbackOpened` / 控件 widget 的 isAnswered/isCorrect
        比纯 DOM 文本稳定；拿不到 Dojo 时返回 ok=False，调用方回退 DOM。
        """
        last = None
        for _ in range(4):
            try:
                v = self.eval_main(_PLAYER_STATE_JS)
                if isinstance(v, dict):
                    last = v
                    if v.get("ok"):
                        return v
                    # AMD registry 首次加载是异步的；只对 loading 稍等，
                    # no-dijit/require 失败则立即回退，不拖慢主流程。
                    if str(v.get("error") or "") != "loading":
                        return v
            except Exception:
                pass
            time.sleep(0.35)
        if last:
            return last
        return {"ok": False, "correctness": None, "feedbackOpen": False,
                "resultPosted": 0, "controls": 0, "answered": 0,
                "correct": 0, "partial": 0, "error": "exception"}

    def check_state(self) -> dict:
        """当前可见 Check 按钮的唯一性/可用性（用于避免点到旧 Check）。"""
        try:
            st = self.state() or {}
            cands = [c for c in (st.get("checkCandidates") or []) if isinstance(c, dict)]
            enabled = [c for c in cands if c.get("enabled")]
            return {"count": len(cands), "enabled": len(enabled),
                    "ok": len(cands) == 1 and len(enabled) == 1,
                    "candidates": cands}
        except Exception:
            return {"count": 0, "enabled": 0, "ok": False, "candidates": []}

    def click_check_unique(self) -> str:
        """唯一 Check 才点；0 个/多个/禁用都返回原因，绝不盲点。"""
        cs = self.check_state()
        n = int(cs.get("count") or 0)
        if n == 0:
            return "none"
        if n > 1:
            return "multiple"
        c = (cs.get("candidates") or [{}])[0]
        if not c.get("enabled"):
            return "disabled"
        uid = str(c.get("uid") or "")
        cid = str(c.get("id") or "")
        expr = ("document.querySelector('[data-sch-uid=%s]')" % json.dumps(uid)) \
            if uid else ("document.getElementById(%s)" % json.dumps(cid))
        try:
            res = self.js(_CLICK_JS % expr)
            if res == "ok":
                time.sleep(0.45)
                return "ok"
            return str(res or "no")
        except Exception:
            return "no"

    def field_present(self, uid: str) -> bool:
        """校验字段 UID 是否仍存在于当前页面（防止旧快照填新页面）。"""
        uid = str(uid or "")
        if not uid:
            return False
        js = """(() => {
  const uid = %s;
  const el = document.querySelector('[data-sch-uid="' + uid + '"]');
  if (!el) return false;
  // 同一 UID 必须还是快照时记住的那个 element。Pearson 有时会重建 DOM
  // 但保留旧属性；只查 UID 会把“新控件”误当成“旧控件”。
  try {
    const mem = window.__schElements;
    if (mem && mem.size && mem.get(uid) !== el) return false;
  } catch (e) {}
  const r = el.getBoundingClientRect();
  if (r.width <= 1 || r.height <= 1) return false;
  const cs = getComputedStyle(el);
  return cs.display !== 'none' && cs.visibility !== 'hidden';
})()""" % json.dumps(uid)
        try:
            # __schElements 建在主世界，必须用 eval_main 才能看到。
            return bool(self.eval_main(js))
        except Exception:
            try:
                return bool(self.js(js))
            except Exception:
                return False

    def math_text(self) -> list:
        """从 MathML/KaTeX/MathJax/data-latex 提取公式文本（学自 Auto-Pearson math.js）。"""
        try:
            v = self.js(_MATH_JS)
            return [str(x) for x in (v or []) if str(x).strip()][:20]
        except Exception:
            return []

    def completion_state(self) -> dict:
        """返回当前判分/警告弹窗的结构化状态（学自 Auto-Pearson completionState）。

        - kind: correct / incorrect / finished / leave / none
        - hasOk / hasNext: 只统计**这个弹窗内部**的按钮
        - checkVisible / checkEnabled: 页面上的 Check 按钮状态
        """
        try:
            v = self.js(_COMPLETION_JS)
            if isinstance(v, dict):
                return v
        except Exception:
            pass
        return {"kind": "none", "hasOk": False, "hasNext": False,
                "checkVisible": False, "checkEnabled": False}

    def feedback(self) -> str:
        """判分结果。兼容旧接口：correct / incorrect / ''。"""
        st = self.completion_state()
        kind = str(st.get("kind") or "")
        if kind in ("correct", "finished"):
            return "correct"
        if kind == "incorrect":
            return "incorrect"
        try:
            return self.js(_FEEDBACK_JS) or ""
        except Exception:
            return ""

    def click_completion(self, action: str = "ok") -> str:
        """只点当前反馈弹窗内部的 OK/Next，绝不点弹窗后面的旧按钮。"""
        st = self.completion_state()
        if not st or st.get("kind") in ("", "none"):
            return "no"
        bid = st.get("nextId") if action == "next" else st.get("okId")
        if bid:
            try:
                return self.js(_CLICK_JS % ("document.getElementById(%s) || null"
                                            % json.dumps(str(bid)))) or "no"
            except Exception:
                return "no"
        # 没有 id 时退回文字查找；再次确认弹窗仍在，避免点到旧 Check
        pattern = r"^next( question)?$" if action == "next" else \
            r"^(ok|continue|got it|close|dismiss)$"
        try:
            if action == "next" and not st.get("hasNext"):
                return "no"
            if action != "next" and not st.get("hasOk"):
                return "no"
            return self.click_text(pattern)
        except Exception:
            return "no"

    def _force_hide_dialog(self, dialog_id: str) -> str:
        """兜底：Pearson 的 FeedbackMessage 有时已把页面推进到下一小问，
        但弹窗 DOM 没消失（Dojo widget.open 已是 false）。这时只隐藏这个
        残留节点，不点弹窗后面的旧 Check/Next。"""
        if not dialog_id:
            return "no"
        js = """(() => {
  const id = %s;
  for (const el of [document.getElementById(id),
                    document.getElementById(id + '_underlay')]) {
    if (el) { el.style.display = 'none'; el.setAttribute('aria-hidden', 'true'); }
  }
  return 'hidden';
})()""" % json.dumps(dialog_id)
        try:
            return self.js(js) or "no"
        except Exception:
            return "no"

    def _feedback_widget_open(self, dialog_id: str):
        """返回 Dojo FeedbackMessage widget 的 open 状态；拿不到返回 None。"""
        if not dialog_id:
            return None
        js = """(() => {
  if (!window.dijit || !dijit.byId) return null;
  const w = dijit.byId(%s);
  return w ? !!w.open : null;
})()""" % json.dumps(dialog_id)
        try:
            return self.eval_main(js)
        except Exception:
            return None

    def dismiss_feedback(self) -> str:
        """关闭当前判分弹窗（只点弹窗内 OK）；处理 Pearson 的残留弹窗。"""
        st = self.completion_state()
        did = str(st.get("dialogId") or "")
        res = self.click_completion("ok")
        if not did:
            return res
        # 正常情况：点 OK 后弹窗消失/页面换题
        for _ in range(10):
            time.sleep(0.2)
            cur = self.completion_state()
            if cur.get("kind") in ("", "none") or cur.get("dialogId") != did:
                return res
        # 异常：DOM 还显示，但 Dojo 已经认为它关闭了（Pearson 偶发）
        if self._feedback_widget_open(did) is False:
            self._force_hide_dialog(did)
            return "ok-stale"
        return res

    def goto_question(self, n: int) -> str:
        """点左侧题号，跳到指定 Question（不依赖 Next 按钮）。"""
        js = r"""(() => {
  const a = [...document.querySelectorAll('a.questionLabel')]
      .find(x => /^Question\s+%d$/i.test((x.innerText || '').trim()));
  if (!a) return 'no';
  a.scrollIntoView({block: 'center'});
  a.click();
  return 'ok';
})()""" % int(n)
        for _ in range(2):
            try:
                if self.js(js) == "ok":
                    return "ok"
            except Exception:
                pass
            time.sleep(0.35)
        return "no"

    def click_graph_tool(self, title: str) -> str:
        js = """(() => {
  const b = [...document.querySelectorAll('button')].find(
      x => (x.getAttribute('title') || '').trim() === %s);
  if (!b) return 'no';
  b.click();
  return 'ok';
})()""" % json.dumps(title)
        try:
            return self.js(js) or "no"
        except Exception:
            return "no"

    def click_graph_at(self, page_x: float, page_y: float) -> None:
        for typ in ("mousePressed", "mouseReleased"):
            self.ws.call("Input.dispatchMouseEvent",
                         {"type": typ, "x": page_x, "y": page_y,
                          "button": "left", "clickCount": 1},
                         timeout=10)

    def graph_point(self, x: float, y: float) -> bool:
        """按数学坐标点一下图形区。"""
        st = self.state() or {}
        g = st.get("graph") or {}
        try:
            x0, x1 = float(g["x0"]), float(g["x1"])
            y0, y1 = float(g["y0"]), float(g["y1"])
            xmin, xmax = float(g["xmin"]), float(g["xmax"])
            ymin, ymax = float(g["ymin"]), float(g["ymax"])
        except Exception:
            return False
        px = x0 + (float(x) - xmin) / (xmax - xmin) * (x1 - x0)
        py = y1 - (float(y) - ymin) / (ymax - ymin) * (y1 - y0)
        self.click_graph_at(px, py)
        return True

    # ---- 写
    def _click_rid(self, rid: str, expect_checked: bool = True) -> str:
        """点一个选项，并确认 checked 状态真的变成了期望值。"""
        rid_js = json.dumps(rid)
        for expr in ("document.getElementById(%s)" % rid_js,
                     "(document.getElementById(%s) || {}).parentElement" % rid_js,
                     "document.querySelector('label[for=' + %s + ']')" % rid_js):
            self.js(_CLICK_JS % ("(%s) || null" % expr))
            time.sleep(0.25)
            st2 = self.state()
            hit = [r for r in (st2.get("radios", []) + st2.get("checks", []))
                   if r["id"] == rid]
            if hit and bool(hit[0].get("checked")) == expect_checked:
                return "ok"
        return "not-checked"

    def pick_choice(self, value: str, multi: bool = False) -> str:
        """按模型答案选一个选项。

        ``value`` 可以是 ``B``、``B. 90%``、``Option B: 90%``，也可以是完整选项
        文本。匹配不到或存在歧义时直接返回错误，不按位置瞎点——这是从
        Auto-Pearson 的 choiceIndex 学来的关键保护。
        """
        value = (value or "").strip()
        if not value:
            return "no-letter"
        st = self.state()
        radios = st.get("radios", [])
        checks = st.get("checks", [])
        # 多选优先用复选框池；单选优先用单选框池，避免混在一起按位置点错
        pool = (checks or radios) if multi else (radios or checks)
        if not pool:
            return "no-match"
        labels = [str(r.get("label") or "") for r in pool]
        m = match_choice(value, labels)
        if not m.ok:
            return "ambiguous" if m.ambiguous else "no-match"
        target = pool[int(m.index)]
        if target.get("disabled"):
            return "disabled"
        if target.get("checked"):
            return "ok"
        return self._click_rid(target["id"], True)

    def pick_multi(self, letters: list[str]) -> str:
        """多选：先清掉旧勾选，再逐个点，全中才算 ok。"""
        st = self.state()
        for box in st.get("checks", []):
            if box.get("checked"):
                self._click_rid(box["id"], False)
                time.sleep(0.15)
        bad = []
        for ch in letters:
            if self.pick_choice(ch, multi=True) != "ok":
                bad.append(ch)
            time.sleep(0.25)
        return "ok" if not bad else "fail:" + ",".join(bad)

    def leave_state(self) -> dict:
        """精确识别 Pearson 的两类“离开未完成题”警告。

        返回 ``kind``：``unchecked``（答案还没检查）/ ``incomplete``（小题没做完）
        / ``leave``（其它离开确认）/ 空字符串。默认调用方应点 No；只有已经把
        跳过写入 skip ledger 才允许 Yes。
        """
        out = {"visible": False, "kind": "", "dialog_id": "", "text": "",
               "yes_count": 0, "no_count": 0, "yes_id": "", "no_id": ""}
        try:
            cs = self.completion_state()
        except Exception:
            return out
        if str(cs.get("kind") or "") != "leave":
            return out
        text = str(cs.get("text") or "")
        low = text.lower()
        if ("without checking" in low or "will not receive any credit" in low
                or "answer has not been checked" in low):
            kind = "unchecked"
        elif ("not completed this question" in low
              or "credit only for the work you" in low):
            kind = "incomplete"
        else:
            kind = "leave"
        yes = [b for b in cs.get("buttons", [])
               if re.fullmatch(r"yes", str(b.get("text") or "").strip(), re.I)]
        no = [b for b in cs.get("buttons", [])
              if re.fullmatch(r"no", str(b.get("text") or "").strip(), re.I)]
        out.update({"visible": True, "kind": kind,
                    "dialog_id": str(cs.get("dialogId") or ""), "text": text,
                    "yes_count": len(yes), "no_count": len(no),
                    "yes_id": str(yes[0].get("id") or "") if len(yes) == 1 else "",
                    "no_id": str(no[0].get("id") or "") if len(no) == 1 else ""})
        return out

    def click_leave(self, choice: str = "no") -> str:
        """点离开警告内部的 Yes/No，且必须唯一。

        绝不在页面上按文字乱点：只在当前可见的 leave dialog 内部找按钮。
        """
        want = "yes" if str(choice).lower().startswith("y") else "no"
        js = r"""
(() => {
  const want = %s;
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2; };
  const clean = (s) => (s || '').replace(/\u200b/g, '').replace(/\s+/g, ' ').trim();
  const leaveRe = /(leave this question|not completed this question|continue without checking|are you sure you want to (leave|continue))/i;
  const dlgs = [...document.querySelectorAll(
      '[role=dialog], [id*=Dialog], [class*=Dialog], [id*=Popup], [class*=Popup]')]
    .filter(vis)
    .map((el) => ({el, text: clean(el.innerText)}))
    .filter((c) => leaveRe.test(c.text))
    .sort((a, b) => a.text.length - b.text.length);
  if (!dlgs.length) return 'none';
  const d = dlgs[0].el;
  const btns = [...d.querySelectorAll('button, a, [role=button]')].filter(vis)
    .map((b) => ({b, text: clean(b.innerText || b.getAttribute('aria-label') || b.getAttribute('title'))}));
  const hit = btns.filter((x) => clean(x.text).toLowerCase() === want);
  if (hit.length !== 1) return hit.length ? 'ambiguous' : 'no-button';
  hit[0].b.click();
  return 'ok';
})()""" % json.dumps(want)
        try:
            return str(self.js(js))
        except Exception:
            return "error"

    def leave_prompt(self) -> bool:
        """有没有「Are you sure you want to leave this question?」这种确认框。"""
        try:
            if self.leave_state().get("visible"):
                return True
        except Exception:
            pass
        js = r"""
(() => {
  const t = (document.body.innerText || '');
  return /Are you sure you want to leave this question|You have not completed this question/i.test(t);
})()
"""
        try:
            return bool(self.js(js))
        except Exception:
            return False

    def feedback_text(self) -> str:
        """判分弹窗里的提示文字（Try again 后面那段）。"""
        st = self.completion_state()
        if st.get("text"):
            return str(st["text"])[:300]
        js = r"""
(() => {
  const e = document.querySelector('[id*=FeedbackMessage]');
  return e ? (e.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 300) : '';
})()
"""
        try:
            return str(self.js(js) or "")
        except Exception:
            return ""

    def dialog_next(self) -> bool:
        """判分弹窗里有没有「Next question」按钮（多小问的题只有 OK）。"""
        return bool(self.completion_state().get("hasNext"))

    def select_option(self, select_id: str, text: str) -> str:
        """原生下拉框：按选项文字选中。"""
        sid = json.dumps(select_id)
        want = json.dumps(text or "")
        js = ("(() => { const s = document.getElementById(%s); if (!s) return 'no';"
              " const norm = (x) => (x || '').replace(/\\s+/g, '').toLowerCase();"
              " const w = norm(%s);"
              " let best = -1;"
              " for (let i = 0; i < s.options.length; i++) {"
              "   const t = norm(s.options[i].text);"
              "   if (t === w) { best = i; break; }"
              "   if (best < 0 && t && w && (t.includes(w) || w.includes(t))) best = i;"
              " }"
              " if (best < 0) return 'no-match';"
              " s.selectedIndex = best;"
              " s.dispatchEvent(new Event('input', { bubbles: true }));"
              " s.dispatchEvent(new Event('change', { bubbles: true }));"
              " return 'ok'; })()") % (sid, want)
        return self.js(js)

    def focus_field(self, field_id: str) -> str:
        expr = "document.getElementById(%s)" % json.dumps(field_id)
        # 先滚到视野中间，否则点击坐标可能落在视口外，编辑器拿不到焦点
        self.js("(() => { const s = %s; if (s) s.scrollIntoView({block: 'center', inline: 'nearest'}); })()" % expr)
        time.sleep(0.35)
        rect = self.js(
            "(() => { const s = %s; if (!s) return null;"
            " const r = s.getBoundingClientRect();"
            " return {x: r.x + r.width / 2, y: r.y + r.height / 2}; })()" % expr)
        if rect:
            # 真实鼠标事件更可靠（dijit 编辑器对合成事件有时不理）
            for typ in ("mousePressed", "mouseReleased"):
                self.ws.call("Input.dispatchMouseEvent", {
                    "type": typ, "x": rect["x"], "y": rect["y"],
                    "button": "left", "clickCount": 1,
                })
                time.sleep(0.05)
        self.js("(() => { const s = %s; if (!s) return false;"
                " const i = s.querySelector('input.focusNode') || s;"
                " try { i.focus(); } catch (e) {} return true; })()" % expr)
        time.sleep(0.2)
        return "ok"

    def clear_field(self) -> None:
        self.key("a", "KeyA", 65, 2)
        self.key("Delete", "Delete", 46)

    def _button_expr(self, pattern: str) -> str:
        """生成按钮查找表达式。Save 类按钮只允许点弹窗/图形框里的，绝不点页面顶部 Save。"""
        reg = "new RegExp(%s, 'i')" % json.dumps(pattern)
        save_guard = "true" if "save" in (pattern or "").lower() else "false"
        return ("(() => { const bs = [...document.querySelectorAll('button, a, [role=button]')]"
                ".filter((b) => { const r = b.getBoundingClientRect();"
                " if (!(r.width > 2 && r.height > 2)) return false;"
                " if (b.disabled || b.getAttribute('aria-disabled') === 'true') return false;"
                " if (" + save_guard + " && !b.closest("
                "'[id*=Popup], [id*=Dialog], [class*=Dialog], [role=dialog]')) return false;"
                " return [b.innerText, b.getAttribute('aria-label'), b.getAttribute('title')]"
                ".some((x) => x && " + reg + ".test(x.trim())); });"
                " const d = bs.filter((b) => b.closest("
                "'[id*=Dialog], [class*=Dialog], [class*=feedback], [role=dialog]'));"
                " return (d.length ? d : bs).pop() || null; })()")

    def click_text(self, pattern: str) -> str:
        """按文字 / aria-label / title 点按钮；有弹窗时优先点弹窗里的。"""
        return self.js(_CLICK_JS % ("(%s)" % self._button_expr(pattern)))

    def click_text_native(self, pattern: str) -> str:
        """在隔离世界原生点击按钮；Save 类按钮同样只允许弹窗内。"""
        expr = ("(() => { const b = %s; if (!b) return 'blocked-or-missing';"
                " b.click(); return 'ok'; })()" % self._button_expr(pattern))
        try:
            return self.js(expr) or "no"
        except Exception:
            return "no"

    # ---- 公式调色板（结构模板：矩阵 / 向量 / 分段…）
    def palette_click(self, field_id: str = "", classes: tuple[str, ...] = (),
                      title_re: str = "", allow_more: bool = True) -> str:
        """在指定输入框的公式调色板里点一个结构按钮。

        结构模板通常在「More」第二页（默认 hidden），直接找可见按钮会漏，
        所以找不到时先点 More 展开，再找一次。返回 ok / no-palette /
        no-tool / more-opened / err:…。
        """
        expr = _PALETTE_CLICK_JS % (
            json.dumps(field_id or ""),
            json.dumps(list(classes)),
            json.dumps(title_re or ""),
            "true" if allow_more else "false",
        )
        try:
            res = str(self.js(expr) or "no")
        except Exception as e:
            return f"err:{e}"
        if res in ("more-opened", "less-opened"):
            time.sleep(0.35)
            return self.palette_click(field_id, classes, title_re, allow_more=False)
        return res

    def close_palette(self) -> None:
        """关掉当前公式调色板，别让它的浮层挡住下一个输入框的真实点击。"""
        js = r"""(() => {
  const vis = (e) => { if (!e) return false; const r = e.getBoundingClientRect();
                       return r.width > 2 && r.height > 2; };
  const pals = [...document.querySelectorAll('div.xlInlineMathPalette')].filter(vis);
  for (const p of pals) {
    const x = p.querySelector('[data-dojo-attach-point="closeButtonNode"]');
    if (x) { try { x.click(); } catch (e) {} }
  }
  return 'ok';
})()"""
        try:
            self.js(js)
        except Exception:
            pass

    # ---- 矩阵
    def click_matrix(self, field_id: str = "") -> str:
        """点开矩阵结构模板：先在当前输入框的调色板里找（必要时展开 More）。"""
        res = self.palette_click(field_id, ("iconMatrix",), r"matrix|矩阵")
        if res == "ok":
            return "ok"
        # 兼容旧页面：矩阵按钮直接在第一行
        expr = ("[...document.querySelectorAll('button.iconMatrix')]"
                ".filter((x) => x.getBoundingClientRect().width > 0)"
                ".sort((a, b) => (b.closest('[id*=ResizableDialog]') ? 1 : 0)"
                " - (a.closest('[id*=ResizableDialog]') ? 1 : 0))[0]")
        fallback = self.js(_CLICK_JS % (f"({expr}) || null"))
        return fallback if fallback == "ok" else res

    def matrix_popup(self):
        """矩阵尺寸弹窗。不同 Pearson 版本 id 不一样，按“两个数字输入 + OK”兜底。"""
        return self.js(r"""
(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2; };
  const hasOk = (p) => [...p.querySelectorAll('button')]
      .some((b) => /^ok$/i.test((b.innerText || '').trim()));
  let pops = [...document.querySelectorAll(
      '[id*=MatrixSizePopup], [id*=MatrixPopup], [id*=MatrixDialog]')].filter(vis);
  if (!pops.length) {
    pops = [...document.querySelectorAll(
        '[role=dialog], [id*=Popup], [id*=Dialog], [class*=Popup], [class*=Dialog]')]
      .filter((p) => vis(p) && p.querySelectorAll('input').length >= 2 && hasOk(p));
  }
  if (!pops.length) return null;
  const pop = pops[pops.length - 1];
  let inputs = [...pop.querySelectorAll('input')];
  const spins = inputs.filter((i) => /spinner/i.test((i.id || '') + ' ' + (i.className || '')));
  if (spins.length >= 2) inputs = spins;
  const ok = [...pop.querySelectorAll('button')]
      .find((b) => /^ok$/i.test((b.innerText || '').trim()));
  return { id: pop.id || '', spins: inputs.slice(0, 2).map((s) => s.id),
           ok: ok ? (ok.id || '') : '', has_ok: !!ok,
           rows: inputs[0] ? inputs[0].value : '', cols: inputs[1] ? inputs[1].value : '' };
})()
""")

    def _click_matrix_ok(self) -> str:
        """没有 id 时，在矩阵弹窗内部按文字点 OK（别点到页面其它 OK）。"""
        js = r"""(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2; };
  const hasOk = (p) => [...p.querySelectorAll('button')]
      .some((b) => /^ok$/i.test((b.innerText || '').trim()));
  let pops = [...document.querySelectorAll(
      '[id*=MatrixSizePopup], [id*=MatrixPopup], [id*=MatrixDialog]')].filter(vis);
  if (!pops.length) {
    pops = [...document.querySelectorAll(
        '[role=dialog], [id*=Popup], [id*=Dialog], [class*=Popup], [class*=Dialog]')]
      .filter((p) => vis(p) && p.querySelectorAll('input').length >= 2 && hasOk(p));
  }
  if (!pops.length) return 'no';
  const ok = [...pops[pops.length - 1].querySelectorAll('button')]
    .find((b) => /^ok$/i.test((b.innerText || '').trim()));
  if (!ok) return 'no-ok';
  ok.click();
  return 'ok';
})()"""
        try:
            return str(self.js(js) or "no")
        except Exception:
            return "no"

    def set_spinner(self, spinner_id: str, value: int) -> bool:
        sid = json.dumps(spinner_id)
        target = int(value)
        get = ("(() => { const i = document.getElementById(%s); if (!i) return '-';"
               " return i.value + '/' + i.getAttribute('aria-valuenow'); })()" % sid)

        def cur():
            try:
                v = str(self.js(get)).split("/")
                return int(v[0]), int(v[-1])
            except Exception:
                return -1, -1

        for _ in range(16):
            val, now = cur()
            if now == target and val == target:
                return True
            if now < 0:
                return False
            which = "Up" if target > now else "Down"
            self.js("(() => { const i = document.getElementById(%s); if (!i) return 'no';"
                    " const w = i.closest('[id^=widget_]') || i.parentElement.parentElement;"
                    " const a = w.querySelector('.dijit%sArrowButton'); if (!a) return 'noarrow';"
                    " const r = a.getBoundingClientRect();"
                    " const o = {bubbles:true, cancelable:true, clientX:r.x+r.width/2,"
                    " clientY:r.y+r.height/2, button:0};"
                    " for (const t of ['pointerdown','mousedown','pointerup','mouseup','click'])"
                    " a.dispatchEvent(new MouseEvent(t, o));"
                    " return i.value; })()" % (sid, which))
            time.sleep(0.18)
        val, now = cur()
        return now == target and val == target

    def cell_ids(self, field_id: str) -> int:
        return self.js("[...document.querySelectorAll('#%s table.eqMatrix td')].length" % field_id) or 0

    def _set_input_value(self, input_id: str, value: int) -> bool:
        """兜底：直接改输入框的值并派发 input/change，兼容不同版本的 spinner。"""
        if not input_id:
            return False
        try:
            got = self.js(
                "(() => { const i = document.getElementById(%s); if (!i) return null;"
                " i.value = %s; i.setAttribute('aria-valuenow', %s);"
                " i.dispatchEvent(new Event('input', {bubbles:true}));"
                " i.dispatchEvent(new Event('change', {bubbles:true}));"
                " return i.value; })()"
                % (json.dumps(input_id), json.dumps(str(int(value))),
                   json.dumps(str(int(value)))))
            return str(got) == str(int(value))
        except Exception:
            return False

    def fill_matrix(self, field_id: str, rows: int, cols: int, values: list[str]) -> str:
        st = self.matrix_popup()
        clicked = ""
        if not st:
            clicked = self.click_matrix(field_id)
            for _ in range(10):
                time.sleep(0.4)
                st = self.matrix_popup()
                if st:
                    break
        if not st:
            return f"矩阵面板没弹出来（{clicked or 'no-tool'}）"
        if st.get("spins"):
            if not self.set_spinner(st["spins"][0], rows) \
                    and not self._set_input_value(st["spins"][0], rows):
                return f"行数没设成 {rows}"
            if len(st["spins"]) > 1 and not self.set_spinner(st["spins"][1], cols) \
                    and not self._set_input_value(st["spins"][1], cols):
                return f"列数没设成 {cols}"
        st = self.matrix_popup()
        if st:
            if st.get("ok"):
                self.js(_CLICK_JS % ("document.getElementById(%s) || null"
                                     % json.dumps(st["ok"])))
            elif st.get("has_ok"):
                self._click_matrix_ok()
        time.sleep(1.4)
        n = self.cell_ids(field_id)
        if n != rows * cols:
            self.focus_field(field_id)
            self.clear_field()
            time.sleep(0.5)
            return f"矩阵尺寸没设成（要 {rows}×{cols}，插出来是 {n} 格）"
        # 矩阵结构已经插进去了，把调色板收起来：它的浮层会挡住后面的输入框
        self.close_palette()

        click_cell = r"""
(() => {
  const cell = document.querySelectorAll('#%s table.eqMatrix td')[%d];
  if (!cell) return 'no';
  const row = cell.querySelector('span.eqRow') || cell;
  const r = row.getBoundingClientRect();
  const o = {bubbles:true, cancelable:true, clientX:r.x + 4, clientY:r.y + r.height / 2, button:0};
  for (const t of ['pointerdown','mousedown','pointerup','mouseup','click'])
    row.dispatchEvent(new MouseEvent(t, o));
  const fn = document.querySelector('#%s input.focusNode');
  if (fn) fn.focus();
  return 'ok';
})()
"""
        total = rows * cols
        for i, v in enumerate(values[:total]):
            time.sleep(1.2)
            self.js(click_cell % (field_id, i, field_id))
            time.sleep(0.2)
            self.insert_math(v)
            time.sleep(1.0)
        label = self.js("(document.querySelector('#%s .eqAccessibleLabel') || {}).textContent || ''"
                        % field_id) or ""
        if label.count("nothing"):
            return "矩阵没填全"
        return ""

    def capture_clip(self, x: float, y: float, w: float, h: float) -> bytes:
        """截取页面上一块区域（CSS 像素，页面坐标），返回 PNG 字节。"""
        r = self.ws.call("Page.captureScreenshot", {
            "format": "png",
            "clip": {"x": x, "y": y, "width": w, "height": h, "scale": 1},
            "captureBeyondViewport": True,
        })
        return base64.b64decode(r["data"])

    def _type_chars(self, text: str) -> None:
        for ch in text:
            self.ws.call("Input.dispatchKeyEvent", {"type": "char", "text": ch})
            time.sleep(0.03)

    def _arrow_right(self) -> None:
        for kind in ("rawKeyDown", "keyUp"):
            self.ws.call("Input.dispatchKeyEvent", {
                "type": kind, "key": "ArrowRight", "code": "ArrowRight",
                "windowsVirtualKeyCode": 39, "nativeVirtualKeyCode": 39,
            })

    def _char(self, ch: str) -> None:
        self.ws.call("Input.dispatchKeyEvent", {"type": "char", "text": ch})
        time.sleep(0.03)

    def _type_term(self, text: str, i: int) -> int:
        """输入一个「项」：数字/字母/括号组，内部递归处理 ^ 和 /。返回结束位置。"""
        n = len(text)
        if i < n and text[i] == "(":
            self._char("(")
            i += 1
            while i < n and text[i] != ")":
                if text[i] in "^/":
                    self._char(text[i])
                    i += 1
                    i = self._type_term(text, i)
                    self._arrow_right()
                else:
                    self._char(text[i])
                    i += 1
            if i < n and text[i] == ")":
                self._char(")")
                i += 1
            return i
        while i < n and text[i] not in "+-*=)":
            if text[i] == "^":
                self._char("^")
                i += 1
                i = self._type_term(text, i)
                self._arrow_right()
            else:
                self._char(text[i])
                i += 1
        return i

    def dropdown_open(self, fid: str) -> bool:
        js = ("(() => { const el = document.getElementById(%s); if (!el) return false;"
              " const r = el.getBoundingClientRect();"
              " const o = {bubbles:true, cancelable:true, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0};"
              " for (const t of ['pointerdown','mousedown','pointerup','mouseup','click'])"
              " el.dispatchEvent(new MouseEvent(t, o)); return true; })()") % json.dumps(fid)
        try:
            self.js(js)
        except Exception:
            return False
        time.sleep(0.5)
        return True

    def dropdown_options(self) -> list[str]:
        js = r"""
(() => {
  const menus = [...document.querySelectorAll('.dijitMenu')]
    .filter((e) => e.getBoundingClientRect().width > 2);
  if (!menus.length) return [];
  const menu = menus[menus.length - 1];
  return [...menu.querySelectorAll('tr.dijitMenuItem')]
    .map((tr) => (tr.innerText || '').replace(/\s+/g, ' ').trim())
    .filter(Boolean);
})()
"""
        try:
            return [str(x) for x in (self.js(js) or [])]
        except Exception:
            return []

    def dropdown_pick(self, idx: int) -> str:
        js = ("""(() => {
  const menus = [...document.querySelectorAll('.dijitMenu')]
    .filter((e) => e.getBoundingClientRect().width > 2);
  if (!menus.length) return 'no-menu';
  const menu = menus[menus.length - 1];
  const items = [...menu.querySelectorAll('tr.dijitMenuItem')]
    .filter((tr) => (tr.innerText || '').trim());
  const tr = items[%d];
  if (!tr) return 'no-item';
  const r = tr.getBoundingClientRect();
  const o = {bubbles:true, cancelable:true, clientX:r.x+r.width/2, clientY:r.y+r.height/2, button:0};
  for (const t of ['pointerdown','mousedown','pointerup','mouseup','click'])
    tr.dispatchEvent(new MouseEvent(t, o));
  return 'ok';
})()""") % idx
        try:
            return str(self.js(js))
        except Exception as e:
            return "err:" + str(e)

    def dropdown_close(self) -> None:
        try:
            self.key("Escape", "Escape", 27)
        except Exception:
            pass
        time.sleep(0.2)

    def paste_math(self, text: str) -> bool:
        """把表达式写进剪贴板再 Ctrl+V 粘进编辑器（Pearson 会自己解析成分数/上标）。"""
        from . import clipboard

        old = ""
        try:
            old = clipboard.get_text()
        except Exception:
            old = ""
        if not clipboard.copy_text(text):
            return False
        try:
            self.key('a', 'KeyA', 65, 2)
            time.sleep(0.08)
            self.key('v', 'KeyV', 86, 2)
            time.sleep(0.45)
        finally:
            if old:
                try:
                    clipboard.copy_text(old)
                except Exception:
                    pass
        return True

    def insert_math(self, text: str) -> None:
        """输入数学表达式。

        Pearson 编辑器里 "^" 进入上标、"/" 进入分母，都不会自动退出；
        退出后 insertText 还会被忽略，所以全程逐字符 + ArrowRight。
        """
        text = (text or "").strip()
        i, n = 0, len(text)
        while i < n:
            ch = text[i]
            if ch in "^/":
                self._char(ch)
                i += 1
                i = self._type_term(text, i)
                time.sleep(0.1)
                self._arrow_right()
                time.sleep(0.15)
            else:
                self._char(ch)
                i += 1

    def field_text(self, field_id: str) -> str:
        """读编辑器的真实内容（含 eqAccessibleLabel），比 state 里的 label 更新鲜。"""
        js = ("(() => { const e = document.getElementById(%s); if (!e) return '';"
              " const lab = e.querySelector('.eqAccessibleLabel');"
              " const t = (e.innerText || '').replace(/\\s+/g, ' ').trim();"
              " const a = lab ? (lab.textContent || '').trim() : '';"
              " return (t + ' ' + a).trim(); })()") % json.dumps(field_id)
        try:
            return str(self.js(js) or "")
        except Exception:
            return ""

    def field_label(self, field_id: str) -> str:
        return self.js("(document.getElementById(%s) || {}).getAttribute && "
                       "document.getElementById(%s).getAttribute('aria-label') || ''"
                       % (json.dumps(field_id), json.dumps(field_id))) or ""

