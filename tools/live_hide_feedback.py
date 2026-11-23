import sys
import time

sys.path.insert(0, ".")
from modules.web import WebPlayer  # noqa: E402

d = WebPlayer(port=9222).connect()
print("before", d.completion_state().get("kind"))
print(d.eval_main("""(() => {
  const w = dijit.byId('xl_player_dialogs_FeedbackMessage_38');
  if (!w) return 'no widget';
  try { w.hide(); } catch (e) { return 'err ' + e; }
  const u = document.getElementById('xl_player_dialogs_FeedbackMessage_38_underlay');
  if (u) u.style.display = 'none';
  const el = document.getElementById('xl_player_dialogs_FeedbackMessage_38');
  if (el) { el.style.display = 'none'; el.setAttribute('aria-hidden', 'true'); }
  return 'hidden';
})()"""))
time.sleep(1.5)
print("after", d.completion_state())
s = d.state()
print("qno", s.get("qno"), "part", s.get("part"), "canCheck", s.get("canCheck"))
