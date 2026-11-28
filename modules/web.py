"""网页模式（退治）：顺着结界（Chrome DevTools Protocol）直连浏览器，读符卡、落笔、交卡。

紫的结界原理：
1. 先张开结界：用 --remote-debugging-port 起一个独立的答题浏览器窗口；
2. 顺着缝隙摸进去：访问 http://127.0.0.1:<port>/json/list 拿到页面，连上 WebSocket；
3. 在符卡所在的 frame 里另开一个隔离世界（隔离执行环境），用 JS 读题干 / 单选框 / 输入框；
4. 把符卡交给式神（模型），要它回 CHOICE / MATRIX / VALUE 三行；
5. 落笔：合成鼠标事件点选项、点输入框，Input.insertText 填值；矩阵先开弹窗定尺寸再逐格落笔；
6. 点 Check answer 看判分，答对就点 Next，答错/异常就收手等人工。

结界内的所有状态（隔离世界、主世界上下文）都属于「境界的缝隙」：缝隙一旦换掉，
旧上下文就作废，必须重新摸一遍，别拿旧符卡去填新题。
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
    """列出结界里能用的页面（只挑真正的网页标签页）。"""
    url = f"http://127.0.0.1:{port}/json/list"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        raise CDPError(
            f"结界还没张开：连不上调试端口 {port}"
            "（先用『启动答题浏览器.bat』张开结界）") from e
    return [p for p in data if p.get("type") == "page" and p.get("webSocketDebuggerUrl")]


class CDP:
    """够用就行的 WebSocket 客户端（只为本机调试端口写）。

    紫的结界专用：单连接、同步等回音，不做并发。任何读写失败都把连接标成
    ``dead``，让上层（WebPlayer）知道「这条缝隙已经废了，该重新摸一条」。
    """

    def __init__(self, url: str, timeout: float = 20.0) -> None:
        self.sock = None
        self.dead = False
        self.buf = b""
        self.mid = 0
        self.timeout = timeout
        self.events: list[dict] = []
        # 执行上下文单独存一份：普通事件列表会被截断到 500 条，
        # 上下文事件一旦被挤掉，主世界就永远摸不回来了（见 main_context_id）。
        self.contexts: dict[int, dict] = {}
        u = urllib.parse.urlsplit(url)
        try:
            self.sock = socket.create_connection((u.hostname, u.port), timeout=timeout)
            key = base64.b64encode(os.urandom(16)).decode()
            req = (
                f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            )
            self.sock.sendall(req.encode())
            buf = b""
            deadline = time.time() + timeout
            while b"\r\n\r\n" not in buf:
                if time.time() > deadline:
                    raise CDPError("结界迟迟没有回音（WebSocket 握手超时）")
                try:
                    chunk = self.sock.recv(4096)
                except socket.timeout as e:
                    raise CDPError("结界迟迟没有回音（WebSocket 握手超时）") from e
                if not chunk:
                    raise CDPError("结界握手失败（WebSocket 连接被对方关掉）")
                buf += chunk
            if b" 101 " not in buf.split(b"\r\n", 1)[0]:
                raise CDPError("结界拒绝了牵手（调试端口拒绝 WebSocket 升级）")
            self.buf = buf.split(b"\r\n\r\n", 1)[1]
        except OSError as e:
            # 握手没成就把 socket 收掉，别让半开的连接留在境界里漏灵力。
            self._drop_socket()
            raise CDPError(f"结界还没张开：连不上调试端口（{e}）") from e
        except Exception:
            self._drop_socket()
            raise

    def _drop_socket(self) -> None:
        """收掉半开的 socket（握手失败/主动关闭时用）。"""
        self.dead = True
        try:
            if self.sock is not None:
                self.sock.close()
        except Exception:
            pass
        self.sock = None

    def _ensure(self, n: int, deadline: float | None = None) -> None:
        """把 self.buf 填到至少 n 字节。

        只追加、**不消费**：这样就算中途超时，缓冲也不会错位（旧实现先吃掉
        2 字节帧头再等正文，一超时整条流就永久错位）。给 deadline 时，
        每次 recv 的 socket 超时也会跟着收紧，`call(timeout=)` 才真的生效。
        """
        while len(self.buf) < n:
            if deadline is not None:
                remain = deadline - time.time()
                if remain <= 0:
                    raise CDPError("结界迟迟没有回音（调试端口响应超时）")
                try:
                    self.sock.settimeout(max(0.05, min(remain, self.timeout)))
                except OSError:
                    pass
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout as e:
                raise CDPError("结界迟迟没有回音（调试端口响应超时）") from e
            except OSError as e:
                self.dead = True
                raise CDPError(f"结界断了（{e}）") from e
            if not chunk:
                self.dead = True
                raise CDPError("结界断了（调试端口关闭了连接）")
            self.buf += chunk

    def _frame(self, deadline: float | None = None):
        """取一整帧；先收齐整帧再推进 self.buf。"""
        self._ensure(2, deadline)
        op = self.buf[0] & 0x0F
        masked = self.buf[1] & 0x80
        ln = self.buf[1] & 0x7F
        pos = 2
        if ln == 126:
            self._ensure(4, deadline)
            ln = struct.unpack(">H", self.buf[2:4])[0]
            pos = 4
        elif ln == 127:
            self._ensure(10, deadline)
            ln = struct.unpack(">Q", self.buf[2:10])[0]
            pos = 10
        mask_len = 4 if masked else 0
        need = pos + mask_len + ln
        self._ensure(need, deadline)
        mask = self.buf[pos:pos + 4] if masked else b"\0\0\0\0"
        start = pos + mask_len
        data = self.buf[start:need]
        if masked:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.buf = self.buf[need:]
        return op, data

    def _pong(self, data: bytes) -> None:
        """回一个 pong 帧（Chrome 偶尔 ping 一下，不回会被当成掉线）。"""
        try:
            mask = os.urandom(4)
            n = len(data)
            if n < 126:
                head = bytes([0x8A, 0x80 | n])
            elif n < 65536:
                head = bytes([0x8A, 0x80 | 126]) + struct.pack(">H", n)
            else:
                head = bytes([0x8A, 0x80 | 127]) + struct.pack(">Q", n)
            self.sock.sendall(
                head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
        except Exception:
            pass

    def _send(self, obj: dict) -> None:
        if self.dead or self.sock is None:
            raise CDPError("结界已经断了（CDP 连接不可用）")
        data = json.dumps(obj).encode("utf-8")
        mask = os.urandom(4)
        n = len(data)
        if n < 126:
            head = bytes([0x81, 0x80 | n])
        elif n < 65536:
            head = bytes([0x81, 0x80 | 126]) + struct.pack(">H", n)
        else:
            head = bytes([0x81, 0x80 | 127]) + struct.pack(">Q", n)
        try:
            self.sock.sendall(
                head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))
        except OSError as e:
            self.dead = True
            raise CDPError(f"结界断了（{e}）") from e

    def _remember(self, msg: dict) -> None:
        """收下服务端推来的事件；上下文事件另存一份，绝不被截断。"""
        m = msg.get("method") or ""
        if m == "Runtime.executionContextCreated":
            ctx = (msg.get("params") or {}).get("context") or {}
            cid = ctx.get("id")
            if isinstance(cid, int):
                self.contexts[cid] = ctx
        elif m == "Runtime.executionContextDestroyed":
            cid = (msg.get("params") or {}).get("executionContextId")
            if isinstance(cid, int):
                self.contexts.pop(cid, None)
        elif m == "Runtime.executionContextsCleared":
            self.contexts.clear()
        self.events.append(msg)
        if len(self.events) > 800:
            self.events = self.events[-500:]

    def call(self, method: str, params: dict | None = None, timeout: float | None = None):
        self.mid += 1
        mid = self.mid
        self._send({"id": mid, "method": method, "params": params or {}})
        deadline = time.time() + (timeout or self.timeout)
        while time.time() < deadline:
            op, data = self._frame(deadline)
            if op == 9:  # ping
                self._pong(data)
                continue
            if op == 8:  # close
                self.dead = True
                raise CDPError("结界那头把连接关上了（调试端口 close）")
            if op != 1:
                continue
            try:
                msg = json.loads(data.decode("utf-8", "replace"))
            except Exception:
                continue
            if msg.get("id") == mid:
                if "error" in msg:
                    # 原始错误文本必须保留：上层靠里面的 "context" 判断要不要重建上下文。
                    raise CDPError("结界拒绝了这次求值（" + str(msg["error"])[:160] + "）")
                return msg.get("result", {})
            if "method" in msg:
                self._remember(msg)
        raise CDPError(f"结界迟迟没有回音（{method} 超时）")

    def close(self) -> None:
        self._drop_socket()


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
    // 2026-11-28 实测：Pearson 有些题是**左右分栏**（左边题干 contentHolderleft、
    // 右边答题框 contentHolderright）。旧代码直接取「第一个 .contentHolder」，
    // 正好拿到左边那个 —— 里面一个答题控件都没有，于是 fields=0、inventory=0，
    // 程序就以为「这页没事可做」，一直空转「等题目出现…」。
    // 《作业侠客》的取法是 `dlg || document.body`（整页），不会有这个问题。
    // 这里保持「优先用带控件的那个 holder，实在没有就整页」。
    const holders = [...document.querySelectorAll('.contentPanel .contentHolder')];
    contentRoot = holders.find((h) => h.querySelector(
                    'span.eqEditor, input[type=radio], input[type=checkbox], ' +
                    'input[type=text], input[type=number], select, .xlFillinItem'))
      || document.getElementById('contentHolderbottom')
      || document.getElementById('contentHoldertop')
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
    const lab = clean(el.getAttribute('aria-label'));
    // 已填 / 已判分的小节，label 里就是内容；占位符才表示「还空着」。
    // 帕秋莉：判过分的 Part 会留在页面上，再往里头写会把已经对的答案搅乱。
    const empty = !lab || /enter your response here|your response|nothing/i.test(lab);
    return {
      id: el.id, uid: uidOf(el), label: lab.slice(0, 120),
      readonly: /true/i.test(el.getAttribute('aria-readonly') || ''),
      disabled: off,
      filled: !empty,
      // Pearson 会在**没选中的选项**里也塞一个输入框（id 里带 Decoy），
      // 填了不计分。但注意：**选中的那个选项**里的空也可能叫 Decoy1，
      // 所以这里只标出来，真正判定要看 in_opt（见下）。
      decoy: /decoy/i.test(el.id || ''),
      // 这个空是不是在某个「选项」里、那个选项选中没有。
      // 只有「往上这几层里**正好只有一个**单选按钮」才算它在某个选项里；
      // 一旦某层祖先出现多个 radio（整个选项列表），说明它是题干正文里的空
      // （`The solution is x = ___`），**绝不能跳过**。
      in_opt: (() => {
        let box = el.parentElement;
        for (let i = 0; i < 6 && box; i++) {
          const rs = box.querySelectorAll('input[type=radio]');
          if (rs.length > 1) return '';
          if (rs.length === 1) return rs[0].checked ? 'checked' : 'unchecked';
          box = box.parentElement;
        }
        return '';
      })(),
      // 这个空自己的上下文：**上一节 + 本节 + 本行**。
      // 只取 parentElement 会丢掉指令；只取本节又会丢掉「上一节给定的数」
      // （长题里 h、k 这些常数常常写在前一节，模型拿不到就只能瞎凑）。
      hint: (() => {
        const own = clean((el.parentElement && el.parentElement.innerText) || '');
        const step = el.closest ? el.closest('.step') : null;
        if (!step) return own.slice(0, 160);
        const steps = [...scope.querySelectorAll('span.step, .step')].filter(vis);
        const i = steps.indexOf(step);
        const prev = i > 0 ? clean(steps[i - 1].innerText || '') : '';
        const s = clean(step.innerText || '');
        const head = (prev ? prev.slice(-120) + ' … ' : '') + s.slice(0, 220);
        return (head + ' … ' + own).slice(0, 420);
      })() };
  });
  const radiosAll = [...scope.querySelectorAll('input[type=radio]')].filter(vis).map((el) => {
    // 旧代码只对 parentElement.className 做 /Disabled/ 判断，大小写敏感：
    // Pearson 有的版本写的是 class="disabled"（全小写），于是被当成可点选项，
    // 点下去毫无反应，整题被误判「选项没点上」。这里统一成不区分大小写 + closest。
    const par = el.parentElement;
    const off = !!el.disabled
      || /disabled/i.test(par ? String(par.className || '') : '')
      || !!(el.closest && el.closest('.disabled, [aria-disabled="true"]'));
    // 选项自己的字母从 aria-label 开头取（`A. Odd` / `B) Even`），别用全局下标：
    // 一页上可能同时有「a 组的 A–D」和「d 组的 A–D」，全局下标会对不上。
    const mlab = clean(el.getAttribute('aria-label'));
    const mletter = mlab.match(/^\s*([A-H])[.)、]/);
    return {
      id: el.id, uid: uidOf(el), label: mlab.slice(0, 160),
      checked: !!el.checked, disabled: off,
      group: el.name || '',
      letter: mletter ? mletter[1] : '' };
  });
  // 只把「当前小问」的选项给模型/选择用；已答过的旧选项通常 disabled，会打乱字母对应
  const radios = radiosAll.filter((r) => !r.disabled);
  const radiosDisabled = radiosAll.length - radios.length;
  const inputs = [...scope.querySelectorAll('input[type=text], input[type=number], input[type=email]')]
      .filter(vis).filter((el) => !el.closest('span.eqEditor')).map((el) => ({
        id: el.id, uid: uidOf(el), label: clean(el.getAttribute('aria-label')).slice(0, 120),
        value: (el.value || '').slice(0, 200), disabled: !!el.disabled }));
  const checks = [...scope.querySelectorAll('input[type=checkbox]')].filter(vis).map((el) => {
    // dijit 复选框自己的 innerText 是空的，文字在 `label[for=id]` 里。
    // （灵梦：找人家的名字，得去门牌上找，别对着空壳子喊。）
    let clab = '';
    try {
      const lf = scope.querySelector('label[for="' + el.id + '"]');
      if (lf) clab = clean(lf.innerText);
    } catch (e) { clab = ''; }
    if (!clab) {
      const box = el.closest('label, .mcButtonArea, .mcAnswerContent, li, td');
      clab = clean((box && box.innerText) || '');
    }
    if (!clab) clab = clean(el.getAttribute('aria-label'));
    const cletter = clab.match(/^\s*([A-H])[.)、]/);
    return {
      id: el.id, uid: uidOf(el), label: clab.slice(0, 160),
      checked: !!el.checked, disabled: !!el.disabled,
      letter: cletter ? cletter[1] : '' };
  });
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

  // 题干：优先取上下分栏；Pearson 还有**左右分栏**：
  //   左 contentHolderleft  = 题目条件（例如 3^(-3)=1/27）
  //   右 contentHolderright = 作答区（log3 ___ = ___）
  // 旧代码只取 bottom/top，左右分栏时模型只看到右半句“log3 ___ = ___”，
  // 看不到要转换的等式，于是永远答不出（2026-11-28 实机复现）。
  const topEl = document.getElementById('contentHoldertop');
  const bottomEl = document.getElementById('contentHolderbottom');
  const leftEl = document.getElementById('contentHolderleft');
  const rightEl = document.getElementById('contentHolderright');
  let stem = topEl ? clean(topEl.innerText) : '';
  stem = stem.split('\n').filter((ln) => !/^(?:[-−–]?\d+(?:\.\d+)?\s+){6,}/.test(ln.trim())).join('\n');
  if (desc) stem = stem.split(desc).join(' ');
  stem = clean(stem).slice(0, 1200);

  // 左右分栏时按“左 → 右”拼；上下布局按“上 → 下”拼，保持原来的阅读顺序。
  const holderEls = [];
  for (const el of [leftEl, rightEl, topEl, bottomEl]) {
    if (el && !holderEls.includes(el)) holderEls.push(el);
  }
  if (!holderEls.length) holderEls.push(scope);
  let raw = clean(holderEls.map((e) => clean(e.innerText)).filter(Boolean).join('\n\n'));
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
  // 「交卷」按钮可能长得像 <a> 或 div[role=button]，只扫 <button> 会漏。
  // 灵梦：这页要是摆着「Submit / Done」这种封印，我就算看见了也不能碰。
  // 但**导航条里的 "Done" 链接不算**——那种误判会把整轮全自动停掉，比不检查还糟。
  const SEL_WIDE = 'button, a, [role=button], input[type=button], input[type=submit]';
  const hasDanger = (() => {
    const re = /^(submit|submit grade|submit assignment|submit for grading|done|finish|turn in|turn it in|提交)$/i;
    return [...document.querySelectorAll(SEL_WIDE)].some((b) => {
      if (!vis(b)) return false;
      if (b.disabled || b.getAttribute('aria-disabled') === 'true') return false;
      if (/disabled/i.test(String(b.className || ''))) return false;
      try {
        if (b.closest('nav, header, footer, [class*=nav], [class*=Nav], [class*=menu], [class*=Menu]'))
          return false;
      } catch (e) { /* 拿不到就当不在导航里 */ }
      return [b.innerText, b.value, b.getAttribute('aria-label'), b.getAttribute('title')]
        .some((x) => x && re.test(String(x).trim()));
    });
  })();
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
    id: el.id, uid: uidOf(el), label: clean(el.getAttribute('aria-label') || '').slice(0, 200),
    // 已经选过 / 这节判过分锁住的下拉不要再动：再点一次会把对的答案改掉。
    value: clean(el.innerText || '').replace(/[▼▾]/g, '').trim().slice(0, 40),
    locked: /true/i.test(el.getAttribute('aria-disabled') || '')
            || /answered|ReadOnly|Disabled/i.test(el.className || '') }));

  // 字段 inventory：页面渲染出来的答题控件数量，必须和快照实际捕获的数量一致。
  // 少一个就说明还有控件没被识别（例如 Q14 的诱饵框/自定义控件），此时绝不让
  // 模型盲答；宁可刷新/记录待人工，也不能漏字段提交。
  //
  // 注意：分子（capturedCount）来自 scope = dlg || contentRoot，分母也必须用 scope。
  // 旧代码分母写死 contentRoot —— 只要页面上有一个可见的 ResizableDialog
  // （判分/帮助/图形弹窗都算），captured 就变成 0、rendered 还是整题的控件数，
  // missing 必然 > 0，于是每一题都被当成「控件没认全」记待人工。
  const renderedEls = [...scope.querySelectorAll(
      'span.eqEditor, input[type=text], input[type=number], input[type=email], ' +
      'input[type=radio], input[type=checkbox], select, .xlFillinItem')]
    .filter(vis)
    .filter((el) => !(el.matches('input[type=text], input[type=number], input[type=email]')
                      && el.closest('span.eqEditor')))
    .filter((el) => !(el.matches('select') && el.closest('.xlFillinItem')));
  const capturedCount = fields.length + inputs.length + radiosAll.length
                      + checks.length + selects.length + dropdowns.length;
  const missingGroups = [...scope.querySelectorAll('.xlMultipleChoice')]
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
    inDialog: !!dlg,
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
  // Check 是否「可点」：灰着的说明还有空没填/没选，这时点它毫无反应，
  // 只会白等一轮判分超时。（帕秋莉：门锁着就别敲了，先看看缺哪把钥匙。）
  const hasCheckOn = checkCandidates.some((c) => c.enabled);
  // 当前这一节（`.step`）的正文：整页文本只留 4000 字，长题会把这一节截掉，
  // 式神于是照抄前面小问的答案。挑「含最后一个可见控件」的那一节。
  const cur = (() => {
    const els = [...scope.querySelectorAll('span.eqEditor, input[type=radio], .xlFillinItem')]
      .filter(vis);
    for (let i = els.length - 1; i >= 0; i--) {
      const s = els[i].closest ? els[i].closest('.step') : null;
      if (s) { const t = clean(s.innerText || ''); if (t) return t.slice(0, 1200); }
    }
    return '';
  })();
  return { text: text, qkey: qkey, rect: qrect, part: [partN, partM], fields: fields, radios: radios,
           dropdowns: dropdowns, questions: questions, qno: qno, graph: graph,
           radios_disabled: radiosDisabled, inputs: inputs,
           checks: checks, selects: selects, imgs: imgs,
           identity: identity, problemKey: problemKey, signature: signature,
           inventory: inventory, incomplete: incomplete,
           checkCandidates: checkCandidates,
           hasCheck: checkCandidates.length > 0 || btn(/^(check answer|final check)$/i),
           canCheck: checkUnique,
           hasCheckOn: hasCheckOn,
           cur: cur,
           hasDanger: hasDanger,
           hasNext: btn(/^(next|next question|continue|continue to next part|next part)$/i),
           inDialog: !!dlg };
})()
"""

