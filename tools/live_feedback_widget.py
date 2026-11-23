import json
import sys

sys.path.insert(0, ".")
from modules.web import WebPlayer  # noqa: E402

d = WebPlayer(port=9222).connect()
js = """(() => {
  const w = dijit.byId('xl_player_dialogs_FeedbackMessage_38');
  if (!w) return {err: 'no widget'};
  const own = Object.keys(w).filter(k => /ok|execute|next|part|check|submit|show|hide/i.test(k));
  let src = '', call = '';
  try { src = String(w.onExecute || '').slice(0, 1200); } catch (e) { src = 'ERR ' + e; }
  try { call = String(w.okClicked || ''); } catch (e) { call = 'ERR ' + e; }
  return {own, onExecute: src, okClicked: call,
          proto: Object.getOwnPropertyNames(Object.getPrototypeOf(w)).filter(k => /ok|execute|next|part|check|submit|show|hide/i.test(k))};
})()"""
print(json.dumps(d.eval_main(js), ensure_ascii=False, indent=1)[:5000])
