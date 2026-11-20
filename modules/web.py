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
import socket
import struct
import time
import urllib.parse
import urllib.request

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
  const scope = dlg || document.body;
  const clean = (s) => (s || '').replace(/\u200b/g, '').replace(/[ \t]+/g, ' ')
                      .replace(/ ?\n ?/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
  const fields = [...scope.querySelectorAll('span.eqEditor')].filter(vis).map((el) => ({
    id: el.id, label: clean(el.getAttribute('aria-label')).slice(0, 120),
    readonly: /true/i.test(el.getAttribute('aria-readonly') || '') }));
  const radiosAll = [...scope.querySelectorAll('input[type=radio]')].filter(vis).map((el) => ({
    id: el.id, label: clean(el.getAttribute('aria-label')).slice(0, 160), checked: !!el.checked,
    disabled: !!el.disabled || /Disabled/.test(el.parentElement ? el.parentElement.className : '') }));
  // 只把「当前小问」的选项给模型/选择用；已答过的旧选项通常 disabled，会打乱字母对应
  const radios = radiosAll.filter((r) => !r.disabled);
  const radiosDisabled = radiosAll.length - radios.length;
  const inputs = [...scope.querySelectorAll('input[type=text], input[type=number], input[type=email]')]
      .filter(vis).filter((el) => !el.closest('span.eqEditor')).map((el) => ({
        id: el.id, label: clean(el.getAttribute('aria-label')).slice(0, 120),
        disabled: !!el.disabled }));
  const checks = [...scope.querySelectorAll('input[type=checkbox]')].filter(vis).map((el) => ({
    id: el.id, label: clean(el.getAttribute('aria-label')).slice(0, 160), checked: !!el.checked,
    disabled: !!el.disabled }));
  const selects = [...scope.querySelectorAll('select')].filter(vis).map((el) => ({
    id: el.id, label: clean(el.getAttribute('aria-label')).slice(0, 120),
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
    id: el.id, label: clean(el.getAttribute('aria-label') || '').slice(0, 200) }));

  return { text: text, qkey: qkey, rect: qrect, part: [partN, partM], fields: fields, radios: radios,
           dropdowns: dropdowns,
           radios_disabled: radiosDisabled, inputs: inputs,
           checks: checks, selects: selects, imgs: imgs,
           hasCheck: btn(/^(check answer|final check)$/i), hasNext: btn(/^(next|next question)$/i),
           inDialog: !!dlg };
})()
"""

_FEEDBACK_JS = r"""
(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2; };
  const good = /\b(well done|fantastic|correct|great|nice work|excellent|way to go|perfect|that'?s right|right answer|you got it)\b/i;
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
        page = (hit or pages or [None])[0]
        if not page:
            raise CDPError("浏览器里没有页面")
        self.ws = CDP(page["webSocketDebuggerUrl"])
        self.ws.call("Page.enable")
        self.ws.call("Runtime.enable")
        self.title = page.get("title", "")
        self.ctx = None
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

    # ---- 读
    def state(self) -> dict:
        return self.js(_STATE_JS) or {}

    def feedback(self) -> str:
        return self.js(_FEEDBACK_JS) or ""

    # ---- 写
    def pick_choice(self, letter: str) -> str:
        letter = (letter or "").strip().upper()[:1]
        if not letter:
            return "no-letter"
        st = self.state()
        pool = st.get("radios", []) + st.get("checks", [])
        cand = [r for r in pool
                if (r.get("label") or "").strip().upper().startswith(letter)]
        if not cand and pool:
            # 选项本身没有字母（如 No / Yes），按 A/B/C 顺序取
            idx = ord(letter) - ord("A")
            if 0 <= idx < len(pool):
                cand = [pool[idx]]
        if not cand:
            return "no-match"
        if not cand:
            return "no-match"
        if cand[0].get("disabled"):
            return "disabled"
        rid = cand[0]["id"]
        rid_js = json.dumps(rid)
        for expr in ("document.getElementById(%s)" % rid_js,
                     "(document.getElementById(%s) || {}).parentElement" % rid_js,
                     "document.querySelector('label[for=' + %s + ']')" % rid_js):
            self.js(_CLICK_JS % ("(%s) || null" % expr))
            time.sleep(0.3)
            st2 = self.state()
            hit = [r for r in (st2.get("radios", []) + st2.get("checks", [])) if r["id"] == rid]
            if hit and hit[0].get("checked"):
                return "ok"
        return "not-checked"

    def pick_multi(self, letters: list[str]) -> str:
        """多选：逐个点，全中才算 ok。"""
        bad = []
        for ch in letters:
            if self.pick_choice(ch) != "ok":
                bad.append(ch)
            time.sleep(0.35)
        return "ok" if not bad else "fail:" + ",".join(bad)

    def leave_prompt(self) -> bool:
        """有没有「Are you sure you want to leave this question?」这种确认框。"""
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
        js = r"""
(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2; };
  const dlgs = [...document.querySelectorAll('[id*=Dialog], [class*=Dialog], [role=dialog], [class*=feedback]')]
      .filter(vis);
  const dlg = dlgs.length ? dlgs[dlgs.length - 1] : null;
  if (!dlg) return false;
  return [...dlg.querySelectorAll('button, a, [role=button]')].some((b) => {
    if (!vis(b)) return false;
    return [b.innerText, b.getAttribute('aria-label'), b.getAttribute('title')]
      .some((x) => x && /^next( question)?$/i.test(x.trim()));
  });
})()
"""
        return bool(self.js(js))

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

    def click_text(self, pattern: str) -> str:
        """按文字 / aria-label / title 点按钮；有弹窗时优先点弹窗里的。"""
        reg = "new RegExp(%s, 'i')" % json.dumps(pattern)
        expr = ("(() => { const bs = [...document.querySelectorAll('button, a, [role=button]')]"
                ".filter((b) => { const r = b.getBoundingClientRect();"
                " if (!(r.width > 2 && r.height > 2)) return false;"
                " return [b.innerText, b.getAttribute('aria-label'), b.getAttribute('title')]"
                ".some((x) => x && " + reg + ".test(x.trim())); });"
                " const d = bs.filter((b) => b.closest("
                "'[id*=Dialog], [class*=Dialog], [class*=feedback], [role=dialog]'));"
                " return (d.length ? d : bs).pop() || null; })()")
        return self.js(_CLICK_JS % ("(%s)" % expr))

    # ---- 矩阵
    def click_matrix(self) -> str:
        expr = ("[...document.querySelectorAll('button.iconMatrix')]"
                ".filter((x) => x.getBoundingClientRect().width > 0)"
                ".sort((a, b) => (b.closest('[id*=ResizableDialog]') ? 1 : 0)"
                " - (a.closest('[id*=ResizableDialog]') ? 1 : 0))[0]")
        return self.js(_CLICK_JS % (f"({expr}) || null"))

    def matrix_popup(self):
        return self.js(r"""
(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2; };
  const pops = [...document.querySelectorAll('[id*=MatrixSizePopup]')]
      .filter((p) => vis(p) && p.querySelectorAll('button').length >= 2);
  if (!pops.length) return null;
  const pop = pops[pops.length - 1];
  const spins = [...pop.querySelectorAll('input')].filter((i) => /NumberSpinner/.test(i.id));
  const ok = [...pop.querySelectorAll('button')]
      .find((b) => (b.innerText || '').trim().toUpperCase() === 'OK');
  return { id: pop.id, spins: spins.map((s) => s.id), ok: ok ? ok.id : '',
           rows: spins[0] ? spins[0].value : '', cols: spins[1] ? spins[1].value : '' };
})()
""")

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

    def fill_matrix(self, field_id: str, rows: int, cols: int, values: list[str]) -> str:
        st = self.matrix_popup()
        if not st:
            self.click_matrix()
            for _ in range(10):
                time.sleep(0.4)
                st = self.matrix_popup()
                if st:
                    break
        if not st:
            return "矩阵面板没弹出来"
        if st.get("spins"):
            if not self.set_spinner(st["spins"][0], rows):
                return f"行数没设成 {rows}"
            if len(st["spins"]) > 1 and not self.set_spinner(st["spins"][1], cols):
                return f"列数没设成 {cols}"
        st = self.matrix_popup()
        if st and st.get("ok"):
            self.js(_CLICK_JS % ("document.getElementById(%s) || null" % json.dumps(st["ok"])))
        time.sleep(1.4)
        n = self.cell_ids(field_id)
        if n != rows * cols:
            self.focus_field(field_id)
            self.clear_field()
            time.sleep(0.5)
            return f"矩阵尺寸没设成（要 {rows}×{cols}，插出来是 {n} 格）"

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

        if not clipboard.copy_text(text):
            return False
        self.key('a', 'KeyA', 65, 2)
        time.sleep(0.08)
        self.key('v', 'KeyV', 86, 2)
        time.sleep(0.45)
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

