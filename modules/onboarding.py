"""六步新手引导：真实主界面截图 + 聚光灯 + 东方角色卡片。"""
from __future__ import annotations

import os
import time
import tkinter as tk

from PIL import Image, ImageDraw, ImageGrab, ImageTk

_ASSETS_FALLBACK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

STEPS = [
    {
        "key": "kaguya", "role": "月之公主 · 永远亭",
        "title": "主界面",
        "copy": "辉夜：欢迎来到永远亭的临时书斋。这里是符卡作业簿——上面是结界的开关，"
                "中间三张符，分别记着摘录、翻译和答案。\n\n"
                "辉夜：别急，先把这里认熟。之后每一道作业，都会经过这三张符。",
    },
    {
        "key": "eirin", "role": "月之头脑",
        "title": "出题与摘录",
        "copy": "永琳：先让魔理沙把题目摘下来。点左上角的「抽符·识别」，或者按 F8，框住题目。\n\n"
                "永琳：识别结果会落在左边的「魔理沙的摘录」里。哪里不对，就直接改；"
                "改完按 F9，重新作答。",
    },
    {
        "key": "reisen", "role": "月兔 · 永远亭",
        "title": "结界",
        "copy": "铃仙：答题浏览器要先张开结界，才能和我们连通。展开「其他术式」，"
                "点「张开结界」。\n\n"
                "铃仙：浏览器打开后，从学校的入口登录。登录好，再点「开始退治」——"
                "别、别在没登录的时候就开始，会白跑的。",
    },
    {
        "key": "tewi", "role": "幸运的白兔 · 妖怪兔",
        "title": "全自动退治",
        "copy": "天为：都准备好了？点「开始退治」，我就把题一题一题地引出来。\n\n"
                "天为：遇到拿不准的，会先留个记号，不会悄悄停下。想收工就点「收工」，"
                "结界先留着，下次还能用。",
    },
    {
        "key": "tewi", "role": "幸运的白兔 · 妖怪兔",
        "title": "香火钱账本",
        "copy": "天为：对了，灵力不是白借的。点开右上角的「香火钱账本」，"
                "今天花了多少、用了哪位式神，都记得清清楚楚。\n\n"
                "天为：别想赖账哦～ 账本只是记账，不会替你乱花。",
    },
    {
        "key": "kagerou", "role": "竹林的狼女 · 影狼",
        "title": "设置与再次引路",
        "copy": "影狼：最后……「设置」里可以换结界来源、改式神，也能重新打开这段引路。\n\n"
                "影狼：我、我说完了。准备好了的话，就点「开始使用」吧。",
    },
]


def _avatar(assets: str, key: str, size: int):
    for folder in ("fan", ""):
        path = os.path.join(assets, "char", folder, f"avatar_{key}.png") if folder else \
            os.path.join(assets, "char", f"avatar_{key}.png")
        if os.path.exists(path):
            try:
                return ImageTk.PhotoImage(
                    Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS))
            except Exception:
                continue
    return None


