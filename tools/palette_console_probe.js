// 公式调色板按钮逐个点击探针（v3：支持 shadow DOM + 诊断）
// 用法：粘到 DevTools Console 回车。页面停在有填空的题目上即可。
// 安全：只在空输入框里操作；每个按钮点完立刻清空；弹窗只按 Cancel；不点 Check/Submit/Save。
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const vis = (e) => {
    if (!e) return false;
    const r = e.getBoundingClientRect();
    return r.width > 2 && r.height > 2;
  };

  // 1) 收集所有可访问的根：document + 同源 iframe + shadow root
  const roots = [];
  (function walkDoc(d) {
    if (!d) return;
    roots.push(d);
    d.querySelectorAll('iframe').forEach((f) => {
      try { if (f.contentDocument) walkDoc(f.contentDocument); } catch (e) {}
    });
  })(document);
  const shadowHosts = [];
  (function walkShadow(root) {
    root.querySelectorAll('*').forEach((el) => {
      if (el.shadowRoot) {
        shadowHosts.push(el.tagName);
        roots.push(el.shadowRoot);
        walkShadow(el.shadowRoot);
      }
    });
  })(document);

  const FIELD_SEL = ['span.eqEditor', '.eqEditor', '[class*="eqEditor"]', '[id*="eqEditor"]'];
  const PAL_SEL = ['div.xlInlineMathPalette', 'div.xlKeyboardDialog',
                   '[class*=KeyboardDialog]', '[data-dojo-attach-point="paletteNode"]'];

  const findFields = (onlyVisible) => {
    const out = [];
    for (const sel of FIELD_SEL) {
      for (const r of roots) {
        for (const f of r.querySelectorAll(sel)) {
          if (onlyVisible && !vis(f)) continue;
          if (!out.includes(f)) out.push(f);
        }
      }
      if (out.length) break;
    }
    return out;
  };
  const findPals = (onlyVisible) => {
    const out = [];
    for (const sel of PAL_SEL) {
      for (const r of roots) {
        for (const p of r.querySelectorAll(sel)) {
          if (onlyVisible && !vis(p)) continue;
          out.push(p);
        }
      }
      if (out.length) break;
    }
    return out;
  };

  let fields = findFields(true);
  if (!fields.length) fields = findFields(false);

  const diag = () => {
    const perDoc = [];
    for (const r of roots) {
      const n = r.querySelectorAll('.eqEditor, span.eqEditor, [class*=eqEditor]').length;
      if (n) perDoc.push(n);
    }
    const ifr = [...document.querySelectorAll('iframe')].map((f) => {
      try { return (f.src || '').slice(0, 60) + (f.contentDocument ? ' [same-origin]' : ' [cross-origin]'); }
      catch (e) { return '(iframe)'; }
    });
    return { roots: roots.length, shadowHosts: shadowHosts.slice(0, 5),
             eqCounts: perDoc, iframes: ifr.slice(0, 6) };
  };
  if (!fields.length) {
    console.log('NO FIELD diag', diag());
    return 'NO FIELD ' + JSON.stringify(diag());
  }

  const empty = fields.filter((f) => !(f.innerText || f.textContent || '').trim());
  const fld = empty[0] || fields[0];
  if ((fld.innerText || fld.textContent || '').trim()) return 'FIELD BUSY';
  const fdoc = fld.ownerDocument;
  const inner = () => ((fld.innerText || fld.textContent || '') + '').trim();

  const realClick = (el) => {
    const r = el.getBoundingClientRect();
    const o = { bubbles: true, cancelable: true, clientX: r.x + 3,
                clientY: r.y + r.height / 2, button: 0 };
    ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(
      (t) => el.dispatchEvent(new MouseEvent(t, o)));
    try { el.focus(); } catch (e) {}
    const inp = el.querySelector && el.querySelector('input');
    if (inp) { try { inp.focus(); } catch (e) {} }
  };

  // 2) 打开调色板（没有就点一下输入框）
  let pals = findPals(true);
  if (!pals.length) {
    realClick(fld);
    await sleep(700);
    pals = findPals(true);
  }
  let hiddenMode = false;
  if (!pals.length) { pals = findPals(false); hiddenMode = pals.length > 0; }
  if (!pals.length) {
    console.log('NO PALETTE diag', diag());
    return 'NO PALETTE ' + JSON.stringify(diag());
  }
  const pal = pals[pals.length - 1];
  const palDoc = pal.ownerDocument || fdoc;
  if (hiddenMode) {
    let n = pal;
    for (let i = 0; i < 3 && n; i++, n = n.parentElement || (n.host)) {
      try {
        n.classList.remove('hidden');
        n.style.display = '';
        n.style.visibility = 'visible';
      } catch (e) {}
    }
  }

  // 3) 工具集合（两页）
  const isTool = (b) => /(^|\s)(toolButton|icon[A-Z])/.test(String(b.className || ''));
  const toolsOf = () => [...pal.querySelectorAll('button')].filter(isTool);
  const iconOf = (b) => String(b.className || '').split(/\s+/).find((c) => /^icon/.test(c)) || '';
  const SKIP = new Set(['iconUndo', 'iconRedo', 'iconMoreTools', 'iconLessTools']);
  const moreBtn = () => [...pal.querySelectorAll('button')].filter(vis)
    .find((b) => /more/i.test((b.getAttribute('title') || '') + (b.textContent || '')));
  const lessBtn = () => [...pal.querySelectorAll('button')].filter(vis)
    .find((b) => /^less$/i.test((b.getAttribute('title') || '').trim()));

  const seen = new Set(), tools = [];
  const grab = (onlyVisible) => {
    for (const b of toolsOf()) {
      if (onlyVisible && !vis(b)) continue;
      const ic = iconOf(b);
      if (!ic || SKIP.has(ic) || seen.has(ic)) continue;
      seen.add(ic);
      tools.push({ ic, title: (b.getAttribute('title') || '').trim() });
    }
  };
  grab(!hiddenMode);
  if (!hiddenMode) {
    let tg = moreBtn() || lessBtn();
    if (tg) { tg.click(); await sleep(300); grab(true); }
    tg = moreBtn() || lessBtn();
    if (tg) { tg.click(); await sleep(200); }
  }

  const ensurePal = async () => {
    if (hiddenMode) return;
    if (!findPals(true).length) { realClick(fld); await sleep(450); }
  };
  const dialogOf = () => [...palDoc.querySelectorAll(
      '[role=dialog], [id*=Popup], [id*=Dialog], [class*=Popup], [class*=Dialog]')]
    .filter(vis).filter((p) => p.querySelector('button')).pop() || null;
  const closeDlg = async () => {
    const d = dialogOf();
    if (!d) return;
    const c = [...d.querySelectorAll('button')]
      .find((b) => /^(cancel|close)$/i.test((b.innerText || '').trim()));
    if (c) c.click();
    await sleep(180);
  };
  const clearField = async () => {
    realClick(fld);
    const sel = fdoc.getSelection(), r = fdoc.createRange();
    r.selectNodeContents(fld);
    sel.removeAllRanges();
    sel.addRange(r);
    try { fdoc.execCommand('delete'); } catch (e) {}
    fld.dispatchEvent(new Event('input', { bubbles: true }));
    await sleep(150);
  };

  const results = [];
  for (let idx = 0; idx < tools.length; idx++) {
    const t = tools[idx];
    console.log(`[${idx + 1}/${tools.length}] ${t.ic} ${t.title}`);
    await ensurePal();
    let btn = [...pal.querySelectorAll('button.' + t.ic)].find(vis);
    if (!btn) {
      const tg = moreBtn() || lessBtn();
      if (tg) { tg.click(); await sleep(250); }
      btn = [...pal.querySelectorAll('button.' + t.ic)].find(vis);
    }
    if (!btn) btn = pal.querySelector('button.' + t.ic);
    const before = inner();
    let clicked = false;
    if (btn) { btn.click(); clicked = true; }
    await sleep(450);
    const dlg = dialogOf();
    let cells = 0;
    try {
      if (fld.id) cells = fdoc.querySelectorAll('#' + CSS.escape(fld.id) + ' table.eqMatrix td').length;
    } catch (e) {}
    const after = inner();
    let effect = '无变化';
    if (dlg) effect = '弹窗:' + (dlg.id || dlg.className || '?');
    else if (cells) effect = '插入矩阵(' + cells + '格)';
    else if (after && after !== before) effect = '插入:' + after.replace(/\s+/g, ' ').slice(0, 40);
    else if (!clicked) effect = '按钮找不到';
    results.push({
      icon: t.ic, title: t.title, effect,
      dialog: dlg ? {
        id: dlg.id || '',
        inputs: [...dlg.querySelectorAll('input')].map((i) => i.id || i.className || '?'),
        buttons: [...dlg.querySelectorAll('button')].map((b) => (b.innerText || '').trim()).filter(Boolean),
      } : null,
    });
    if (dlg) await closeDlg();
    await clearField();
    if (inner()) {
      await clearField();
      if (inner()) {
        results.push({ icon: t.ic, title: t.title, effect: '清空失败，已停止', dialog: null });
        break;
      }
    }
  }
  await clearField();
  console.table(results.map((r) => ({ icon: r.icon, title: r.title, effect: r.effect })));
  const json = JSON.stringify(results, null, 2);
  console.log(json);
  try { if (typeof copy === 'function') copy(json); } catch (e) {}
  console.log('DONE ' + results.length + (hiddenMode ? ' (hidden-palette)' : ''));
  return 'DONE ' + results.length;
})()
