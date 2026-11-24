"""检查安装包的用户许可协议页：/CURRENTUSER 跳过模式对话框，翻到许可页截图。"""
import ctypes
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from modules import capture  # noqa: E402

capture.make_dpi_aware()
setup = os.path.join(ROOT, "installer", "Output", "SpellCardHomework-Setup-1.0.6-rc.04.exe")
proc = subprocess.Popen([setup, "/CURRENTUSER", "/LANG=chinesesimplified"])

user32 = ctypes.windll.user32
VK_RETURN = 0x0D
KEYEVENTF_KEYUP = 0x0002


def press_enter() -> None:
    user32.keybd_event(VK_RETURN, 0, 0, 0)
    user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)


def find_window():
    for w in capture.list_windows(include_own=True):
        t = w.title.strip()
        if any(k in t for k in ("安装", "Setup", "符卡")):
            return w
    return None


time.sleep(4)
w = find_window()
print("welcome:", w.title if w else None, (w.w, w.h) if w else None)
if w:
    user32.SetForegroundWindow(w.hwnd)
    time.sleep(0.4)
    press_enter()          # Welcome -> License
    time.sleep(2)
    w2 = find_window()
    print("license:", w2.title if w2 else None, (w2.w, w2.h) if w2 else None)
    if w2:
        capture.grab(w2, "window").image.save(os.path.join(HERE, "shots", "installer_eula.png"))
        print("saved installer_eula.png")
        user32.PostMessageW(w2.hwnd, 0x0010, 0, 0)
time.sleep(2)
try:
    proc.kill()
except Exception:
    pass