_PALETTE_CLICK_JS = r"""
(() => {
  const vis = (e) => { if (!e) return false; const r = e.getBoundingClientRect();
                       const cs = getComputedStyle(e);
                       return r.width > 2 && r.height > 2
                         && cs.display !== 'none' && cs.visibility !== 'hidden'
                         && cs.opacity !== '0'; };
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
  const buttons = () => [...pal.querySelectorAll('button')].filter(vis)
    .filter((b) => !b.disabled && b.getAttribute('aria-disabled') !== 'true');
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
  // 部分正确：Pearson 的文案是 "Your answer is partially correct."，它同时命中 good
  // 里的 correct，所以必须在 good 之前单独判出来，否则 partial 会被当成满分答对。
  const partial = /\b(partially correct|partially right|partial credit)\b/i;
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
    if (partial.test(t)) return 'partial';
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
  const vis = (e) => {
    if (!e.getClientRects().length) return false;
    const s = getComputedStyle(e);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    if (parseFloat(s.opacity || '1') < 0.05) return false;
    const r = e.getBoundingClientRect();
    return r.width > 2 && r.height > 2;
  };
  const good = /\b(well done|fantastic|great|nice work|excellent|way to go|perfect|that'?s right|right answer|you got it|correct)\b/i;
  // 判错的文案：除了否定式，还要拦「**correct answer**」—— Pearson 判错时会写
  // 「The correct answer is …」，这句里就带着 correct，旧规则一路掉进 good 判成答对。
  const bad = /\b(incorrect|not\s+correct|isn'?t\s+correct|not\s+quite|try again|not\s+right|wrong|sorry|almost|check your work|partially\s+correct|correct\s+answer)\b/i;
  // 判分框一定带一颗按钮：老界面是 OK，真 Pearson 2026-11 的新界面只有
  // 「Next question」（class btnOnly）。题目正文里不会有这些按钮文字。
  const BTN = /^(ok|next|next question|try again|show answer|similar exercise|guided solution|display correct answer)$/i;
  const hasBtn = (d) => [...d.querySelectorAll('button')].filter(vis).some(
      (b) => BTN.test(((b.innerText || b.value || '') + '').trim()));
  const texts = (d) => [...d.querySelectorAll('button')].filter(vis)
      .map((b) => ((b.innerText || b.value || '') + '').trim());
  const cands = [...document.querySelectorAll(
      '.feedbackDialog, [class*=feedbackDialog], [id*=FeedbackMessage], [role=dialog], [class*=feedback]')]
      .filter(vis).filter(hasBtn);
  for (const d of cands.reverse()) {
    const t = (d.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 600);
    if (!t) continue;
    const bs = texts(d);
    // 把按钮文字从整段里剔掉，剩下的才是「判分文案」。只剩按钮名的框（空弹窗/残影）
    // 不能当成答对 —— 真判分框都有自己的一句话。
    let bare = t;
    for (const b of bs) if (b) bare = bare.split(b).join('');
    bare = bare.trim();
    // **结构优先于文案**：
    //   - 有「Try again / Show answer / Display correct answer」= 判错；
    //   - 文案里有 bad 里的词 = 判错；
    //   - 有自己的一句文案 + 「Next question」= 判对；
    //   - 老界面的 OK 按钮 + 没有否定词 = 判对。
    if (bs.some((b) => /^(try again|retry|show answer|display correct answer)$/i.test(b))) {
      window.__fb_text = t; return 'incorrect';
    }
    if (bad.test(t)) { window.__fb_text = t; return 'incorrect'; }
    if (bare && bs.some((b) => /^(next|next question|continue)$/i.test(b))) {
      window.__fb_text = t; return 'correct';
    }
    if (good.test(t) || bs.some((b) => /^ok$/i.test(b))) {
      window.__fb_text = t; return 'correct';
    }
    window.__fb_text = t;
  }
  return '';
})()
"""

