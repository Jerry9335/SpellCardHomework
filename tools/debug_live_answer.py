import json
import sys

sys.path.insert(0, r"D:\zack\Desktop\Develop\Shinichi-Exercise-Tools")
from modules import answer_engine, llm, question_reader, settings, verify_math
from modules.web import WebPlayer

cfg = settings.load()
d = WebPlayer(port=9222)
d.connect()
st = d.state()
print("qno", st.get("qno"), "part", st.get("part"), "canCheck", st.get("canCheck"))
text = st.get("text") or ""
part_n = int((st.get("part") or [0, 0])[0] or 0)
# mirror App._web_focus_text
import re

seg = text
if part_n:
    m = re.search(rf"Part\s+{part_n}\b(.*?)(?=Part\s+{part_n + 1}\b|\Z)", text, re.S | re.I)
    if m:
        seg = m.group(1).strip()
stem = ""
pieces = re.split(r"Part\s+1\b", text, maxsplit=2, flags=re.I)
if len(pieces) >= 3:
    stem = pieces[1].strip()
if part_n == 1 and stem and seg.startswith(stem[:60]):
    seg = seg[len(stem):].lstrip()
focus = f"当前是第 {part_n} 小问，只回答这一小问。\n{stem}\n\n{seg}"
packet = question_reader.build_packet(st, focus)
print("packet keys", packet.keys())
print("text tail:\n", focus[-1500:])
print("hint:", answer_engine._control_hint(packet))
eng = answer_engine.AnswerEngine(lambda m, t=0.7, tag="": "")
msgs = eng._messages(packet, "这是独立作答。请先自己在草稿里算一遍，再只输出 CHOICE / MATRIX / DROPDOWN / VALUE 四行；不要参考其他答案。")
print("messages chars", sum(len(m.get("content", "")) for m in msgs))
raw = llm.chat_stream(
    cfg["base_url"], cfg["api_key"], cfg["model"], msgs,
    temperature=0.7, extra_body=None, timeout=120).text
print("RAW START")
print(raw)
print("RAW END")
print("parsed", json.dumps(verify_math.canonical_value(raw), ensure_ascii=False))