class OnboardingWizard(tk.Toplevel):
    def __init__(self, app, on_finish=None, start_step: int = 1, on_progress=None):
        super().__init__(app.root)
        self.app = app
        self.on_progress = on_progress
        self.assets = getattr(app, "ASSETS", getattr(app, "assets_dir", _ASSETS_FALLBACK))
        self.on_finish = on_finish or (lambda _skipped=False: None)
        self.bg = "#0f0b1b"
        self.panel = "#171224"
        self.text = "#f2eef8"
        self.muted = "#a89fc7"
        self.gold = "#e8c46a"
        self.border = "#3a3157"
        self.F_TITLE = getattr(app, "F_TITLE", "楷体")
        self.F_UI = getattr(app, "F_UI", "Microsoft YaHei UI")
        self.step = max(1, min(len(STEPS), int(start_step or 1)))
        self._avatar_ref = None
        self._shot_ref = None
        self._finished = False
        self._shots: dict[str, Image.Image] = {}
        self._row_rect = (0, 0, 0, 0)
        self._actions_was_open = bool(getattr(app, "_actions_open", False))

        self.title("新手引导 · 符卡作业簿")
        self.configure(bg=self.bg)
        self.overrideredirect(True)
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self._screen = (sw, sh)
        self.geometry(f"{sw}x{sh}+0+0")
        self._capture_shots()
        self._build()
        self._show_step(self.step)
        self.bind("<Escape>", lambda _e: self._finish(True))
        self.bind("<Right>", lambda _e: self._next())
        self.bind("<Left>", lambda _e: self._prev())
        try:
            self.grab_set()
            self.focus_force()
        except Exception:
            pass

    # ------------------------------------------------------------------ 截图
    def _root_box(self):
        r = self.app.root
        try:
            r.update_idletasks()
            return (r.winfo_rootx(), r.winfo_rooty(),
                    max(1, r.winfo_width()), max(1, r.winfo_height()))
        except Exception:
            return (0, 0, 1280, 800)

    def _capture(self) -> Image.Image:
        r = self.app.root
        rx, ry, rw, rh = self._root_box()
        was_top = False
        try:
            was_top = bool(r.attributes("-topmost"))
        except Exception:
            pass
        try:
            r.attributes("-topmost", True)
            r.lift()
            r.update_idletasks()
            r.update()
            time.sleep(0.25)
        except Exception:
            pass
        try:
            shot = ImageGrab.grab(bbox=(rx, ry, rx + rw, ry + rh))
        except Exception:
            shot = Image.new("RGB", (rw, rh), (18, 14, 30))
        finally:
            try:
                r.attributes("-topmost", was_top)
            except Exception:
                pass
        return shot.convert("RGB")

    def _capture_shots(self) -> None:
        try:
            self._shots["collapsed"] = self._capture()
        except Exception:
            self._shots["collapsed"] = Image.new("RGB", (1280, 800), (18, 14, 30))
        try:
            if not getattr(self.app, "_actions_open", False):
                self.app._expand_actions()
            self.app.root.update_idletasks()
            self.app.root.update()
            self._shots["expanded"] = self._capture()
            self._row_rect = self._union([
                self._bbox(getattr(self.app, "btn_browser", None)),
                self._bbox(getattr(self.app, "btn_web", None)),
                self._bbox(getattr(self.app, "actions_row", None)),
            ])
            if not self._actions_was_open:
                self.app._collapse_actions()
                self.app.root.update_idletasks()
        except Exception:
            self._shots["expanded"] = self._shots["collapsed"]

    def _bbox(self, widget):
        try:
            if widget is None or not widget.winfo_exists():
                return None
            rx, ry, _, _ = self._root_box()
            x = widget.winfo_rootx() - rx
            y = widget.winfo_rooty() - ry
            return (x, y, widget.winfo_width(), widget.winfo_height())
        except Exception:
            return None

    def _union(self, boxes):
        boxes = [b for b in boxes if b]
        if not boxes:
            return (0, 0, 0, 0)
        x0 = min(b[0] for b in boxes)
        y0 = min(b[1] for b in boxes)
        x1 = max(b[0] + b[2] for b in boxes)
        y1 = max(b[1] + b[3] for b in boxes)
        return (x0, y0, x1 - x0, y1 - y0)

    def _rect_for(self, step: int):
        _, _, rw, rh = self._root_box()
        if step <= 1:
            return (0, 0, rw, rh)
        if step == 2:
            return self._union([self._bbox(getattr(self.app, "btn_capture", None)),
                                self._bbox(getattr(self.app, "panels", {}).get("src"))])
        if step in (3, 4):
            if self._row_rect and self._row_rect[2] > 20:
                return self._row_rect
            row = getattr(self.app, "actions_row", None)
            b = self._bbox(row)
            if b and b[2] > 20:
                return b
            return self._union([self._bbox(getattr(self.app, "btn_browser", None)),
                                self._bbox(getattr(self.app, "btn_web", None))])
        if step == 5:
            return self._bbox(getattr(self.app, "header_btns", None)) or (rw - 430, 0, 410, 100)
        if step == 6:
            return self._bbox(getattr(self.app, "settings_btn", None)) or \
                self._bbox(getattr(self.app, "header_btns", None))
        return (0, 0, rw, rh)

    # ------------------------------------------------------------------ 合成
    def _compose(self, shot: Image.Image, rect, max_w: int, max_h: int):
        sw, sh = shot.size
        scale = min(max_w / sw, max_h / sh)
        dw, dh = max(1, int(sw * scale)), max(1, int(sh * scale))
        pic = shot.resize((dw, dh), Image.LANCZOS)
        base = Image.new("RGB", (dw, dh), (5, 3, 10))
        base.paste(pic, (0, 0))
        if rect and rect[2] > 4 and rect[3] > 4:
            x, y, w, h = [int(v * scale) for v in rect]
            x = max(0, min(dw - 2, x))
            y = max(0, min(dh - 2, y))
            w = max(2, min(dw - x, w))
            h = max(2, min(dh - y, h))
            dim = Image.new("RGBA", (dw, dh), (5, 3, 10, 178))
            base = Image.alpha_composite(base.convert("RGBA"), dim).convert("RGB")
            crop = pic.crop((x, y, x + w, y + h))
            mask = Image.new("L", (w, h), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=18, fill=255)
            base.paste(crop, (x, y), mask)
            draw = ImageDraw.Draw(base)
            draw.rounded_rectangle((x, y, x + w - 1, y + h - 1), radius=18,
                                   outline=(255, 214, 120), width=3)
        return base

    def _build(self) -> None:
        self.canvas = tk.Canvas(self, bg=self.bg, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        sw, sh = self._screen
        self.canvas.create_text(52, 38, text="新手引导", anchor="w",
                                fill=self.gold, font=(self.F_TITLE, 30))
        self.step_text = self.canvas.create_text(sw - 50, 48, text="01 / 06", anchor="e",
                                                 fill=self.gold, font=(self.F_UI, 13, "bold"))
        self.sub_text = self.canvas.create_text(52, 78, text="东方 Project 风格 · 6 步认识符卡作业簿",
                                                anchor="w", fill=self.muted, font=(self.F_UI, 10))
        self.shot_item = self.canvas.create_image(52, 112, anchor="nw")
        card_w = 382
        card_x = sw - card_w - 50
        card_y = 116
        card_h = min(sh - 190, 742)
        self.card = tk.Frame(self, bg=self.panel, highlightbackground=self.border,
                             highlightthickness=1)
        self.card.place(x=card_x, y=card_y, width=card_w, height=card_h)
        self.avatar_lbl = tk.Label(self.card, bg=self.panel, bd=0)
        self.avatar_lbl.pack(pady=(26, 8))
        self.name_lbl = tk.Label(self.card, text="", bg=self.panel, fg=self.gold,
                                 font=(self.F_UI, 17, "bold"))
        self.name_lbl.pack()
        self.role_lbl = tk.Label(self.card, text="", bg=self.panel, fg=self.muted,
                                 font=(self.F_UI, 9))
        self.role_lbl.pack(pady=(3, 12))
        tk.Frame(self.card, bg=self.border, height=1).pack(fill="x", padx=18)
        self.copy_lbl = tk.Label(self.card, text="", bg=self.panel, fg=self.text,
                                 font=(self.F_UI, 11), justify="left", anchor="w",
                                 wraplength=330)
        self.copy_lbl.pack(fill="both", expand=True, padx=22, pady=18)
        self.dots = tk.Canvas(self.card, width=120, height=18, bg=self.panel,
                              highlightthickness=0)
        self.dots.pack(anchor="w", padx=22)
        bar = tk.Frame(self.card, bg=self.panel)
        bar.pack(fill="x", padx=22, pady=(8, 20))
        self.skip_btn = tk.Button(bar, text="跳过引路", command=lambda: self._finish(True),
                                  bg=self.panel, fg=self.muted, activebackground=self.panel,
                                  activeforeground=self.text, relief="flat", bd=0,
                                  cursor="hand2", font=(self.F_UI, 9))
        self.skip_btn.pack(side="left")
        self.next_btn = tk.Button(bar, text="下一位 →", command=self._next,
                                  bg=self.gold, fg="#241b12", activebackground="#f0d486",
                                  activeforeground="#241b12", relief="flat", bd=0,
                                  padx=18, pady=7, cursor="hand2",
                                  font=(self.F_UI, 10, "bold"))
        self.next_btn.pack(side="right")
        self.prev_btn = tk.Button(bar, text="← 上一位", command=self._prev,
                                  bg=self.panel, fg=self.muted, activebackground=self.panel,
                                  activeforeground=self.text, relief="flat", bd=0,
                                  cursor="hand2", font=(self.F_UI, 9))
        self.prev_btn.pack(side="right", padx=(0, 14))

    def _show_step(self, step: int) -> None:
        self.step = max(1, min(len(STEPS), step))
        d = STEPS[self.step - 1]
        self.canvas.itemconfigure(self.step_text, text=f"{self.step:02d} / 06")
        self.canvas.itemconfigure(self.sub_text, text=f"东方 Project 风格 · 第 {self.step} 步 / 共 6 步")
        shot = self._shots.get("expanded" if self.step in (3, 4) else "collapsed")
        if shot is None:
            shot = self._shots.get("collapsed")
        sw, sh = self._screen
        max_w = max(480, sw - 520)
        max_h = max(360, sh - 220)
        rect = self._rect_for(self.step)
        try:
            img = self._compose(shot, rect, max_w, max_h)
            self._shot_ref = ImageTk.PhotoImage(img)
            x = 52
            y = 112 + max(0, (max_h - img.height) // 2)
            self.canvas.coords(self.shot_item, x, y)
            self.canvas.itemconfigure(self.shot_item, image=self._shot_ref)
        except Exception:
            pass
        av = _avatar(self.assets, d["key"], 172)
        if av is not None:
            self._avatar_ref = av
            self.avatar_lbl.configure(image=av)
        self.name_lbl.configure(text=_name(d["key"]))
        self.role_lbl.configure(text=d["role"])
        self.copy_lbl.configure(text=d["copy"])
        self._draw_dots()
        self.prev_btn.configure(state="normal" if self.step > 1 else "disabled",
                                fg=self.muted if self.step > 1 else "#5b5470")
        self.next_btn.configure(text="开始使用" if self.step == len(STEPS) else "下一位 →")
        try:
            if self.on_progress:
                self.on_progress(self.step)
        except Exception:
            pass

    def _draw_dots(self) -> None:
        self.dots.delete("all")
        for i in range(len(STEPS)):
            x = 8 + i * 18
            fill = self.gold if i + 1 <= self.step else self.border
            r = 5 if i + 1 == self.step else 4
            self.dots.create_oval(x - r, 9 - r, x + r, 9 + r, fill=fill, outline="")

    def _next(self) -> None:
        if self.step >= len(STEPS):
            self._finish(False)
        else:
            self._show_step(self.step + 1)

    def _prev(self) -> None:
        if self.step > 1:
            self._show_step(self.step - 1)

    def _finish(self, skipped: bool = False) -> None:
        if self._finished:
            return
        self._finished = True
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        try:
            self.on_finish(bool(skipped))
        except Exception:
            pass


def _name(key: str) -> str:
    return {"kaguya": "蓬莱山辉夜", "eirin": "八意永琳", "reisen": "铃仙",
            "tewi": "因幡天为", "kagerou": "今泉影狼"}.get(key, key)
