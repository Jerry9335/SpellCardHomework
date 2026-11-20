"""全屏半透明遮罩，用鼠标拖拽框选题目区域。"""
from __future__ import annotations

import tkinter as tk

from . import capture


def select_region(parent: tk.Misc) -> tuple[int, int, int, int] | None:
    """返回物理像素坐标 (x, y, w, h)；用户按 Esc 或没拖动则返回 None。"""
    vx, vy, vw, vh = capture.virtual_screen_rect()
    result: dict = {}

    top = tk.Toplevel(parent)
    top.withdraw()
    top.overrideredirect(True)
    top.geometry(f"{vw}x{vh}+{vx}+{vy}")
    top.attributes("-topmost", True)
    top.attributes("-alpha", 0.35)
    top.configure(bg="black")

    canvas = tk.Canvas(top, bg="black", highlightthickness=0, cursor="crosshair")
    canvas.pack(fill="both", expand=True)

    canvas.create_text(
        vw // 2, 46,
        text="拖动鼠标框选题目区域   ·   Esc 取消",
        fill="#ffffff", font=("Microsoft YaHei UI", 18, "bold"),
    )

    st: dict = {"x0": 0, "y0": 0, "rect": None, "label": None}

    def on_press(ev):
        st["x0"], st["y0"] = ev.x, ev.y
        if st["rect"] is not None:
            canvas.delete(st["rect"])
        if st["label"] is not None:
            canvas.delete(st["label"])
        st["rect"] = canvas.create_rectangle(ev.x, ev.y, ev.x, ev.y, outline="#4c8dff", width=2)
        st["label"] = canvas.create_text(ev.x + 8, ev.y - 16, text="", fill="#ffffff", anchor="w",
                                         font=("Consolas", 12, "bold"))

    def on_drag(ev):
        if st["rect"] is None:
            return
        canvas.coords(st["rect"], st["x0"], st["y0"], ev.x, ev.y)
        w, h = abs(ev.x - st["x0"]), abs(ev.y - st["y0"])
        if st["label"] is not None:
            canvas.coords(st["label"], min(st["x0"], ev.x) + 8, min(st["y0"], ev.y) - 16)
            canvas.itemconfigure(st["label"], text=f"{w} × {h}")

    def on_release(ev):
        x0, y0 = st["x0"], st["y0"]
        x1, y1 = ev.x, ev.y
        left, top_ = min(x0, x1), min(y0, y1)
        w, h = abs(x1 - x0), abs(y1 - y0)
        if w >= 30 and h >= 30:
            result["rect"] = (vx + left, vy + top_, w, h)
        close()

    def on_cancel(_ev=None):
        close()

    def close():
        try:
            top.grab_release()
            top.destroy()
        except tk.TclError:
            pass

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    top.bind("<Escape>", on_cancel)
    canvas.bind("<Escape>", on_cancel)

    top.deiconify()
    top.lift()
    try:
        top.grab_set()
    except tk.TclError:
        pass
    top.focus_force()
    parent.wait_window(top)
    return result.get("rect")
