"""主世界页面代理：注入到 Pearson 页面里，用真实 DOM / Dojo 操作。"""
from __future__ import annotations

AGENT_JS = r"""
(() => {
  if (window.__SCH_AGENT__) return 'ready';
  const vis = (e) => {
    const r = e.getBoundingClientRect();
    return r.width > 2 && r.height > 2 && getComputedStyle(e).display !== 'none'
           && getComputedStyle(e).visibility !== 'hidden';
  };
  const clickEl = (el) => {
    if (!el) return false;
    try { el.scrollIntoView({block: 'center'}); } catch (e) {}
    try { el.focus(); } catch (e) {}
    try { el.click(); return true; } catch (e) {}
    return false;
  };
  const unblock = () => {
    for (const e of document.querySelectorAll('.xlStandbyUnderlay')) {
      try { e.style.pointerEvents = 'none'; } catch (err) {}
    }
  };
  window.__SCH_AGENT__ = {
    ready: true,
    busy() {
      return [...document.querySelectorAll('.xlStandbyUnderlay')].some((e) => {
        if (!vis(e)) return false;
        const o = parseFloat(getComputedStyle(e).opacity || '1');
        return o > 0.05;
      });
    },
    unblock() { unblock(); return 'ok'; },
    clickText(pattern) {
      let re;
      try { re = new RegExp(pattern, 'i'); } catch (e) { return 'bad-regex'; }
      const bs = [...document.querySelectorAll('button, a, [role=button]')]
        .filter((b) => vis(b) && !b.disabled && b.getAttribute('aria-disabled') !== 'true')
        .filter((b) => [b.innerText, b.getAttribute('aria-label'), b.getAttribute('title')]
          .some((x) => x && re.test(x.trim())));
      if (!bs.length) return 'no';
      const dlgs = bs.filter((b) => b.closest(
        '[id*=Dialog], [class*=Dialog], [class*=feedback], [role=dialog]'));
      const b = (dlgs.length ? dlgs : bs).pop();
      unblock();
      return clickEl(b) ? 'ok' : 'no';
    },
    clickId(id) {
      const el = document.getElementById(id);
      if (!el) return 'no';
      unblock();
      return clickEl(el) ? 'ok' : 'no';
    },
    clickCheck() {
      const bs = [...document.querySelectorAll('button, a, [role=button]')]
        .filter((b) => vis(b) && !b.disabled && b.getAttribute('aria-disabled') !== 'true')
        .filter((b) => /^(check answer|final check)$/i.test((b.innerText || '').trim())
                     || /^(check answer|final check)$/i.test(b.getAttribute('aria-label') || ''));
      if (!bs.length) return 'disabled';
      unblock();
      return clickEl(bs[bs.length - 1]) ? 'ok' : 'no';
    },
    clickNext() {
      const bs = [...document.querySelectorAll('button, a, [role=button]')]
        .filter((b) => vis(b) && !b.disabled)
        .filter((b) => /^(next|next question)$/i.test((b.innerText || '').trim())
                     || /^(next|next question)$/i.test(b.getAttribute('aria-label') || ''));
      if (!bs.length) return 'no';
      unblock();
      return clickEl(bs[bs.length - 1]) ? 'ok' : 'no';
    },
    pickRadio(id) { return this.clickId(id); },
    graphWidget() {
      const el = document.querySelector('.graphControl .xygraph') ||
                 document.querySelector('.xygraph');
      if (!el) return null;
      const gw = window.dijit ? dijit.byId(el.id) : null;
      return gw || null;
    }
  };
  return 'ready';
})()
"""
