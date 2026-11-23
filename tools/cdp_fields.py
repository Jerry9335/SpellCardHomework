import json
import sys

sys.path.insert(0, r"D:\zack\Desktop\Develop\Shinichi-Exercise-Tools")
from modules.web import WebPlayer

d = WebPlayer(port=9222)
d.connect()
expr = r"""
(() => {
  const out = [];
  for (const el of document.querySelectorAll('span.eqEditor')) {
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    out.push({id: el.id, rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
              display: cs.display, visibility: cs.visibility, opacity: cs.opacity,
              aria: el.getAttribute('aria-label'), hidden: el.hidden,
              parent: el.parentElement ? el.parentElement.className : '',
              parentStyle: el.parentElement ? el.parentElement.getAttribute('style') : '',
              text: (el.innerText || '').slice(0, 80)});
  }
  const radios = [...document.querySelectorAll('input[type=radio]')].map(el => ({
    id: el.id, checked: el.checked, disabled: el.disabled,
    rect: [Math.round(el.getBoundingClientRect().x), Math.round(el.getBoundingClientRect().y)],
    label: (el.getAttribute('aria-label') || '').slice(0, 100)}));
  return {url: location.href, fields: out, radios: radios};
})()
"""
print(json.dumps(d.eval_main(expr), ensure_ascii=False, indent=2))
