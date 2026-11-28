"""设置页保存测试：更新渠道 / 退治 Toast 开关（不再有更新间隔）。"""
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
           if isinstance(x, tk.Toplevel)
           and ("设置" in x.title() or "境界設定" in x.title()))
widgets = list(walk(win))
combos = [w for w in widgets if isinstance(w, ttk.Combobox)]
chan = next(c for c in combos if "自动（Gitee 优先）" in c.cget("values"))
chan.set("仅 GitHub（外界神社）")
chan.event_generate("<<ComboboxSelected>>")

assert any(isinstance(c, ttk.Combobox) and "1 小时" in c.cget("values")
           for c in combos), "更新间隔选项应包含默认 1 小时"
assert not any(isinstance(c, ttk.Combobox) and "每次启动" in c.cget("values")
               for c in combos), "更新间隔不应再有每次启动选项"

auto_cb = next(c for c in widgets
               if isinstance(c, ttk.Checkbutton) and c.cget("text") == "退治")
if auto_cb.instate(["selected"]):
    auto_cb.invoke()

save_btn = next(b for b in widgets
                if isinstance(b, (ttk.Button, tk.Button))
                and b.cget("text") in ("保存", "记入卷宗"))
save_btn.invoke()
for _ in range(10):
    root.update()
    time.sleep(0.05)

print({k: a.cfg.get(k) for k in ("update_channel", "toast_auto")})
assert a.cfg.get("update_channel") == "github"
assert a.cfg.get("toast_auto") is False
root.destroy()
print("RESULT: PASS")
