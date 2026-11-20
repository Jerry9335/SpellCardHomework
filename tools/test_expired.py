"""试用到期：启动必须弹授权窗口；关掉窗口程序必须退出。"""
import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from modules import capture, license as lic  # noqa: E402

capture.make_dpi_aware()
cfg = tempfile.mkdtemp(prefix="sch_expired_")
os.makedirs(cfg, exist_ok=True)
now = int(time.time())
first = now - 6 * 86400
last = now - 60
data = {"first": first, "last": last, "runs": 2,
        "sig": lic._trial_sig(first, last, 2)}
with open(os.path.join(cfg, "trial.json"), "w", encoding="utf-8") as f:
    json.dump(data, f)

env = dict(os.environ)
env["SHINICHI_CONFIG_DIR"] = cfg
pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
app_path = os.path.join(ROOT, "app.pyw")
proc = subprocess.Popen([pyw, app_path], cwd=ROOT, env=env)
time.sleep(5)

wins = [w for w in capture.list_windows(include_own=True) if w.title.strip() in
        ("符卡作业簿", "博麗神社 · 结界许可") and w.pid == proc.pid]
titles = [w.title for w in wins]
print("到期启动窗口:", titles)
assert "博麗神社 · 结界许可" in titles, "到期没有弹授权窗口"
assert "符卡作业簿" not in titles, "到期却进了主界面"
capture.grab(next(w for w in wins if "许可" in w.title), "window").image.save(
    os.path.join(HERE, "shots", "expired_boot.png"))

# 关掉授权窗口 -> 程序应退出
dlg = next(w for w in wins if "许可" in w.title)
user32 = ctypes.windll.user32
WM_CLOSE = 0x0010
user32.PostMessageW(dlg.hwnd, WM_CLOSE, 0, 0)
time.sleep(3)
print("窗口关闭后进程退出:", proc.poll() is not None)
assert proc.poll() is not None, "关闭授权窗口后程序没有退出"

# 在进程内验证：过期状态下输入正确激活码 -> 放行
os.environ["SHINICHI_CONFIG_DIR"] = tempfile.mkdtemp(prefix="sch_act_")
import tkinter as tk

import app as appmod

root = tk.Tk()
root.withdraw()
sys.path.insert(0, ROOT)
from modules import license as lic2, license_sign as signer2

machine = lic2.machine_code()
good = signer2.make_code(machine, days=0)
print("测试用激活码:", good)


def fill_and_activate() -> None:
    for top in root.winfo_children():
        if isinstance(top, tk.Toplevel) and "结界许可" in top.title():
            def walk(w):
                for c in w.winfo_children():
                    try:
                        if isinstance(c, tk.Entry):
                            c.insert(0, good)
                        if isinstance(c, tk.Button) and c.cget("text") == "解开结界":
                            c.invoke()
                            return True
                    except Exception:
                        pass
                    if walk(c):
                        return True
                return False
            walk(top)
            return


root.after(900, fill_and_activate)
ok = appmod.show_activation(root, "灵梦：五天试用已经结束，需要激活码。先拿一张许可来吧。")
print("输入激活码后窗口返回:", ok, "许可状态:", lic2.status()[0])
root.destroy()
