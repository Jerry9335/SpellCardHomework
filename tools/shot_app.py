"""启动真实窗口并截图，用于检查界面布局。"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from modules import capture

capture.make_dpi_aware()
shots = os.path.join(HERE, "shots")
os.makedirs(shots, exist_ok=True)

pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
if not os.path.exists(pyw):
    pyw = sys.executable

env = os.environ.copy()
env["SHINICHI_CONFIG_DIR"] = os.path.join(shots, ".cfg")

proc = subprocess.Popen([pyw, "app.pyw"], cwd=ROOT, env=env)

win = None
for _ in range(80):
    time.sleep(0.25)
    wins = capture.list_windows()
    win = next((w for w in wins if w.pid == proc.pid and w.title.strip()), None)
    if win:
        break

if not win:
    print("没有等到窗口出现，进程状态:", proc.poll())
    for w in capture.list_windows():
        print("  window:", w.pid, w.title[:60])
    proc.terminate()
    sys.exit(1)

print("window:", win.title, win.rect)
time.sleep(1.2)
capture.bring_to_front(win.hwnd)
time.sleep(0.7)

out = os.path.join(shots, "app_ui.png")
capture.grab(win, "screen").image.save(out)
print("saved", out)

proc.terminate()
try:
    proc.wait(timeout=5)
except Exception:
    proc.kill()
