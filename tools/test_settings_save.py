"""设置页保存测试：更新渠道 / 自定义间隔 / 退治 Toast 开关。"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import tkinter as tk
import tkinter.ttk as ttk

import app as appmod

root = tk.Tk()
a = appmod.App(root)
root.withdraw()
a._open_settings()
for _ in range(10):
    root.update()
    time.sleep(0.05)


def walk(w):
    for c in w.winfo_children():
        yield c
        yield from walk(c)


win = next(x for x in root.winfo_children()
           if isinstance(x, tk.Toplevel) and "设置" in x.title())
widgets = list(walk(win))
combos = [w for w in widgets if isinstance(w, ttk.Combobox)]
chan = next(c for c in combos if "自动（Gitee 优先）" in c.cget("values"))
chan.set("仅 GitHub（外界神社）")
chan.event_generate("<<ComboboxSelected>>")

intv = next(c for c in combos if "5 小时" in c.cget("values"))
intv.set("自定义")
intv.event_generate("<<ComboboxSelected>>")

spin = next(s for s in widgets if isinstance(s, ttk.Spinbox)
            and str(s.cget("from")) == "1" and str(s.cget("to")) == "720")
spin.delete(0, "end")
spin.insert(0, "7")

auto_cb = next(c for c in widgets
               if isinstance(c, ttk.Checkbutton) and c.cget("text") == "退治")
if auto_cb.instate(["selected"]):
    auto_cb.invoke()

save_btn = next(b for b in widgets
                if isinstance(b, ttk.Button) and b.cget("text") == "保存")
save_btn.invoke()
for _ in range(10):
    root.update()
    time.sleep(0.05)

print({k: a.cfg.get(k) for k in (
    "update_channel", "update_interval_hours", "toast_auto")})
assert a.cfg.get("update_channel") == "github"
assert int(a.cfg.get("update_interval_hours") or 0) == 7
assert a.cfg.get("toast_auto") is False
root.destroy()
print("RESULT: PASS")
