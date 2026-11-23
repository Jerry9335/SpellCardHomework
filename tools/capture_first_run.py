# -*- coding: utf-8 -*-
"""本地截图：首次安装契约 + 新手引导（仅开发/验收用）。"""
from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ.setdefault("SHINICHI_CONFIG_DIR", os.path.join(HERE, ".test_config_onboarding"))
sys.path.insert(0, ROOT)

import tkinter as tk
from PIL import ImageGrab

from app import App

SHOTS = os.path.join(ROOT, "tools", "shots")


def _grab_widget(win, name: str) -> None:
    win.update_idletasks()
    win.update()
    time.sleep(0.35)
    x, y = win.winfo_rootx(), win.winfo_rooty()
    w, h = win.winfo_width(), win.winfo_height()
    im = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    im.save(os.path.join(SHOTS, name))
    print("saved", name, im.size)


def main() -> None:
    os.makedirs(SHOTS, exist_ok=True)
    root = tk.Tk()
    root.withdraw()
    app = App(root)
    root.deiconify()
    root.lift()
    root.update_idletasks()
    time.sleep(0.5)

    app.start_setup_wizard(start_step=1)
    root.update_idletasks()
    time.sleep(0.4)
    wiz = app._setup_win
    _grab_widget(wiz, "impl_setup_1_provider.png")
    wiz._toggle_more()
    _grab_widget(wiz, "impl_setup_1_more.png")
    wiz._show_step(2)
    _grab_widget(wiz, "impl_setup_2_key.png")
    wiz._show_step(3)
    _grab_widget(wiz, "impl_setup_3_models.png")
    try:
        wiz.grab_release()
    except Exception:
        pass
    wiz.destroy()
    app._setup_win = None
    root.update_idletasks()
    root.update()
    root.deiconify()
    root.lift()
    root.focus_force()
    time.sleep(0.6)

    app.open_onboarding(manual=True, start_step=1)
    root.update_idletasks()
    time.sleep(0.6)
    ob = app._onboarding_win
    _grab_widget(ob, "impl_onboarding_1_main.png")
    ob._show_step(4)
    _grab_widget(ob, "impl_onboarding_4_auto.png")
    ob._show_step(6)
    _grab_widget(ob, "impl_onboarding_6_settings.png")
    try:
        ob.grab_release()
    except Exception:
        pass
    ob.destroy()
    app._onboarding_win = None

    # 设置里的“引路与契约”入口
    app._open_settings()
    root.update_idletasks()
    time.sleep(0.5)
    sett = app._settings_win
    canvases = []
    def _find_canvas(w):
        for c in w.winfo_children():
            if isinstance(c, tk.Canvas):
                canvases.append(c)
            _find_canvas(c)
    _find_canvas(sett)
    for c in canvases:
        try:
            c.yview_moveto(1.0)
        except Exception:
            pass
    _grab_widget(sett, "impl_settings_reopen.png")
    sett.destroy()
    app._settings_win = None

    # 关于程序：确认版本号
    app._about_app()
    root.update_idletasks()
    time.sleep(0.6)
    about = None
    for w in root.winfo_children():
        try:
            if isinstance(w, tk.Toplevel) and w.title() == "关于程序":
                about = w
                break
        except Exception:
            pass
    if about is not None:
        _grab_widget(about, "impl_about_version.png")

    root.destroy()
    print("DONE")


if __name__ == "__main__":
    main()
