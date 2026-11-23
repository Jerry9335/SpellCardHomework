import json
import sys

sys.path.insert(0, ".")
from modules.web import WebPlayer  # noqa: E402

d = WebPlayer(port=9222).connect()
js = """(() => {
  const b = document.getElementById('xl_dijit-bootstrap_Button_522');
  if (!b) return {err: 'no btn'};
  const r = b.getBoundingClientRect();
  const x = r.x + r.width / 2, y = r.y + r.height / 2;
  const stack = document.elementsFromPoint(x, y).slice(0, 10).map(e => ({
    tag: e.tagName, id: e.id, cls: (e.className || '').toString().slice(0, 100),
    pe: getComputedStyle(e).pointerEvents, z: getComputedStyle(e).zIndex,
    text: (e.innerText || '').replace(/\\s+/g, ' ').slice(0, 60),
  }));
  const dlg = document.getElementById('xl_player_dialogs_FeedbackMessage_38');
  return {btn: {x, y}, stack, dlg: {display: getComputedStyle(dlg).display,
          z: getComputedStyle(dlg).zIndex,
          tab: dlg.getAttribute('tabindex')}};
})()"""
print(json.dumps(d.eval_main(js), ensure_ascii=False, indent=1))
