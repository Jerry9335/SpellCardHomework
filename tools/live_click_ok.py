import json
import sys
import time

sys.path.insert(0, ".")
from modules.web import WebPlayer  # noqa: E402

d = WebPlayer(port=9222).connect()
js = """(() => {
  const b = document.getElementById('xl_dijit-bootstrap_Button_522');
  if (!b) return null;
  const r = b.getBoundingClientRect();
  let fx = 0, fy = 0, fe = null;
  try {
    fe = window.frameElement;
    if (fe) { const fr = fe.getBoundingClientRect(); fx = fr.x; fy = fr.y; }
  } catch (e) {}
  return {x: fx + r.x + r.width / 2, y: fy + r.y + r.height / 2,
          bx: r.x, by: r.y, fx, fy,
          frame: fe ? {w: fe.getBoundingClientRect().width, h: fe.getBoundingClientRect().height} : null};
})()"""
pt = d.eval_main(js)
print("pt", pt)
if pt:
    for typ in ("mousePressed", "mouseReleased"):
        d.ws.call("Input.dispatchMouseEvent", {
            "type": typ, "x": pt["x"], "y": pt["y"], "button": "left", "clickCount": 1,
        })
    time.sleep(1.2)
print("kind", d.completion_state().get("kind"))