# 取 Dojo registry 的共用逻辑：真实 Pearson 不保证有全局 dijit，通常只暴露 AMD
# require（和 _PLAYER_STATE_JS 里那套缓存/异步加载是同一份约定）。这里抽成独立
# 表达式，画图（GraphControl）和判分读取都用它，谁也别再裸写 dijit.byId。
_DIJIT_BOOT_JS = r"""(() => {
  const d = window.dijit || window.__schDijitRegistry;
  if (d && typeof d.byId === 'function') return 'ok';
  if (typeof window.require === 'function'
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
    return 'loading';
  }
  if (window.__schDijitLoading) return 'loading';
  return 'no-dijit';
})()"""


class WebPlayer:
    """连着答题浏览器（结界）：读符卡、落笔、交卡。"""

    def __init__(self, port: int = DEFAULT_PORT, log=None) -> None:
        self.port = port
        self.ws: CDP | None = None
        self.ctx = None
        self.title = ""
        # Player iframe 的 frameId：connect() 与 _player_ctx() 必须用同一个，
        # 否则 js()（隔离世界）和 eval_main()（主世界）会各说各话、读两个不同的 frame。
        self.player_frame = ""
        self._present_unverifiable = False
        self.log = log or (lambda _m: None)
        self.last_url = ""

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
            raise CDPError("结界里没有可用的页面（浏览器里没有可答题的标签页）")
        self.ws = CDP(page["webSocketDebuggerUrl"])
        self.ws.call("Page.enable")
        self.ws.call("Runtime.enable")
        self.title = page.get("title", "")
        self.ctx = None
        self.player_frame = ""
        self._present_unverifiable = False
        try:
            tree = self.ws.call("Page.getFrameTree")["frameTree"]
            self._resolve_player_frame(tree)
        except Exception:
            self.player_frame = ""
        # 不再注入主世界 Agent：全部操作走隔离世界 DOM 与一次性主世界求值。
        # 注意：调用方（app.pyw）会在前面补 “紫：”，这里不要再自带角色前缀。
        self.log(f"已顺着缝隙连上结界（{self.title[:60] or page.get('url', '')[:60]}）")
        return self

    def close(self) -> None:
        if self.ws:
            self.ws.close()
            self.ws = None
        self.ctx = None

    # ---- 基础
    @staticmethod
    def _frames_of(tree: dict) -> list[dict]:
        """展平 frameTree，返回所有 frame 描述。"""
        out: list[dict] = []

        def walk(node):
            f = (node or {}).get("frame") or {}
            if f:
                out.append(f)
            for c in (node or {}).get("childFrames") or []:
                walk(c)

        walk(tree)
        return out

    def _resolve_player_frame(self, tree: dict) -> str:
        """从 frameTree 里定下唯一的 Player frame，后续所有上下文都认它。

        优先保留上次认过的那个（页面内导航时 frameId 通常不变）；否则取最后一个
        Player frame —— 与 connect() 选“最近打开的标签页”保持一致。
        """
        ids = [f["id"] for f in self._frames_of(tree)
               if f.get("id") and "Player/Player.aspx" in (f.get("url") or "")]
        if self.player_frame and self.player_frame in ids:
            return self.player_frame
        self.player_frame = ids[-1] if ids else ""
        return self.player_frame

    def _player_ctx(self) -> int:
        tree = self.ws.call("Page.getFrameTree")["frameTree"]
        frame_id = self._resolve_player_frame(tree) or tree["frame"]["id"]
        r = self.ws.call("Page.createIsolatedWorld", {"frameId": frame_id, "worldName": "shinichi"})
        return r["executionContextId"]

    def _check_alive(self) -> None:
        """结界断了就别再往旧缝隙里塞术式了，让上层去重连。"""
        if getattr(self.ws, "dead", False):
            raise CDPError("结界已经断了（CDP 连接不可用），需要重新连一次")

    def js(self, expr: str, timeout: float = 20.0):
        self._check_alive()
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
                raise CDPError("符卡上的术式出错了（页面脚本异常）："
                               + str(r["exceptionDetails"].get("text"))[:120])
            return r["result"].get("value")

    def insert(self, text: str) -> None:
        self._check_alive()
        self.ws.call("Input.insertText", {"text": text})

    def key(self, k: str, code: str, vk: int, mods: int = 0) -> None:
        self._check_alive()
        for t in ("keyDown", "keyUp"):
            self.ws.call("Input.dispatchKeyEvent",
                         {"type": t, "key": k, "code": code,
                          "windowsVirtualKeyCode": vk, "modifiers": mods})

    def main_context_id(self) -> int | None:
        """Player iframe 的 main world 上下文；Dojo 全局只在这里可见。"""
        frame = getattr(self, "player_frame", "")
        # 页面导航会先创建 about:blank 再创建正式页面的上下文；必须取最新的
        # 一个，否则会拿到已经被销毁的旧 contextId。
        #
        # 上下文事件存在 ws.contexts（dict，按创建顺序），不会被普通事件列表
        # 截断到 500 条给挤掉 —— 旧实现把两者混在一个列表里，长会话一截断就
        # 永远找不到主世界，field_present 于是恒 False，整轮静默死循环。
        ctxs = getattr(self.ws, "contexts", None)
        if isinstance(ctxs, dict) and ctxs:
            for cid, c in reversed(list(ctxs.items())):
                aux = (c or {}).get("auxData") or {}
                if aux.get("isDefault") and (not frame or aux.get("frameId") == frame):
                    return int(cid)
            return None
        # 兜底：极老的连接对象只存了事件列表（保留旧行为，别一上来就瞎）。
        for msg in reversed(getattr(self.ws, "events", [])):
            if msg.get("method") != "Runtime.executionContextCreated":
                continue
            c = msg.get("params", {}).get("context", {})
            aux = c.get("auxData") or {}
            if aux.get("isDefault") and (not frame or aux.get("frameId") == frame):
                return int(c.get("id"))
        return None

    def eval_main(self, expr: str):
        self._check_alive()
        cid = self.main_context_id()
        if cid is None:
            return None
        try:
            r = self.ws.call("Runtime.evaluate",
                             {"expression": expr, "contextId": cid, "returnByValue": True})
        except CDPError as e:
            if "context" not in str(e).lower():
                raise
            time.sleep(0.35)
            cid = self.main_context_id()
            if cid is None:
                return None
            r = self.ws.call("Runtime.evaluate",
                             {"expression": expr, "contextId": cid, "returnByValue": True})
        if "exceptionDetails" in r:
            raise CDPError("符卡上的术式出错了（页面脚本异常）："
                           + str(r["exceptionDetails"].get("text"))[:160])
        return r.get("result", {}).get("value")

    def dijit_ready(self, timeout: float = 4.0) -> bool:
        """等 Dojo registry 就绪（真实 Pearson 可能要走 AMD 异步加载）。

        拿不到就返回 False，由调用方返回 ``'no-dijit'``；绝不裸写 ``dijit.byId``，
        否则只有 AMD 的页面上会直接 ReferenceError，被上层吞成“画图失败”。
        """
        deadline = time.time() + max(0.0, float(timeout))
        while True:
            try:
                st = self.eval_main(_DIJIT_BOOT_JS)
            except Exception:
                st = None
            if st == "ok":
                return True
            if st != "loading" or time.time() >= deadline:
                return False
            time.sleep(0.25)

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
        """在放大图形框里用 Dojo GraphControl API 画二次函数。

        返回：``ok`` / ``no-modal`` / ``no-dijit`` / ``no-popup`` / ``no-graph`` /
        ``no-widget`` / ``no-tool`` / ``draw-error`` / ``draw-failed`` /
        ``no-save`` / ``save-error`` / ``save-not-closed`` / ``saved``。
        """
        if not self.dijit_ready():
            return "no-dijit"
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
  const d = window.dijit || window.__schDijitRegistry;
  if (!d || typeof d.byId !== 'function') return 'no-dijit';
  const gw = d.byId(el.id);
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
                "const d=window.dijit||window.__schDijitRegistry;"
                "const w=d?d.byId(b.id):null;"
                "if(w&&w.onClick)w.onClick();else b.click();"
                "return 'ok';})()")
        except Exception:
            saved = "save-error"
        time.sleep(0.8)
        if self.graph_modal_open():
            # 有些 Pearson 弹窗会叠多层；Save 已把图形写回，隐藏残余弹窗
            try:
                self.eval_main(
                    "(() => {const d=window.dijit||window.__schDijitRegistry;"
                    "for(const e of [...document.querySelectorAll('[id*=GraphZoomPopup]')]){"
                    "const w=d?d.byId(e.id):null;if(w&&w.hide)w.hide();}"
                    "return 'ok';})()")
            except Exception:
                pass
            time.sleep(0.5)
        if self.graph_modal_open():
            return "save-not-closed"
        return str(saved or "saved")

    def add_graph_objects(self, objects: list[dict]) -> str:
        """在放大图形框里直接写入多个 GraphControl 对象（line/quadratic）。

        返回串与 :meth:`draw_quadratic` 同构，另外可能返回 ``no-dijit``。
        """
        if not self.dijit_ready():
            return "no-dijit"
        if not self.open_graph_modal():
            return "no-modal"
        js = """(() => {
  const ps = [...document.querySelectorAll('[id*=GraphZoomPopup]')];
  const pop = ps.find(e => {const r=e.getBoundingClientRect();
      return r.width>200 && r.height>150 && getComputedStyle(e).display!=='none'
             && e.querySelector('.xygraph');});
  if (!pop) return 'no-popup';
  const el = pop.querySelector('.xygraph');
  const d = window.dijit || window.__schDijitRegistry;
  if (!d || typeof d.byId !== 'function') return 'no-dijit';
  const gw = d.byId(el.id);
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
                "const d=window.dijit||window.__schDijitRegistry;"
                "const w=d?d.byId(b.id):null;"
                "if(w&&w.onClick)w.onClick();else b.click();"
                "return 'ok';})()")
        except Exception:
            saved = "save-error"
        time.sleep(0.8)
        if self.graph_modal_open():
            try:
                self.eval_main(
                    "(() => {const d=window.dijit||window.__schDijitRegistry;"
                    "for(const e of [...document.querySelectorAll('[id*=GraphZoomPopup]')]){"
                    "const w=d?d.byId(e.id):null;if(w&&w.hide)w.hide();}"
                    "return 'ok';})()")
            except Exception:
                pass
            time.sleep(0.5)
        if self.graph_modal_open():
            return "save-not-closed"
        return str(saved or "saved")

    def add_graph_objects_inline(self, objects: list[dict]) -> str:
        """优先操作页面内嵌图（不进放大弹窗）。只写入图形模型，不点页面顶部 Save。

        返回：``ok`` / ``no-dijit`` / ``no-inline`` / ``no-widget`` / ``inline-failed``。
        """
        if not self.dijit_ready():
            return "no-dijit"
        js = """(() => {
  const el = document.querySelector('.graphControl .xygraph') ||
             document.querySelector('.xygraph');
  if (!el) return 'no-inline';
  const d = window.dijit || window.__schDijitRegistry;
  if (!d || typeof d.byId !== 'function') return 'no-dijit';
  const gw = d.byId(el.id);
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
        """校验字段 UID 是否仍存在于当前页面（防止旧快照填新页面）。

        三重判据：先问主世界的 ``__schElements``（同一 element 才算数），主世界摸不到
        （eval_main 返回 None，例如上下文被境界换掉）就退回隔离世界只查 UID 属性；
        两边都问不到才返回 True —— 这时闸门降级为「只比 signature」，宁可不拦，
        也不能因为看不见主世界就把整题判成“控件没了”（那会无限丢答案重读）。
        """
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
        # 主世界：__schElements 只在这里可见。返回 None 说明主世界不可用，
        # 不能当成“字段不存在”（bool(None) is False 是本项目最坑的一个假阴性）。
        try:
            v = self.eval_main(js)
        except Exception:
            v = None
        if v is not None:
            return bool(v)
        # 隔离世界：看不见 element 表，但 UID 属性是 DOM 上的，照样能查“元素还在不在”。
        try:
            return bool(self.js(js))
        except Exception:
            # 两边都问不到：判定为“无法校验”，放行，让 signature 闸门独自把关。
            self._warn_present_unverifiable()
            return True

    def _warn_present_unverifiable(self) -> None:
        """「校验不了」只提示一次，别每题每控件刷屏。

        调用方（app.pyw）会在前面补 “紫：”，这里不要再自带角色前缀。
        """
        if getattr(self, "_present_unverifiable", False):
            return
        self._present_unverifiable = True
        try:
            self.log("境界的缝隙看不清控件了，这一轮只比快照指纹。")
        except Exception:
            pass

    def math_text(self) -> list:
        """从 MathML/KaTeX/MathJax/data-latex 提取公式文本（学自 Auto-Pearson math.js）。"""
        try:
            v = self.js(_MATH_JS)
            return [str(x) for x in (v or []) if str(x).strip()][:20]
        except Exception:
            return []

    def completion_state(self) -> dict:
        """返回当前判分/警告弹窗的结构化状态（学自 Auto-Pearson completionState）。

        ``kind`` 的完整枚举：
        ``correct`` / ``partial`` / ``incorrect`` / ``finished`` / ``leave`` / ``none``。
        （``partial`` = 部分正确，例如 "Your answer is partially correct."；
        调用方应当按“没全对”处理，而不是按答对。）

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
        """判分结果。返回枚举：``correct`` / ``partial`` / ``incorrect`` / ``''``。

        旧接口只认 correct / incorrect / ''；``partial`` 是这次新加的
        （部分正确），调用方要单独处理，别再当成答对。
        """
        st = self.completion_state()
        kind = str(st.get("kind") or "")
        if kind in ("correct", "finished"):
            return "correct"
        if kind == "partial":
            return "partial"
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
        """点左侧题号，跳到指定 Question（不依赖 Next 按钮）。

        题号文字的规则必须和 `_STATE_JS` 里读 `questions` 的那套一致：Pearson 的
        anchor 文本常常是 `Question 5, Correct` / `Question 5, Partially correct`，
        旧实现要求整串严格等于 `Question 5`，于是所有跳题/回补都永远失败。
        这里同时看 innerText 和 aria-label，并额外容忍只有数字的写法。
        """
        js = r"""(() => {
  const want = %d;
  const labels = [...document.querySelectorAll('a.questionLabel')];
  const textOf = (x) => ((x.innerText || '') + ' ' + (x.getAttribute('aria-label') || ''));
  let a = labels.find((x) => {
    const m = /Question\s+(\d+)\b/i.exec(textOf(x));
    return !!m && parseInt(m[1], 10) === want;
  });
  // 有的 Pearson 版本 anchor 里只写数字（"5"）。
  if (!a) {
    a = labels.find((x) => {
      const t = ((x.innerText || '').trim() || (x.getAttribute('aria-label') || '').trim());
      const m = /^(\d+)$/.exec(t);
      return !!m && parseInt(m[1], 10) === want;
    });
  }
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
        """点一个选项，并确认 checked 状态真的变成了期望值。

        三条路依次试：控件本身、父节点、对应的 label。全部用 getElementById /
        htmlFor 比对定位，不拼 CSS 选择器（id 里带引号/括号时拼选择器会炸）。
        """
        rid_js = json.dumps(rid)
        for expr in ("document.getElementById(%s)" % rid_js,
                     "(document.getElementById(%s) || {}).parentElement" % rid_js,
                     "[...document.querySelectorAll('label')]"
                     ".find((l) => l.htmlFor === %s || l.getAttribute('for') === %s)"
                     % (rid_js, rid_js)):
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
        radios = [r for r in st.get("radios", []) if not r.get("disabled")]
        # 多小问里上一问的复选框会 disabled 留在页面上；它们不是当前小问
        # 的选项，不能参与匹配（否则会把 B 匹配到上一问的禁用框上）。
        checks = [c for c in st.get("checks", []) if not c.get("disabled")]
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
            if box.get("disabled"):
                continue
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

        绝不在页面上按文字乱点：只在「确实含着这段警告」的容器里找按钮。

        2026-11-28 真页面踩到的坑：Pearson 的确认框是
        `div#xl_player_dialogs_ConfirmationDialog_0.dijitDialog`，
        里面分两块——
          · `..._ConfirmationDialog_0_content`（`dijitDialogPaneContent`）只放文字；
          · `div.xlDialogFooter > div.xlDialogButtonContainer > button` 才是按钮。
        旧代码挑「文字最短的那个匹配节点」，正好挑中只有文字的那块，
        于是永远返回 `no-button` —— 警告框关不掉，后面所有导航都被它挡住。
        （灵梦：门牌挂在左边，钥匙孔在右边，你光盯着门牌当然开不了门。）
        """
        want = "yes" if str(choice).lower().startswith("y") else "no"
        # 先用 leave_state 已经解析出来的那个唯一按钮 id
        target_id = ""
        try:
            ls = self.leave_state()
            if ls.get("visible"):
                target_id = str(ls.get(want + "_id") or "")
        except Exception:
            target_id = ""
        js = r"""
(() => {
  const want = %s;
  const targetId = %s;
  const vis = (e) => { if (!e) return false; const r = e.getBoundingClientRect();
                       return r.width > 2 && r.height > 2; };
  const clean = (s) => (s || '').replace(/\u200b/g, '').replace(/\s+/g, ' ').trim();
  const fire = (node) => {
    try { node.click(); } catch (e) {}
    if (String(node.tagName || '').toUpperCase() === 'BUTTON') return true;
    // dijit 那种假按钮（span[role=button]）：补一整套鼠标事件
    try {
      const r = node.getBoundingClientRect();
      const o = {bubbles: true, cancelable: true, button: 0,
                 clientX: r.x + r.width / 2, clientY: r.y + r.height / 2};
      for (const t of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
        node.dispatchEvent(new MouseEvent(t, o));
      }
    } catch (e) {}
    return true;
  };
  const exact = (b) => clean(b.innerText || b.value
                             || b.getAttribute('aria-label')
                             || b.getAttribute('title')).toLowerCase() === want;
  // ① 第 0 选择：leave_state 给的唯一 id（最可靠）
  if (targetId) {
    const byId = document.getElementById(targetId);
    if (vis(byId)) { fire(byId); return 'ok'; }
  }
  // ② 整页找「文字正好是 Yes/No」且所在容器里确实有这段警告的按钮
  const leaveRe = /(leave this question|not completed this question|continue without checking|will not receive any credit|are you sure you want to (leave|continue))/i;
  const cands = [...document.querySelectorAll('button, a, [role=button], input[type=button]')]
    .filter(vis).filter(exact);
  const good = cands.filter((b) => {
    let p = b;
    for (let i = 0; i < 8 && p; i++) {
      if (leaveRe.test(clean(p.innerText || ''))) return true;
      p = p.parentElement;
    }
    return false;
  });
  if (good.length === 1) { fire(good[0]); return 'ok'; }
  if (good.length > 1) return 'ambiguous';
  if (cands.length === 1) { fire(cands[0]); return 'ok'; }
  return cands.length ? 'ambiguous' : 'no-button';
})()""" % (json.dumps(want), json.dumps(target_id))
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
        """原生下拉框：按选项文字选中。

        返回枚举：``ok`` / ``no``（找不到 select）/ ``no-match`` /
        ``ambiguous``（包含式兜底命中多个，宁可不选也不选错）。
        调用方只认 ``ok``，其它值都算失败，别把“差不多”当成选上了。
        """
        sid = json.dumps(select_id)
        want = json.dumps(text or "")
        # 没有精确命中才用“包含”兜底；命中多个就报 ambiguous，宁可不选也不选错。
        js = ("(() => { const s = document.getElementById(%s); if (!s) return 'no';"
              " const norm = (x) => (x || '').replace(/\\s+/g, '').toLowerCase();"
              " const w = norm(%s);"
              " let best = -1;"
              " const partials = [];"
              " for (let i = 0; i < s.options.length; i++) {"
              "   const t = norm(s.options[i].text);"
              "   if (w && t === w) { best = i; break; }"
              "   if (w && t && (t.includes(w) || w.includes(t))) partials.push(i);"
              " }"
              " if (best < 0 && partials.length === 1) best = partials[0];"
              " if (best < 0 && partials.length > 1) return 'ambiguous';"
              " if (best < 0) return 'no-match';"
              " s.selectedIndex = best;"
              " s.dispatchEvent(new Event('input', { bubbles: true }));"
              " s.dispatchEvent(new Event('change', { bubbles: true }));"
              " return 'ok'; })()") % (sid, want)
        return self.js(js)

    def focus_field(self, field_id: str) -> str:
        """把焦点放进那个空里。

        照《作业侠客》的写法：**纯合成事件 + `i.focus()`，不用坐标**。
        我们原来是用 `Input.dispatchMouseEvent` 按 getBoundingClientRect 去点，
        可播放器在 iframe 里 —— 元素坐标是 iframe 相对的，CDP 的 Input 却按整页算，
        于是**点歪了**：焦点没进去，`clear_field` 的前置检查直接返回 False，
        整个填空被放弃，最后报「没有更多题了」。（2026-11-28 用户实测）
        """
        expr = "document.getElementById(%s)" % json.dumps(field_id)
        # 先确保它在视野里（滚一下不影响焦点）
        try:
            self.js("(() => { const s = %s; if (s) s.scrollIntoView({block: 'center'}); })()"
                    % expr)
            time.sleep(0.2)
        except Exception:
            pass
        js = ("(() => { const s = %s; if (!s) return 'no';"
              " const i = s.querySelector('input.focusNode') || s;"
              " const r = s.getBoundingClientRect();"
              " const o = {bubbles:true, cancelable:true,"
              " clientX:r.x+4, clientY:r.y+r.height/2, button:0};"
              " for (const t of ['pointerdown','mousedown','pointerup','mouseup','click'])"
              " s.dispatchEvent(new MouseEvent(t, o));"
              " i.focus(); return 'ok'; })()") % expr
        return self.js(js)

    def clear_field(self) -> bool:
        """清空当前聚焦的那个空；**先确认焦点真在编辑器里**，否则不按。

        学自《作业侠客》`clear_field`：原来是无条件发 Ctrl+A + Delete，
        焦点被页面抢走时（点了别处、页面重绘、格子只读），Ctrl+A 会选中
        **整页文字**，后面所有键入都进不了输入框。
        （帕秋莉：笔不在自己手里，就别乱划。）
        """
        focused = False
        try:
            focused = bool(self.js(
                "(() => { const a = document.activeElement;"
                " return !!a && /focusNode/.test(String(a.className || '')); })()"))
        except Exception:
            focused = False
        if not focused:
            return False
        self.key("a", "KeyA", 65, 2)
        self.key("Delete", "Delete", 46)
        try:
            n = int(self.js(
                "(() => { const s = window.getSelection && window.getSelection();"
                " return s ? String(s.toString() || '').length : 0; })()") or 0)
            if n > 200:
                self.js("(() => { const s = window.getSelection && window.getSelection();"
                        " if (s) s.removeAllRanges(); return 'cleared'; })()")
                return False
        except Exception:
            pass
        return True

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
            # Dojo 的展开动画/慢 VM 上 0.35s 不一定够；轮询同一页几次，
            # 否则会在“按钮其实已经出来”时误报 no-tool。
            last = "no-tool"
            for _ in range(8):
                time.sleep(0.25)
                last = self.palette_click(field_id, classes, title_re, allow_more=False)
                if last != "no-tool":
                    return last
            return last
        return res

    def palette_infinity(self, field_id: str = "") -> str:
        """点当前输入框调色板里的 ∞ 按钮，插入真正的无穷符号。

        为什么不用 ``insert_math("\\inf")``：Pearson 会把它渲染成字面文本
        “infinity”，Check 不认；调色板按钮才会插入 ``∞``（2026-11-28 Q17 实测）。
        """
        js = r"""(() => {
  const vis = (e) => { if (!e) return false; const r = e.getBoundingClientRect();
                       const cs = getComputedStyle(e);
                       return r.width > 2 && r.height > 2
                         && cs.display !== 'none' && cs.visibility !== 'hidden'
                         && cs.opacity !== '0'; };
  let pals = [...document.querySelectorAll('div.xlInlineMathPalette')].filter(vis);
  if (!pals.length) return 'no-palette';
  const field = document.getElementById(%s);
  let pal = pals[pals.length - 1];
  if (field) {
    const fr = field.getBoundingClientRect();
    let bd = 1e9;
    for (const p of pals) {
      const r = p.getBoundingClientRect();
      const d = Math.abs(r.top - fr.top) + Math.abs(r.left - fr.left);
      if (d < bd) { bd = d; pal = p; }
    }
  }
  const b = [...pal.querySelectorAll('button')].filter(vis).find((x) => {
    const cls = String(x.className || '');
    const lab = ((x.getAttribute('title') || '') + ' ' +
                 (x.getAttribute('aria-label') || '')).trim();
    return /(^|\s)iconInf(\s|$)/.test(cls) || /infinity|\\inf/i.test(lab);
  });
  if (!b) return 'no-button';
  const r = b.getBoundingClientRect();
  const o = {bubbles:true, cancelable:true, clientX:r.x+r.width/2,
             clientY:r.y+r.height/2, button:0};
  for (const t of ['pointerdown','mousedown','pointerup','mouseup','click']) {
    try { b.dispatchEvent(t.startsWith('pointer') ? new PointerEvent(t, o) : new MouseEvent(t, o)); } catch (e) {}
  }
  return 'ok';
})()""" % json.dumps(field_id or "")
        try:
            return str(self.js(js) or "no")
        except Exception as e:
            return "err:" + str(e)

    def close_palette(self) -> None:
        """关掉当前公式调色板，别让它的浮层挡住下一个输入框的真实点击。"""
        js = r"""(() => {
  const vis = (e) => { if (!e) return false; const r = e.getBoundingClientRect();
                       const cs = getComputedStyle(e);
                       return r.width > 2 && r.height > 2
                         && cs.display !== 'none' && cs.visibility !== 'hidden'
                         && cs.opacity !== '0'; };
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
  const vis = (e) => { const r = e.getBoundingClientRect();
                       const cs = getComputedStyle(e);
                       return r.width > 2 && r.height > 2
                         && cs.display !== 'none' && cs.visibility !== 'hidden'
                         && cs.opacity !== '0'; };
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

    def close_matrix_popup(self) -> str:
        """关掉残留的矩阵尺寸弹窗，避免下次 fill_matrix 误用上一题的尺寸。"""
        js = r"""(() => {
  const vis = (e) => { if (!e) return false; const r = e.getBoundingClientRect();
                       const cs = getComputedStyle(e);
                       return r.width > 2 && r.height > 2
                         && cs.display !== 'none' && cs.visibility !== 'hidden'
                         && cs.opacity !== '0'; };
  let pops = [...document.querySelectorAll(
      '[id*=MatrixSizePopup], [id*=MatrixPopup], [id*=MatrixDialog]')].filter(vis);
  if (!pops.length) return 'none';
  const pop = pops[pops.length - 1];
  const btn = [...pop.querySelectorAll('button')]
    .find((b) => /^(cancel|close)$/i.test((b.innerText || '').trim()))
    || pop.querySelector('[data-dojo-attach-point="closeButtonNode"]');
  if (!btn) return 'no-button';
  try { btn.click(); } catch (e) { return 'err:' + e; }
  return 'ok';
})()"""
        try:
            return str(self.js(js) or "no")
        except Exception:
            return "no"

    def _click_matrix_ok(self) -> str:
        """没有 id 时，在矩阵弹窗内部按文字点 OK（别点到页面其它 OK）。"""
        js = r"""(() => {
  const vis = (e) => { const r = e.getBoundingClientRect();
                       const cs = getComputedStyle(e);
                       return r.width > 2 && r.height > 2
                         && cs.display !== 'none' && cs.visibility !== 'hidden'
                         && cs.opacity !== '0'; };
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
        """矩阵格子数（td 数量）。按 id 取元素，绝不把 field_id 拼进 CSS 选择器。"""
        return self.js(
            "(() => { const f = document.getElementById(%s);"
            " return f ? f.querySelectorAll('table.eqMatrix td').length : 0; })()"
            % json.dumps(field_id)) or 0

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
        """在指定空里插一个 rows×cols 的矩阵并逐格落笔。

        返回空串表示成功；非空串是给用户看的失败原因（会被拼进
        “魔理沙：填矩阵失败——…” 里）。``field_id`` 全程用 getElementById 取，
        不拼 CSS 选择器（id 里有引号/数字开头时旧写法会直接 SyntaxError）。
        """
        # 先清掉上一题/上一次尝试残留的矩阵尺寸弹窗，否则会直接改错弹窗。
        # 关不掉也继续：后面 st.get(...) 还会再读一次，读到的若不是本题的弹窗，
        # 尺寸那一步会失败并如实报错，不会把旧尺寸当成新矩阵。
        if self.matrix_popup():
            self.close_matrix_popup()
            time.sleep(0.35)
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
            return f"矩阵的术式面板没从境界里浮出来（{clicked or 'no-tool'}）"
        if st.get("spins"):
            if not self.set_spinner(st["spins"][0], rows) \
                    and not self._set_input_value(st["spins"][0], rows):
                return f"行数没设成 {rows} 行"
            if len(st["spins"]) > 1 and not self.set_spinner(st["spins"][1], cols) \
                    and not self._set_input_value(st["spins"][1], cols):
                return f"列数没设成 {cols} 列"
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
            return f"矩阵尺寸没设成（要 {rows}×{cols} 格，术式只结了 {n} 格）"
        # 矩阵结构已经插进去了，把调色板收起来：它的浮层会挡住后面的输入框
        self.close_palette()

        click_cell = r"""
(() => {
  const f = document.getElementById(%s);
  if (!f) return 'no-field';
  const cells = f.querySelectorAll('table.eqMatrix td');
  const cell = cells[%d];
  if (!cell) return 'no-cell';
  const row = cell.querySelector('span.eqRow') || cell;
  const r = row.getBoundingClientRect();
  const o = {bubbles:true, cancelable:true, clientX:r.x + 4, clientY:r.y + r.height / 2, button:0};
  for (const t of ['pointerdown','mousedown','pointerup','mouseup','click'])
    row.dispatchEvent(new MouseEvent(t, o));
  const fn = f.querySelector('input.focusNode');
  if (fn) fn.focus();
  return 'ok';
})()
"""
        total = rows * cols
        for i, v in enumerate(values[:total]):
            time.sleep(1.2)
            self.js(click_cell % (json.dumps(field_id), i))
            time.sleep(0.2)
            self.insert_math(v)
            time.sleep(1.0)
        # 逐格回读：不能只看全局 label 里有没有 "nothing"。
        # 有些矩阵某格插入失败时标签可能仍是空串，最终却不会报错。
        time.sleep(0.4)
        empty = self.js(r"""(() => {
  const f = document.getElementById(%s);
  if (!f) return [];
  const cells = [...f.querySelectorAll('table.eqMatrix td')];
  const bad = [];
  cells.forEach((td, i) => {
    const lab = td.querySelector('.eqAccessibleLabel');
    const txt = ((td.innerText || '') + ' ' + (lab ? lab.textContent : ''))
      .replace(/\s+/g, ' ').trim();
    if (!txt || /(^|\s)nothing(\s|$)/i.test(txt)) bad.push(i + 1);
  });
  return bad;
})()""" % json.dumps(field_id)) or []
        if empty:
            return "矩阵第 " + "、".join(str(x) for x in empty[:6]) + " 格没填进去（符卡还是空的）"
        label = self.js(
            "(() => { const f = document.getElementById(%s); if (!f) return '';"
            " const l = f.querySelector('.eqAccessibleLabel');"
            " return (l && l.textContent) || ''; })()" % json.dumps(field_id)) or ""
        if label.count("nothing"):
            return "矩阵没填全，符卡还剩空格"
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

    # ---- 数学输入：Pearson 编辑器是「边打边结构化」的 -------------------
    # 紫：那台编辑器的规矩很刁钻——敲下 `/`，光标就钻进分母；敲下 `^`，就钻进指数，
    # 都不肯自己出来。这时候你打一个 `)`，它会被吞进分母，整行标红。
    # 要真的跳出来，得按**两下**右箭头（一下只到这一项末尾）。
    #
    # 所以填公式不能「整段塞进去再统一跳」，要一段段编排：
    # 普通片段整段插；遇到 `/` `^` `_` 先把这一项打完、跳出去，再继续。
    # （这套节奏是拿真页面 A/B 调出来的：按箭头**之前**必须等，等了才不会丢字符。）
    MATH_SETTLE = 0.02
    MATH_ARROW_WAIT = 0.8
    MATH_AFTER_ARROW = 0.02

    @staticmethod
    def _match_paren(s: str, i: int, end: int) -> int:
        """s[i] 是 ( 或 [，返回配对的 ) / ] 下标；不配对返回 -1。"""
        depth = 0
        for j in range(i, end):
            c = s[j]
            if c in "([":
                depth += 1
            elif c in ")]":
                depth -= 1
                if depth == 0:
                    return j
        return -1

    def _math_put(self, text: str) -> None:
        """插一小段，**整段 insertText**。

        2026-11-28 在真编辑器上做了 9 轮 A/B，结论是两条：
        1. `_type_seq` 只会把**平段**交过来（`/2`、`^2`、`x+3` 这种，
           靠 `_flat_group` / `_flat_denom` / `_flat_primary` 保证），
           平段整段插进去是对的；**带嵌套结构的整串**才会被吃错。
        2. 真正脆的是「按右箭头」的时机：`insertText` 会当场提交，
           而逐字符 `char` 事件不提交 —— 提交前按箭头会把刚打的字带走。
           实测「平段 insertText + 等 0.8s 再按箭头」2/2 稳定通过。

        所以：平段整段插（快），按箭头的等待放到 0.8s（稳）。
        """
        if not text:
            return
        self.insert(text)
        if self.MATH_SETTLE:
            time.sleep(self.MATH_SETTLE)

    def _math_escape(self, n: int = 2) -> None:
        """从分母/指数里跳出来：等编辑器重排 → 两下右箭头 → 等光标落定。"""
        time.sleep(self.MATH_ARROW_WAIT)
        for _ in range(n):
            self._arrow_right()
        time.sleep(self.MATH_AFTER_ARROW)

    @staticmethod
    def _flat_group(s: str, start: int, end: int) -> bool:
        """括号里能不能整段一次打（没有分式/指数/根号）。"""
        seg = s[start:end]
        return not any(k in seg for k in ("/", "^", "_", "\\sqrt"))

    @staticmethod
    def _flat_denom(s: str, start: int, end: int) -> bool:
        """分母能不能整段一次打：再嵌一层 `/` 或根号，右括号又会被吞。"""
        seg = s[start:end]
        return bool(seg) and "/" not in seg and "\\sqrt" not in seg

    def _primary_extent(self, s: str, i: int, end: int) -> int:
        """`^` / `_` 后面「一个单位」到哪儿结束（只算下标，不插入）。"""
        while i < end and s[i] in " \t":
            i += 1
        if i >= end:
            return i
        if s[i] in "+-" and i + 1 < end:
            i += 1
            while i < end and s[i] in " \t":
                i += 1
        if i >= end:
            return i
        c = s[i]
        if c in "([":
            j = self._match_paren(s, i, end)
            return (j + 1) if j >= 0 else end
        if c == "\\":
            j = i + 1
            while j < end and s[j].isalpha():
                j += 1
            return j
        if c.isdigit():
            j = i
            while j < end and (s[j].isdigit() or s[j] == "."):
                j += 1
            return j
        return i + 1

    @staticmethod
    def _flat_primary(s: str, start: int, end: int) -> bool:
        """指数/根号参数能不能整段一次打。"""
        seg = s[start:end]
        if not seg:
            return False
        if seg[0] in "([":
            inner = seg[1:-1] if seg[-1] in ")]" else seg[1:]
            return not any(k in inner for k in ("/", "^", "_", "\\sqrt"))
        return True

    def _denom_end(self, s: str, i: int, end: int) -> int:
        """分母到哪儿为止。

        我们的 to_editor_input 会把「后面还跟着因子」的分式写成 `(1)/(2)x`，
        所以分母若以括号开头，就只取那一组、然后跳出去——不能一路吃到 `x`。
        （慧音：一个分式只该管住它自己的分母，后面那个 x 是另一个因数。）
        """
        j = i
        while j < end and s[j] in " \t":
            j += 1
        if j < end and s[j] in "([":
            k = self._match_paren(s, j, end)
            return (k + 1) if k >= 0 else end
        depth = 0
        while j < end:
            c = s[j]
            if c in "([":
                depth += 1
            elif c in ")]":
                if depth == 0:
                    break
                depth -= 1
            elif depth == 0 and c in "+-":
                break
            j += 1
        return j

    def _type_denom(self, s: str, i: int, end: int) -> None:
        """把分母 [i, end) 打进去。括号递归处理，其余整段插。"""
        buf = ""
        j = i
        while j < end:
            c = s[j]
            if c in "([":
                if buf:
                    self._math_put(buf)
                    buf = ""
                k = self._match_paren(s, j, end)
                if k < 0:
                    buf += s[j:end]
                    break
                self._math_put(c)
                self._type_seq(s, j + 1, k)
                self._math_put(")" if c == "(" else "]")
                j = k + 1
                continue
            buf += c
            j += 1
        if buf:
            self._math_put(buf)

    def _type_primary(self, s: str, i: int, end: int) -> int:
        """指数的「一个单位」：^(...)、^-1、^2、^n、^\\pi。返回新下标。"""
        while i < end and s[i] in " \t":
            i += 1
        if i >= end:
            return i
        sign = ""
        if s[i] in "+-" and i + 1 < end:
            sign = s[i]
            i += 1
            while i < end and s[i] in " \t":
                i += 1
        if i >= end:
            self._math_put(sign)
            return i
        c = s[i]
        if c in "([":
            j = self._match_paren(s, i, end)
            if j < 0:
                self._math_put(sign + s[i:end])
                return end
            self._math_put(sign + c)
            self._type_seq(s, i + 1, j)
            self._math_put(")" if c == "(" else "]")
            return j + 1
        if c == "\\":
            j = i + 1
            while j < end and s[j].isalpha():
                j += 1
            self._math_put(sign + s[i:j])
            return j
        if c.isdigit():
            j = i
            while j < end and (s[j].isdigit() or s[j] == "."):
                j += 1
            self._math_put(sign + s[i:j])
            return j
        self._math_put(sign + c)
        return i + 1

    def _type_seq(self, s: str, i: int, end: int) -> None:
        """编排 [i, end) 这一段表达式（不含外层括号）。

        能一次插完的就不拆：
        - 普通片段后面直接跟 `/` + 简单分母 → `x+3/2`、`16/m^2` 一次插；
        - 整组 `(...)` 是纯的 → 整组一次插；
        - 整组 + 简单分母/指数 → `(a+b)/(c+d)`、`(x+1)^2` 一次插；
        - `^2` / `^-1` / `^(x+1)` / `\\sqrt(2x+1)` 各算一个整体。
        这样既少几次 CDP 往返，右括号也一定在跳出分式之后才落笔。
        """
        while i < end:
            c = s[i]
            if c in " \t":
                i += 1
                continue
            if c in "([":
                j = self._match_paren(s, i, end)
                if j < 0:
                    self._math_put(s[i:end])
                    return
                # 整组 + 简单分母：(a+b)/(c+d)
                if (j + 1 < end and s[j + 1] == "/"
                        and self._flat_group(s, i + 1, j)):
                    k = self._denom_end(s, j + 2, end)
                    if k > j + 2 and self._flat_denom(s, j + 2, k):
                        self._math_put(s[i:k])
                        self._math_escape()
                        i = k
                        continue
                # 整组 + 简单指数：(x+1)^2
                if (j + 1 < end and s[j + 1] in "^_"
                        and self._flat_group(s, i + 1, j)):
                    k = self._primary_extent(s, j + 2, end)
                    if k > j + 2 and self._flat_primary(s, j + 2, k):
                        self._math_put(s[i:k])
                        self._math_escape()
                        i = k
                        continue
                # 纯整组一次插：(x+1)
                if self._flat_group(s, i + 1, j):
                    self._math_put(s[i:j + 1])
                    i = j + 1
                    continue
                # 组里有分式/指数：老老实实拆
                self._math_put(c)
                self._type_seq(s, i + 1, j)
                self._math_put(")" if c == "(" else "]")
                i = j + 1
                continue
            if c in ")]":
                # 正常情况下括号上面就配好对了；孤立闭括号按原样插
                self._math_put(c)
                i += 1
                continue
            if c == "/":
                k = self._denom_end(s, i + 1, end)
                if k > i + 1 and self._flat_denom(s, i + 1, k):
                    self._math_put(s[i:k])      # "/2" 一次插
                    self._math_escape()
                    i = k
                    continue
                self._math_put("/")
                self._type_denom(s, i + 1, k)
                self._math_escape()
                i = k
                continue
            if c in "^_":
                k = self._primary_extent(s, i + 1, end)
                if k > i + 1 and self._flat_primary(s, i + 1, k):
                    self._math_put(s[i:k])      # "^2" 一次插
                    self._math_escape()
                    i = k
                    continue
                self._math_put(c)
                i = self._type_primary(s, i + 1, end)
                self._math_escape()
                continue
            if c == "\\":
                j = i + 1
                while j < end and s[j].isalpha():
                    j += 1
                cmd = s[i:j]
                if cmd == "\\sqrt":
                    k = self._primary_extent(s, j, end)
                    if k > j and self._flat_primary(s, j, k):
                        self._math_put(s[i:k])   # "\\sqrt(2x+1)" 一次插
                        self._math_escape()
                        i = k
                        continue
                    self._math_put(cmd)
                    i = self._type_primary(s, j, end)
                    self._math_escape()
                    continue
                self._math_put(cmd)
                i = j
                continue
            # 普通字符：收到下一个特殊符号；若后面紧跟简单分母，连分母一起插
            j = i + 1
            while j < end and s[j] not in "()[]/^_\\":
                j += 1
            # 函数名后面跟一个「纯括号组」时整段一起插：`ln (2x+1)` 里那个空格
            # 是语义分隔，拆成两次 insertText 有可能被编辑器吃掉，函数就变乘号了。
            if (j < end and s[j] in "([" and s[i:j].endswith(" ")):
                k2 = self._match_paren(s, j, end)
                if k2 > j and self._flat_group(s, j + 1, k2):
                    self._math_put(s[i:k2 + 1])
                    i = k2 + 1
                    continue
            if j < end and s[j] == "/":
                k = self._denom_end(s, j + 1, end)
                if k > j + 1 and self._flat_denom(s, j + 1, k):
                    self._math_put(s[i:k])      # "x+3/2" 一次插
                    self._math_escape()
                    i = k
                    continue
            self._math_put(s[i:j])
            i = j

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
        """把一段表达式填进公式编辑器。

        紫：整段塞进去是不行的——`/` 和 `^` 会让光标停在分母/指数里，
        右括号会被吞掉。所以交给 `_type_seq` 一段段编排，该跳的时候先跳。
        `text` 应该是 `latex.to_editor_input()` 的产物（已经去过反斜杠以外
        的 Unicode，分式/根号/对数都换成了编辑器认的写法）。
        """
        s = str(text or "")
        if not s:
            return
        self._type_seq(s, 0, len(s))


    # ================================================================
    # 下面这一整段学自《作业侠客》的 WebPlayer：
    # 「等（不写死 sleep）」「四条下一题路线」「判分框」「作业总览页」「重开标签」。
    # 我们的旧代码是边踩坑边补的特判，不成体系；他这套是跑顺过的，照搬。
    # （灵梦：人家走通的路，就别自己再摸一遍了。）
    # ================================================================
    def js_object(self, expr: str, timeout: float = 15.0):
        """跑一段 JS 并返回**对象引用**（不取值），拿来拿 DOM 元素的 objectId 做截图。"""
        self._check_alive()
        if self.ctx is None:
            self.ctx = self._player_ctx()
        return self.ws.call("Runtime.evaluate",
                            {"expression": expr, "contextId": self.ctx,
                             "returnByValue": False}, timeout=timeout)

    def top_js(self, expr: str, timeout: int = 10):
        """在**最外层**页面里跑 JS（题号、‹ › 箭头、Save 都在那一层，不在播放器 iframe 里）。"""
        r = self.ws.call("Runtime.evaluate",
                      {"expression": expr, "returnByValue": True}, timeout=timeout)
        return r.get("result", {}).get("value")

    def top_href(self) -> str:
        """最外层页面的 URL（判断「是不是被踢回作业总览页」用）。"""
        try:
            v = self.top_js("location.href")
            href = v if isinstance(v, str) else ""
        except Exception:
            href = ""
        if href.startswith("http"):
            self.last_url = href
        return href

    def wait_js(self, expr: str, timeout: float = 2.0, interval: float = 0.12) -> bool:
        """等一段 JS 返回真值；超时返回 False。"""
        end = time.time() + timeout
        while time.time() < end:
            try:
                if self.js(expr):
                    return True
            except Exception:
                pass
            time.sleep(interval)
        return False

    def wait_feedback(self, timeout: float = 12.0, interval: float = 0.2) -> str:
        """等判分弹窗出文字。"""
        end = time.time() + timeout
        while time.time() < end:
            try:
                v = (self.feedback() or "").strip()
                if v:
                    return v
            except Exception:
                pass
            time.sleep(interval)
        return ""

    def wait_text_change(self, old_text: str, timeout: float = 8.0,
                         interval: float = 0.2) -> bool:
        """等题干文字变了（换 Part / 换题）。"""
        end = time.time() + timeout
        while time.time() < end:
            try:
                if (self.state() or {}).get("text") != old_text:
                    return True
            except Exception:
                pass
            time.sleep(interval)
        return False

    def label_of(self, field_id: str) -> str:
        try:
            return str(self.js(
                "(document.getElementById(%s) || {}).getAttribute && "
                "document.getElementById(%s).getAttribute('aria-label') || ''"
                % (json.dumps(field_id), json.dumps(field_id))) or "")
        except Exception:
            return ""

    def feedback_visible(self) -> bool:
        """判分框还开着吗（用于判断「点了下一题以后到底翻了没有」）。"""
        try:
            return bool(self.js(_FEEDBACK_VIS_JS))
        except Exception:
            return False

    def click_feedback_next(self) -> bool:
        """点判分框里的「Next question」。

        真 Pearson（2026-11 新界面）做完一题后，这是**唯一可用**的下一题按钮：
        点它 = 关框 + 进下一节/下一题，标签和 URL 都不动。
        """
        try:
            return str(self.js(_FEEDBACK_NEXT_JS) or "") == "ok"
        except Exception:
            return False

    def click_next_btn(self) -> str:
        """点播放器标题栏自己那颗「下一题」按钮（`button.btnNext`）。

        做完一整题后它是 disabled，这时要用 `click_feedback_next()`。
        """
        try:
            return str(self.js(_NEXT_BTN_JS) or "")
        except Exception:
            return "no"

    def click_inline_next(self) -> bool:
        """点播放器里**不会跳走**的「下一题」（只认 `<button>` 和 `#`/`javascript:` 的 `<a>`）。"""
        try:
            return str(self.js(_INLINE_NEXT_JS) or "") == "ok"
        except Exception:
            return False

    def click_next_arrow(self) -> bool:
        """点「下一题」那个箭头（`›`）。"""
        try:
            if self.js(_NEXT_ARROW_JS) == "ok":
                return True
        except Exception:
            pass
        try:
            return self.top_js(_NEXT_ARROW_JS) == "ok"
        except Exception:
            return False

    def wait_advanced(self, old_qn, old_text: str, timeout: float = 20.0,
                      interval: float = 0.25) -> bool:
        """等「真的翻到下一节/下一题」。

        不能只看文字变化：判分后分数行会从 `Points: 0 of 1` 变成 `Points: 1 of 1`，
        只按文字判断会把「刚判完、还没翻页」误当成翻页成功。
        判据：① 题号变了；或 ② Check answer 又出现了（说明已在新的一节）、
        文字也换了、判分框已关。
        """
        end = time.time() + timeout
        while time.time() < end:
            try:
                st = self.state() or {}
                q = st.get("qno") if st.get("qno") is not None else st.get("qnum")
                if old_qn is not None and q is not None and q != old_qn:
                    return True
                txt = st.get("text") or ""
                if (txt and txt != old_text and st.get("hasCheck")
                        and not self.feedback_visible()):
                    return True
            except Exception:
                pass
            time.sleep(interval)
        return False

    def close_feedback(self) -> str:
        """点掉判分弹窗（Well done / Nice work …）里的 OK。

        那个 OK 有时是灰的（弹窗还在渐显、按钮 disabled），合成点击会被吞，
        所以：等它可点 → 原生 click() + 合成事件都来一遍 → 回读弹窗是否没了
        → 再试 → Esc 兜底。
        """
        click_ok = r"""
(() => {
  const vis = (e) => {
    if (!e.getClientRects().length) return false;
    const s = getComputedStyle(e);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    if (parseFloat(s.opacity || '1') < 0.05) return false;
    const r = e.getBoundingClientRect();
    return r.width > 2 && r.height > 2;
  };
  const dlg = [...document.querySelectorAll('[role=dialog],[id*=Dialog]')]
      .filter(vis).filter((d) => /ok/i.test(d.innerText || ''))[0];
  if (!dlg) return 'none';
  const cands = [...dlg.querySelectorAll('button,[role=button]')].filter(vis)
      .filter((b) => !b.disabled)
      .filter((b) => /^\s*(ok|close|continue|done)\s*$/i
          .test(((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')).trim()));
  if (!cands.length) return 'blocked';
  const ok = cands[0];
  const r = ok.getBoundingClientRect();
  const o = {bubbles:true, cancelable:true, clientX:r.x + r.width / 2,
             clientY:r.y + r.height / 2, button:0};
  for (const t of ['pointerdown','mousedown','pointerup','mouseup','click'])
    ok.dispatchEvent(new MouseEvent(t, o));
  if (ok.click) ok.click();
  return 'ok';
})()
"""
        for _ in range(12):
            try:
                self.js(click_ok)
            except Exception:
                pass
            time.sleep(0.3)
            try:
                if not int(self.js(_OK_DIALOG_JS) or 0):
                    return ""
            except Exception:
                pass
        try:
            self.key("Escape", "Escape", 27)
            time.sleep(0.5)
            if not int(self.js(_OK_DIALOG_JS) or 0):
                return ""
        except Exception:
            pass
        return "弹窗还开着"

    def dialog_open(self) -> bool:
        """浏览器是不是弹了「是否离开网站？」这类原生对话框。"""
        try:
            for ev in reversed(getattr(self, "events", []) or []):
                if ev.get("method") == "Page.javascriptDialogOpening":
                    return True
        except Exception:
            pass
        return False

    def dismiss_dialog(self) -> bool:
        """把那个对话框按「取消」关掉（留在原页）。"""
        if not self.dialog_open():
            return False
        try:
            self.ws.call("Page.handleJavaScriptDialog", {"accept": False})
        except Exception:
            return False
        return True

    def wait_dialog(self, timeout: float = 1.5, interval: float = 0.15) -> bool:
        """点完可能跳页的按钮后，等一小会看有没有弹「是否离开网站？」。"""
        end = time.time() + timeout
        while time.time() < end:
            if self.dialog_open():
                return True
            time.sleep(interval)
        return False

    def on_overview(self) -> bool:
        """当前是否停在 Pearson 的「作业总览」页。"""
        return "OverviewHomework" in self.top_href()

    def resume_from_overview(self) -> bool:
        """被踢回作业总览页时，点那颗 Resume 回到播放器。"""
        if not self.on_overview():
            return False
        js = r"""
        (() => {
          const el = [...document.querySelectorAll('button, a, input[type=button]')]
            .filter((e) => /^\s*resume\s*$/i.test(((e.innerText || e.value) || '').trim()))[0];
          if (!el) return 'no';
          const r = el.getBoundingClientRect();
          const o = { bubbles: true, cancelable: true,
                      clientX: r.x + 4, clientY: r.y + r.height / 2, button: 0 };
          ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach((t) => {
            el.dispatchEvent(t.indexOf('pointer') === 0 ? new PointerEvent(t, o) : new MouseEvent(t, o));
          });
          return 'ok';
        })()
        """
        try:
            return self.top_js(js) == "ok"
        except Exception:
            return False

    def page_info(self) -> dict:
        """题号 / 总题数——这些在外层页面里，不在播放器那层 iframe。"""
        try:
            r = self.ws.call("Runtime.evaluate",
                          {"expression": _PAGE_INFO_JS, "returnByValue": True},
                          timeout=10)
        except Exception:
            return {}
        return r.get("result", {}).get("value") or {}

    def reopen(self):
        """页面被关掉时，用最后记住的地址在新标签里重开，并连上去。"""
        url = getattr(self, "last_url", "") or ""
        if not url.startswith("http"):
            raise CDPError("不知道原来的地址，开不回来")
        port = getattr(self, "port", 9222)
        target = "http://127.0.0.1:%d/json/new?%s" % (
            port, urllib.parse.quote(url, safe=""))
        req = urllib.request.Request(target, method="PUT")
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                tab = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            raise CDPError("重开标签失败：%s" % str(e)[:60])
        self.ws = CDP(tab["webSocketDebuggerUrl"])
        self.ws.call("Page.enable")
        self.ws.call("Runtime.enable")
        self.ctx = None
        self.player_frame = ""
        # 新标签要 8–12 秒才把播放器 iframe 建好，等它真能读到题号再返回
        end = time.time() + 20.0
        while time.time() < end:
            time.sleep(1.0)
            self.ctx = None
            self.player_frame = ""
            try:
                if (self.state() or {}).get("qno"):
                    return self
            except Exception:
                continue
        raise CDPError("重开的页面一直没进到题目页")

    def capture_el(self, expr: str):
        """把 expr 选中的元素截成 PNG base64（不带 data: 前缀）。

        作图区是 `div.xygraph`（SVG 渲染），DOM 里拿不到像素，
        所以按元素 objectId → contentQuads → 截图裁剪。
        """
        for attempt in (0, 1):
            try:
                r = self.js_object(expr)
            except Exception:
                if attempt:
                    return None
                continue
            oid = (r.get("result") or {}).get("objectId")
            if not oid:
                return None
            try:
                q = self.ws.call("DOM.getContentQuads", {"objectId": oid}, timeout=15)
            except Exception:
                return None
            quads = q.get("quads") or []
            if not quads:
                return None
            xs = quads[0][0::2]
            ys = quads[0][1::2]
            clip = {"x": min(xs), "y": min(ys),
                    "width": max(1.0, max(xs) - min(xs)),
                    "height": max(1.0, max(ys) - min(ys)), "scale": 2}
            try:
                raw = self.ws.call("Page.captureScreenshot",
                                {"format": "png", "clip": clip}, timeout=20)
            except Exception:
                return None
            return raw.get("data")
        return None

    def capture_graph(self):
        """截题目给的那张图（`div.xygraph`）——图是 SVG 时模型本来根本看不到。"""
        expr = r"""
        (() => {
          const vis = (e) => { const r = e.getBoundingClientRect();
            return r.width > 40 && r.height > 40 && e.offsetParent !== null; };
          return [...document.querySelectorAll('div.xygraph')].filter(vis)[0] || null;
        })()
        """
        try:
            return self.capture_el(expr)
        except Exception:
            return None

    def capture_pic(self, idx: int = 0):
        """把本题里第 idx 张可见 canvas/img 截成 PNG base64。"""
        expr = r"""
        (() => {
          const vis = (e) => { const r = e.getBoundingClientRect();
            return r.width > 20 && r.height > 20 && e.offsetParent !== null; };
          const list = [...document.querySelectorAll('canvas, img')].filter((e) => {
            if (!vis(e)) return false;
            const r = e.getBoundingClientRect();
            return r.width >= 80 && r.height >= 60;
          });
          return list[%d] || null;
        })()
        """ % idx
        try:
            return self.capture_el(expr)
        except Exception:
            return None

    def field_text(self, field_id: str) -> str:
        """读编辑器的真实内容。

        2026-11-28 真页面踩到的坑：这个框的 `innerText` 会有**两份**渲染
        （实测 `"2\\n2"`），再加上 aria-label 的 `"2"`，旧代码把它们拼起来
        得到 `"2 2 2"`，归一化后变成 `"222"` —— 于是「把 2 填进去」永远被判成
        「没填进去」，一题能耗 20 多秒、最后还是跳过。
        （帕秋莉：同一个数抄了三遍，谁看都觉得是另一个数。）

        所以只取**一个**权威来源，按可信度排：朗读文本 → 渲染层 → innerText。
        """
        js = ("(() => { const e = document.getElementById(%s); if (!e) return '';"
              " const isPh = (s) => !s || /enter your response|nothing/i.test(s);"
              " const lab = e.querySelector('.eqAccessibleLabel');"
              " const a = lab ? (lab.textContent || '').replace(/\\s+/g, ' ').trim() : '';"
              " if (!isPh(a)) return a;"
              " const doc = e.querySelector('.eqDocument');"
              " const d = doc ? (doc.textContent || '').replace(/\\s+/g, ' ').trim() : '';"
              " if (!isPh(d)) return d;"
              " return (a || d || (e.innerText || '').replace(/\\s+/g, ' ').trim()); })()"
              ) % json.dumps(field_id)
        try:
            return str(self.js(js) or "")
        except Exception:
            return ""

    def field_label(self, field_id: str) -> str:
        return self.js("(document.getElementById(%s) || {}).getAttribute && "
                       "document.getElementById(%s).getAttribute('aria-label') || ''"
                       % (json.dumps(field_id), json.dumps(field_id))) or ""


# ======================================================================
# 以下 JS 常量学自《作业侠客》hwai.py（原样移植，只补中文注释）。
# 分工：
#   _WARN_JS          「没点 Check 就要离开」警告框 → 一律点 No 留下
#   _PAGE_INFO_JS     外层页面的题号 / 总题数 / 有没有 › 
#   _FEEDBACK_NEXT_JS 判分框里那颗「Next question」（做完一题后唯一能走的按钮）
#   _FEEDBACK_VIS_JS  判分框还开着吗
#   _INLINE_NEXT_JS   播放器里不会整页跳走的「下一题」
#   _NEXT_ARROW_JS    标题栏的 ›
#   _NEXT_BTN_JS      播放器自己的 button.btnNext
#   _OK_DIALOG_JS     数一数「有 OK 按钮的弹窗」还有几个
# ======================================================================
_VIS_FN = r"""
  const vis = (e) => {
    if (!e.getClientRects().length) return false;
    const s = getComputedStyle(e);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    if (parseFloat(s.opacity || '1') < 0.05) return false;
    const r = e.getBoundingClientRect();
    return r.width > 2 && r.height > 2;
  };
"""

_WARN_JS = r"""(() => {
  const vis = (e) => {
    if (!e.getClientRects().length) return false;
    const s = getComputedStyle(e);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    const r = e.getBoundingClientRect();
    return r.width > 2 && r.height > 2;
  };
  // 注意：不能用 `.pop()` 取最后一个匹配的容器 —— dijit 弹窗的内容区
  // `dijitDialogPaneContent` 也含这句话、也匹配 `[class*=Dialog]`，
  // 但它**没有按钮**，pop 到它就永远点不动（我们 2026-11-28 也踩过同一个坑）。
  // 改成：按文档顺序找第一个「既有这句话、又有 No 按钮」的容器。
  const cands = [...document.querySelectorAll('[role=dialog], .dijitDialog, [class*=Dialog]')]
      .filter(vis).filter((e) => /will not receive any credit|without checking your answer/i
                                   .test(e.innerText || ''));
  if (!cands.length) return 'no';
  for (const dlg of cands) {
    const b = [...dlg.querySelectorAll('button')].filter(vis)
        .find((x) => /^(no|cancel|取消|否)$/i.test(((x.innerText || '').trim()));
    if (!b) continue;
    const r = b.getBoundingClientRect();
    const o = { bubbles: true, cancelable: true, clientX: r.x + r.width / 2,
                clientY: r.y + r.height / 2, button: 0 };
    for (const t of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'])
      b.dispatchEvent(new MouseEvent(t, o));
    return 'dismissed';
  }
  return 'found';
})()"""

_PAGE_INFO_JS = r"""
(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2; };
  const clean = (s) => (s || '').replace(/\u200b/g, '').replace(/[ \t]+/g, ' ').trim();
  const num = (s) => { const m = (s || '').match(/\bQuestion\s+(\d+)/i); return m ? +m[1] : null; };
  const head = clean([...document.querySelectorAll('header, [class*=header], [class*=Header], [class*=nav]')]
      .filter(vis).map((e) => e.innerText || '').join(' '));
  let qnum = num(head);
  const items = [...document.querySelectorAll('a, li, [role=link]')].filter(vis)
      .map((e) => ({ n: num(clean(e.innerText).slice(0, 40)),
                     cur: /current|active|selected/i.test(e.className || '') }));
  const nums = items.filter((i) => i.n !== null);
  const qmax = nums.length ? Math.max.apply(null, nums.map((i) => i.n)) : null;
  if (qnum === null) {
    const cur = nums.find((i) => i.cur);
    if (cur) qnum = cur.n;
  }
  if (qnum === null) qnum = num(clean(document.body.innerText || '').slice(0, 600));
  const arrows = [...document.querySelectorAll('a, button, [role=button]')].filter(vis)
      .filter((b) => /^[›»〉>]$/.test(clean(b.innerText))
                     || /next question/i.test(b.getAttribute('aria-label') || ''));
  const nextArrow = arrows.find((b) => !b.disabled
      && b.getAttribute('aria-disabled') !== 'true'
      && !/disabled/i.test(b.className || ''));
  return { qnum: qnum, qmax: qmax, hasNextQ: !!nextArrow };
})()
"""

_FEEDBACK_NEXT_JS = r"""(() => {
  const vis = (e) => {
    if (!e.getClientRects().length) return false;
    const s = getComputedStyle(e);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    if (parseFloat(s.opacity || '1') < 0.05) return false;
    const r = e.getBoundingClientRect();
    return r.width > 2 && r.height > 2;
  };
  // 只认 <button>：Pearson 页脚那个「Next question」是 <a href>，点了会整页跳走。
  // 做完一题后标题栏那颗 › 是 disabled，也不会被这里选中。
  const hit = [...document.querySelectorAll('button')].filter(vis).filter((b) => {
    if (b.disabled || b.getAttribute('aria-disabled') === 'true') return false;
    return /^(next question|next)$/i.test(((b.innerText || b.value || '') + '').trim());
  });
  const inFb = hit.filter((b) => b.closest('.feedbackDialog, [class*=feedbackDialog], [role=dialog]')
                             || /btnOnly/.test(String(b.className || '')));
  const b = inFb[inFb.length - 1] || null;
  if (!b) return 'no';
  const r = b.getBoundingClientRect();
  const o = {bubbles: true, cancelable: true, clientX: r.x + r.width / 2,
             clientY: r.y + r.height / 2, button: 0};
  for (const t of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'])
    b.dispatchEvent(new MouseEvent(t, o));
  return 'ok';
})()"""

_FEEDBACK_VIS_JS = r"""(() => {
  const vis = (e) => {
    if (!e.getClientRects().length) return false;
    const s = getComputedStyle(e);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    if (parseFloat(s.opacity || '1') < 0.05) return false;
    const r = e.getBoundingClientRect();
    return r.width > 2 && r.height > 2;
  };
  return [...document.querySelectorAll('.feedbackDialog, [class*=feedbackDialog], [id*=FeedbackMessage]')]
      .some(vis);
})()"""

_INLINE_NEXT_JS = r"""(() => {
  const vis = (e) => { const r = e.getBoundingClientRect();
                      return r.width > 2 && r.height > 2; };
  const bad = /try again|previous|back|上一/i;
  const safeHref = (e) => {
    if (e.tagName !== 'A') return true;
    const h = e.getAttribute('href') || '';
    return !h || h.charAt(0) === '#' || /^javascript:/i.test(h);
  };
  const cands = [...document.querySelectorAll('a, button, [role=button]')].filter(vis)
    .filter(safeHref)
    .filter((e) => !e.disabled && e.getAttribute('aria-disabled') !== 'true'
                   && !/disabled/i.test(String(e.className || '')))
    .filter((e) => !bad.test((e.innerText || '') + ' ' + (e.getAttribute('aria-label') || '')));
  const hit = cands.find((e) => /next question/i.test(
      (e.getAttribute('aria-label') || '') + ' ' + (e.getAttribute('title') || '')))
      || cands.find((e) => /next/i.test(String(e.className || '')))
      || cands.find((e) => /^[›»>]$/.test((e.innerText || '').trim()));
  if (!hit) return 'no';
  const r = hit.getBoundingClientRect();
  const o = {bubbles:true, cancelable:true, clientX:r.x + r.width / 2,
             clientY:r.y + r.height / 2, button:0};
  for (const t of ['pointerdown','mousedown','pointerup','mouseup','click'])
    hit.dispatchEvent(new MouseEvent(t, o));
  return 'ok';
})()"""

_NEXT_ARROW_JS = r"""(() => {
  const vis = (e) => { const r = e.getBoundingClientRect();
                      return r.width > 2 && r.height > 2; };
  const bad = /try again|previous|back|上一/i;
  const cands = [...document.querySelectorAll('button, a, [role=button]')].filter(vis)
    .filter((e) => !bad.test((e.innerText || '') + ' ' + (e.getAttribute('aria-label') || '')))
    .filter((e) => !e.disabled && e.getAttribute('aria-disabled') !== 'true'
                   && !/disabled/i.test(String(e.className || '')));
  let hit = cands.find((e) => /next question/i.test(
      (e.getAttribute('aria-label') || '') + ' ' + (e.getAttribute('title') || '')));
  if (!hit) hit = cands.find((e) => /next/i.test((e.className || '').toString()));
  if (!hit) hit = cands.find((e) => /^[›»>]$/.test((e.innerText || '').trim()));
  if (!hit) return 'no';
  const r = hit.getBoundingClientRect();
  const o = {bubbles:true, cancelable:true, clientX:r.x + r.width / 2,
             clientY:r.y + r.height / 2, button:0};
  for (const t of ['pointerdown','mousedown','pointerup','mouseup','click'])
    hit.dispatchEvent(new MouseEvent(t, o));
  return 'ok';
})()"""

_NEXT_BTN_JS = r"""(() => {
  const b = document.querySelector('button.btnNext, button[aria-label="Next question"]');
  if (!b) return 'no';
  if (b.disabled || b.getAttribute('aria-disabled') === 'true') return 'disabled';
  const r = b.getBoundingClientRect();
  const o = { bubbles: true, cancelable: true, clientX: r.x + r.width / 2,
              clientY: r.y + r.height / 2, button: 0 };
  for (const t of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'])
    b.dispatchEvent(new MouseEvent(t, o));
  return 'ok';
})()"""

_OK_DIALOG_JS = r"""
(() => {
  const vis = (e) => {
    if (!e.getClientRects().length) return false;
    const s = getComputedStyle(e);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    if (parseFloat(s.opacity || '1') < 0.05) return false;
    const r = e.getBoundingClientRect();
    return r.width > 2 && r.height > 2;
  };
  const dl = [...document.querySelectorAll('[role=dialog],[id*=Dialog]')].filter(vis)
      .filter((d) => [...d.querySelectorAll('button')].some(
          (b) => /^\s*ok\s*$/i.test((b.innerText || '').trim())));
  return dl.length;
})()
"""
