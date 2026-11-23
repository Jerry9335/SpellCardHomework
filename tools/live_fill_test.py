import sys
import time

sys.path.insert(0, r"D:\zack\Desktop\Develop\Shinichi-Exercise-Tools")
from modules import latex
from modules.web import WebPlayer

d = WebPlayer(port=9222)
d.connect()

for fid in ("S3", "Decoy1"):
    print("---", fid, d.field_text(fid))
    d.focus_field(fid)
    time.sleep(0.4)
    d.clear_field()
    time.sleep(0.3)
    ok = d.paste_math(latex.to_paste_input("(0, 5/3)"))
    if not ok:
        d.insert_math(latex.to_editor_input("(0, 5/3)"))
    time.sleep(0.8)
    print("paste", ok, "text", repr(d.field_text(fid)))
    s = d.state()
    print("canCheck", s.get("canCheck"), "qno", s.get("qno"), "part", s.get("part"))
    break
