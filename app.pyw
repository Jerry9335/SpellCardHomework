"""
符卡作业簿 —— 抽符（截屏）· 退治（作答）· 收卡（答案）。
幻想郷 · 宿題退治

双击 "符卡作业簿.exe" 启动，或 pythonw app.pyw
"""
from __future__ import annotations

import base64
import ctypes
import datetime as dt
import hashlib
import json
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from PIL import Image, ImageTk  # noqa: E402

from modules import (answer_engine, answer_format, banner_time, capture, clipboard,
                     first_run, greetings, hotkey, latex, llm, ocr_local, onboarding,
                     prompts, question_reader, region, settings, setup_wizard, skip_ledger,
                     theme, user_name, verify_math, web)  # noqa: E402

APP_TITLE = settings.APP_TITLE
ASSETS = os.path.join(HERE, "assets")
CFG_PATH = settings.CONFIG_PATH

C = {
    "bg": "#141221",
    "panel": "#1c1830",
    "panel2": "#231d3a",
    "input": "#2a2342",
    "text": "#f2eef8",
    "muted": "#a89fc7",
    "accent": "#d7444f",
    "accent_dark": "#a8303a",
    "gold": "#e8c46a",
    "ok": "#7ed6a5",
    "warn": "#f2a65a",
    "err": "#ff6b6b",
    "border": "#3a3157",
}
CLASSIC_C = dict(C)

VK_F8 = 0x77
VK_F9 = 0x78

TIPS = {
    "ready": "灵梦：把题目截图丢过来吧，早点退治完早点休息。",
    "done": "灵梦：这张符卡，我收下了。",
    "auto": "咲夜：时间开始流动了。",
    "stop": "紫：那就先休息一下吧。",
    "recognize": "魔理沙：让开，我来摘录这段符卡！",
    "translate": "慧音：这段英文，我来解释给你听。",
    "answer": "灵梦：交给我吧，把它退治掉。",
    "busy": "灵梦：别催，我正在处理。",
    "error": "魔理沙：呜哇，出岔子了……",
    "copied": "魔理沙：抄下来了！",
    "saved": "灵梦：好，我记住了。",
    "empty": "灵梦：连符卡都没递过来，我怎么退治？",
    "window_lost": "紫：那扇窗户跑到境界外面去了……",
    "auto_off": "灵梦：那就先这样吧。",
}

PLACEHOLDERS = {
    "src": "灵梦：把题目截图丢过来吧。\n\n· F8 截屏识别（或点左上角）\n· 识别结果可以在这里直接改，改完按 F9 重新作答",
    "trans": "慧音：英文题目的话，翻译会出现在这里。",
    "ans": "灵梦：答案会出现在这里。",
}

SPEAKERS = {
    "灵梦": "reimu", "魔理沙": "marisa", "慧音": "keine", "咲夜": "sakuya",
    "帕秋莉": "patchouli", "蕾米莉亚": "remilia", "芙兰": "flandre", "紫": "yukari",
}

QUOTES = [    "灵梦：这种作业，一张符卡就解决了吧。",
    "魔理沙：这种题，一炮就搞定啦！",
    "慧音：写作业的时候要认真一点哦。",
    "灵梦：又是练习题……真麻烦啊。",
    "魔理沙：让我看看，这道题藏着什么花样。",
    "咲夜：时间刚好，来得及。",
    "帕秋莉：公式记牢了，就不会出错。",
    "紫：别急，境界的另一边总有答案。",
    "灵梦：符卡回收完毕，下一个。",
    "魔理沙：这次的答案，我可不会写错！",
    "慧音：错题要好好订正才行。",
    "灵梦：……你又在偷懒看屏幕了吧。",
]


class Tooltip:
    """鼠标悬停时显示的说明。"""

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _e=None) -> None:
        if self.tip is not None:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, bg=C["panel2"], fg=C["text"],
                 relief="solid", bd=1, padx=8, pady=4,
                 font=("Microsoft YaHei UI", 9), justify="left").pack()

    def _hide(self, _e=None) -> None:
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None


def _pick_font(root: tk.Misc, candidates: list[str], fallback: str) -> str:
    fams = set(tkfont.families(root))
    for name in candidates:
        if name in fams:
            return name
    return fallback


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.cfg = settings.load()
        self.theme = str(self.cfg.get("theme", theme.THEME_CLASSIC))
        if self.theme == theme.THEME_NEW and (
                not self.cfg.get("theme_unlocked") or not theme.assets_available(ASSETS)):
            self.theme = theme.THEME_CLASSIC
            self.cfg["theme"] = theme.THEME_CLASSIC
        self._pending_theme: str | None = None
        self._relaunching = False
        C.clear()
        C.update(CLASSIC_C)
        if self.theme == theme.THEME_NEW:
            C.update(theme.NEW_COLORS)
        self.q: "queue.Queue[tuple]" = queue.Queue()
        self.busy = False
        self.cancel = threading.Event()
        self.windows: list[capture.WindowInfo] = []
        self.target_title = ""
        self.target_hwnd = 0
        self.region: tuple[int, int, int, int] | None = None

        self.last_text = ""
        self._web_hint = ""
        self._web_try = {}
        self._web_prev = {}
        self._web_seen = set()
        self.last_answer = ""
        self._auto_prev = None
        self._auto_last_change = 0.0
        self._auto_changed = False
        self._auto_last_trigger = 0.0
        self._settings_win: tk.Toplevel | None = None
        self._setup_win = None
        self._onboarding_win = None
        self._manual_onboarding = False
        self._onboarding_pre_access = ""
        self._onboarding_config_existed = False
        self._banner_job = None
        self._banner_phase = banner_time.phase_for_now()
        self._banner_cache = {}
        self._banner_item = None
        self._banner_display = None
        self._banner_fade_job = None
        self._banner_timer_job = None
        self._user_display = user_name.current_display_name()
        self._greet_avatars = {}
        self._greet_slot = greetings.slot_for_now()
        self._greet_recent = []
        self._greet_last_avatar = ""
        self._greet_rotate_job = None
        self._greet_timer_job = None
        self._theme_header_photo = None
        self._theme_header_item = None
        self._theme_header_job = None
        self._theme_content_photo = None
        self._theme_content_item = None
        self._theme_content_job = None
        self._theme_fade_job = None
        self._theme_content_display = None
        self._theme_panel_frames = []
        self._theme_panel_windows = []
        self._full_bg_canvas = None
        self._full_bg_item = None
        self._full_bg_photo = None
        self._full_bg_display = None
        self._full_bg_job = None
        self._toolbar_bar = None
        self._row2 = None
        self._status_bar = None
        self._scrollbars: dict[str, ttk.Scrollbar] = {}
        self.web_on = False
        self._barrier_last = None          # 结界（调试端口）上一次是否在线
        self._barrier_closing = False
        self._barrier_launching = False
        self._barrier_launch_until = 0.0
        self.web_stop = threading.Event()
        self.web_thread: threading.Thread | None = None
        self.messages: list[dict] = []
        self._streams: dict[tuple, latex.MathStream] = {}
        self.clip_watcher: clipboard.ClipboardWatcher | None = None
        self._update_checking = False
        self._launch_time = time.time()
        self._update_offered = ""
        self._update_last_source = ""
        self._web_user_stop = True
        self._web_round_failed = False

        self._resolve_fonts()
        self._load_avatars()
        self._build_style()
        self._build_ui()
        self._apply_config()
        self.root.after(1500, self._banner_phase_tick)
        self.root.after(60000, self._banner_watchdog)
        self.root.after(1500, self._greeting_tick)
        self.root.after(60000, self._greeting_watchdog)
        self._schedule_greeting_rotation()
        self.root.bind("<FocusIn>", self._on_banner_focus, add="+")
        self.root.bind("<Map>", self._on_banner_focus, add="+")
        self._start_hotkeys()
        self.root.after(60, self._pump)
        self.root.after(300, self._refresh_windows_async)
        self.root.after(3000, self._render_banner)
        self.root.after(12000, self._rotate_quote)
        self.root.after(5000, self._update_tick)
        self.root.after(2500, self._trial_reminder)
        self.root.after(1200, self._watch_barrier)
        self.clip_var.trace_add("write", lambda *_: setattr(self, "_clip_enabled", bool(self.clip_var.get())))
        self._start_clipboard()
        try:
            from modules import usage as _usage

            _usage.set_listener(self._on_usage_record)
            self._refresh_usage_meta()
        except Exception:
            pass

    # ------------------------------------------------------------------ 基础
    def _resolve_fonts(self) -> None:
        self.F_TITLE = _pick_font(self.root, ["华文行楷", "楷体", "Microsoft YaHei UI"], "Microsoft YaHei UI")
        self.F_JP = _pick_font(self.root, ["Yu Gothic UI", "Yu Gothic", "Microsoft YaHei UI"], "Microsoft YaHei UI")
        self.F_UI = "Microsoft YaHei UI"
        self.F_TEXT = ("Microsoft YaHei UI", 12)
        self.F_MONO = ("Consolas", 11)

    def _load_avatars(self) -> None:
        """加载角色头像：优先现代画风（assets/char/fan），否则用官方立绘裁切版。"""
        self._avatars: dict[str, ImageTk.PhotoImage] = {}
        self._status_icons: dict[str, ImageTk.PhotoImage] = {}
        self._btn_icons: dict[str, ImageTk.PhotoImage] = {}
        self._author_imgs: dict[str, ImageTk.PhotoImage] = {}
        self._greet_avatars: dict[str, ImageTk.PhotoImage] = {}
        for _ak in ("shinichi", "fastrof", "xiang"):
            _p = os.path.join(ASSETS, "authors", f"{_ak}.png")
            if not os.path.exists(_p):
                continue
            try:
                _im = Image.open(_p).convert("RGBA")
                self._author_imgs[_ak] = ImageTk.PhotoImage(_im.resize((120, 120), Image.LANCZOS))
            except Exception:
                pass

        keys = ("reimu", "marisa", "sakuya", "keine", "patchouli", "remilia",
                "flandre", "yukari", "aya", "kaguya", "eirin", "reisen",
                "tewi", "kagerou")
        for key in keys:
            for path in (os.path.join(ASSETS, "char", "fan", f"avatar_{key}.png"),
                         os.path.join(ASSETS, "char", f"avatar_{key}.png")):
                if not os.path.exists(path):
                    continue
                try:
                    im = Image.open(path).convert("RGBA")
                    self._avatars[key] = ImageTk.PhotoImage(im.resize((96, 96), Image.LANCZOS))
                    self._status_icons[key] = ImageTk.PhotoImage(im.resize((44, 44), Image.LANCZOS))
                    self._btn_icons[key] = ImageTk.PhotoImage(im.resize((24, 24), Image.LANCZOS))
                    break
                except Exception:
                    continue

        for key in keys:
            path = os.path.join(ASSETS, "char", "toast", f"avatar_{key}.png")
            if not os.path.exists(path):
                continue
            try:
                im = Image.open(path).convert("RGBA")
                self._greet_avatars[key] = ImageTk.PhotoImage(
                    im.resize((44, 44), Image.LANCZOS))
            except Exception:
                continue

    def _build_style(self) -> None:
        st = ttk.Style(self.root)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", background=C["bg"], foreground=C["text"], font=(self.F_UI, 10))
        st.configure("TFrame", background=C["bg"])
        st.configure("TLabel", background=C["bg"], foreground=C["text"])
        st.configure("Gold.TLabel", background=C["bg"], foreground=C["gold"])
        st.configure("TButton", background=C["panel2"], foreground=C["text"], bordercolor=C["border"],
                     focuscolor=C["bg"], padding=(10, 5), relief="flat")
        st.map("TButton", background=[("active", "#322a52"), ("disabled", "#1b1830")],
               foreground=[("disabled", "#5f5878")])
        st.configure("TEntry", fieldbackground=C["input"], foreground=C["text"], insertcolor=C["text"],
                     bordercolor=C["border"], lightcolor=C["border"], darkcolor=C["border"])
        st.configure("TCombobox", fieldbackground=C["input"], background=C["input"], foreground=C["text"],
                     arrowcolor=C["gold"], bordercolor=C["border"], lightcolor=C["border"], darkcolor=C["border"])
        st.map("TCombobox", fieldbackground=[("readonly", C["input"])], foreground=[("readonly", C["text"])])
        st.configure("TSpinbox", fieldbackground=C["input"], foreground=C["text"], arrowcolor=C["gold"],
                     bordercolor=C["border"])
        st.configure("TCheckbutton", background=C["bg"], foreground=C["text"], focuscolor=C["bg"])
        st.map("TCheckbutton", background=[("active", C["bg"])])
        st.configure("TScrollbar", background=C["input"], troughcolor=C["panel"], bordercolor=C["panel"],
                     arrowcolor=C["gold"], width=10)
        st.configure("Vertical.TScrollbar", background=C["input"], troughcolor=C["panel"],
                     bordercolor=C["panel"], arrowcolor=C["gold"], width=10)
        st.configure("Horizontal.TScrollbar", background=C["input"], troughcolor=C["panel"],
                     bordercolor=C["panel"], arrowcolor=C["gold"])
        st.configure("Dark.Vertical.TScrollbar", background=C["input"], troughcolor=C["panel"],
                     bordercolor=C["panel"], arrowcolor=C["gold"],
                     lightcolor=C["panel"], darkcolor=C["panel"])
        st.configure("TSeparator", background=C["border"])
        self.root.option_add("*TCombobox*Listbox.background", C["input"])
        self.root.option_add("*TCombobox*Listbox.foreground", C["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", C["accent"])
        self.root.option_add("*TCombobox*Listbox.font", (self.F_UI, 10))

    # ------------------------------------------------------------------ 启动画面
    # 注意：启动画面在 App 创建之前就由 make_splash() 显示，这里不再处理。

    # ------------------------------------------------------------------ 界面
    def _build_ui(self) -> None:
        r = self.root
        r.title(APP_TITLE)
        r.configure(bg=C["bg"])
        r.minsize(1020, 660)

        w, h = 1380, 880
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        r.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")

        if self.theme == theme.THEME_NEW:
            self._build_full_bg()
        self._build_header()
        self._build_toolbar()
        self._build_panels()
        self._build_status()
        if self.theme == theme.THEME_NEW:
            self.root.after(180, self._apply_glass_ui)

    def _build_full_bg(self) -> None:
        c = tk.Canvas(self.root, bg=C["bg"], highlightthickness=0, bd=0)
        c.place(x=0, y=0, relwidth=1, relheight=1)
        try:
            c.tk.call("lower", c._w)
        except Exception:
            pass
        self._full_bg_canvas = c
        self.root.bind("<Configure>", self._schedule_full_bg, add="+")
        self.root.after(60, self._render_full_bg)

    def _schedule_full_bg(self, ev=None) -> None:
        if ev is not None and getattr(ev, "widget", None) is not self.root:
            return
        if self._full_bg_job is not None:
            try:
                self.root.after_cancel(self._full_bg_job)
            except Exception:
                pass
        self._full_bg_job = self.root.after(110, self._render_full_bg)

    def _render_full_bg(self) -> None:
        self._full_bg_job = None
        c = self._full_bg_canvas
        if c is None:
            return
        w, h = self.root.winfo_width(), self.root.winfo_height()
        if w < 120 or h < 80:
            return
        try:
            im = theme.compose_background(ASSETS, self._banner_phase, (w, h))
            photo = ImageTk.PhotoImage(im)
        except Exception:
            return
        self._full_bg_display = im
        self._full_bg_photo = photo
        if self._full_bg_item is None:
            self._full_bg_item = c.create_image(0, 0, anchor="nw", image=photo,
                                                tags=("full_bg",))
        else:
            c.itemconfigure(self._full_bg_item, image=photo)
            c.coords(self._full_bg_item, 0, 0)
        c.tag_lower(self._full_bg_item)
        # 标题直接画在全窗口背景上，背景从顶到底连续
        c.delete("theme_title")
        light = self._banner_phase in ("day", "afternoon")
        if light:
            title_fill, title_out = "#241226", "#fff8ea"
            sub_fill, sub_out = "#7a2a22", "#fff8ea"
        else:
            title_fill, title_out = "#fffaf6", "#160e20"
            sub_fill, sub_out = C["gold"], "#160e20"
        for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2),
                       (2, 2), (2, -2), (-2, 2), (-2, -2)):
            c.create_text(26 + dx, 40 + dy, text="符卡作业簿", anchor="w",
                          fill=title_out, font=(self.F_TITLE, 26), tags="theme_title")
            c.create_text(30 + dx, 74 + dy, text="～ 幻想郷・宿題退治 ～", anchor="w",
                          fill=sub_out, font=(self.F_JP, 11), tags="theme_title")
        c.create_text(26, 40, text="符卡作业簿", anchor="w", fill=title_fill,
                      font=(self.F_TITLE, 26), tags="theme_title")
        c.create_text(30, 74, text="～ 幻想郷・宿題退治 ～", anchor="w", fill=sub_fill,
                      font=(self.F_JP, 11), tags="theme_title")
        c.tag_raise("theme_title")

    def _set_layered(self, widget, alpha: int) -> None:
        if os.name != "nt":
            return
        try:
            hwnd = widget.winfo_id()
            u = ctypes.windll.user32
            ex = u.GetWindowLongW(hwnd, -20)
            u.SetWindowLongW(hwnd, -20, int(ex) | 0x80000)
            u.SetLayeredWindowAttributes(hwnd, 0, max(0, min(255, int(alpha))), 0x2)
        except Exception:
            pass

    def _apply_glass_tree(self, widget, alpha: int = 212) -> None:
        try:
            cls = widget.winfo_class()
        except Exception:
            return
        a = alpha
        if cls in ("Text", "Listbox"):
            a = min(248, alpha + 24)
        elif cls in ("Button", "Checkbutton", "Radiobutton", "Label"):
            a = min(245, alpha + 14)
        self._set_layered(widget, a)
        try:
            for child in widget.winfo_children():
                self._apply_glass_tree(child, alpha)
        except Exception:
            pass

    def _apply_glass_ui(self) -> None:
        if self.theme != theme.THEME_NEW:
            return
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        for w in (self._toolbar_bar, self._row2, self._status_bar, self.header_btns):
            if w is not None:
                self._apply_glass_tree(w, 210)
        for f in self._theme_panel_frames:
            self._apply_glass_tree(f, 205)

    def _build_header(self) -> None:
        if self.theme == theme.THEME_NEW:
            self._build_theme_header()
        else:
            self._build_classic_header()

    def _build_theme_header(self) -> None:
        # 不再单独画 140px 横幅；标题直接画在全窗口背景上
        self.header_btns = tk.Frame(self.root, bg=C["panel2"])
        self.header_btns.place(relx=1.0, y=28, anchor="ne", x=-20)

        def _hbtn(text: str, cmd):
            b = tk.Button(
                self.header_btns, text=text, command=cmd,
                bg=C["panel2"], fg=C["gold"], activebackground=C["accent_dark"],
                activeforeground="#ffffff", relief="flat", bd=0,
                padx=10, pady=5, cursor="hand2", font=(self.F_UI, 10, "bold"),
            )
            b.pack(side="left", padx=(4, 0))
            return b

        usage_btn = _hbtn("✦  香火钱账本", self._open_usage)
        Tooltip(usage_btn, "香火钱账本：查看每次调用的 tokens、耗时和费用")
        self.settings_btn = _hbtn("⚙  设置", self._open_settings)
        _hbtn("✦  关于程序", self._about_app)
        _hbtn("✿  关于作者", self._about_authors)
        self.root.after(80, self._render_theme_header)

    def _schedule_theme_header(self, _ev=None) -> None:
        if self._theme_header_job is not None:
            try:
                self.root.after_cancel(self._theme_header_job)
            except Exception:
                pass
        self._theme_header_job = self.root.after(90, self._render_theme_header)

    def _render_theme_header(self) -> None:
        self._theme_header_job = None
        self._render_full_bg()

    def _build_classic_header(self) -> None:
        self.header = tk.Canvas(self.root, height=96, bd=0, highlightthickness=0, bg=C["bg"])
        self.header.pack(fill="x")
        self._banner_src = self._load_banner(self._banner_phase)

        self.header.bind("<Configure>", self._schedule_banner)
        self._banner_photo = None

        self.header_btns = tk.Frame(self.header, bg="#1b1730")
        self.header_btns.place(relx=1.0, rely=0.5, anchor="e", x=-20)

        def _hbtn(text: str, cmd):
            b = tk.Button(
                self.header_btns, text=text, command=cmd,
                bg="#1b1730", fg=C["gold"], activebackground=C["accent_dark"],
                activeforeground="#ffffff", relief="flat", bd=0,
                padx=10, pady=5, cursor="hand2", font=(self.F_UI, 10, "bold"),
            )
            b.pack(side="left", padx=(4, 0))
            return b

        usage_btn = _hbtn("✦  香火钱账本", self._open_usage)
        Tooltip(usage_btn, "香火钱账本：查看每次调用的 tokens、耗时和费用")
        self.settings_btn = _hbtn("⚙  设置", self._open_settings)
        _hbtn("✦  关于程序", self._about_app)
        _hbtn("✿  关于作者", self._about_authors)

    BANNER_FILES = {
        "day": "banner_day.png",
        "afternoon": "banner.png",
        "night": "banner_night.png",
    }

    def _load_banner(self, phase: str):
        """按阶段取图；缺图时回退到 banner.png。"""
        names = []
        name = self.BANNER_FILES.get(phase)
        if name:
            names.append(name)
        if "banner.png" not in names:
            names.append("banner.png")
        for name in names:
            if name in self._banner_cache:
                return self._banner_cache[name]
            path = os.path.join(ASSETS, name)
            if not os.path.exists(path):
                continue
            try:
                img = Image.open(path).convert("RGB")
            except Exception:
                continue
            self._banner_cache[name] = img
            return img
        return None

    def _compose_banner(self, src, w: int, h: int):
        """按原来的缩放/居中裁切逻辑合成 header 图。"""
        scale = max(w / src.width, h / src.height)
        nw, nh = max(1, int(src.width * scale) + 1), max(1, int(src.height * scale) + 1)
        resized = src.resize((nw, nh), Image.BILINEAR)
        left, top = (nw - w) // 2, (nh - h) // 2
        resized = resized.crop((left, top, left + w, top + h))
        from PIL import ImageDraw as _ID

        overlay = Image.new("RGBA", resized.size, (0, 0, 0, 0))
        od = _ID.Draw(overlay)
        gw = max(1, int(resized.width * 0.55))
        for x in range(gw):
            alpha = int(175 * (1 - x / gw))
            od.line([(x, 0), (x, resized.height)], fill=(16, 12, 30, alpha))
        return Image.alpha_composite(resized.convert("RGBA"), overlay).convert("RGB")

    def _cancel_banner_fade(self) -> None:
        if self._banner_fade_job is not None:
            try:
                self.root.after_cancel(self._banner_fade_job)
            except Exception:
                pass
            self._banner_fade_job = None

    def _schedule_banner(self, _ev=None) -> None:
        if self._banner_job is not None:
            try:
                self.root.after_cancel(self._banner_job)
            except Exception:
                pass
        self._banner_job = self.root.after(90, self._render_banner)

    def _render_banner(self) -> None:
        self._banner_job = None
        if self.theme == theme.THEME_NEW:
            self._render_theme_header()
            return
        self._cancel_banner_fade()
        c = self.header
        w = max(200, c.winfo_width())
        h = int(c.cget("height"))
        c.delete("banner_img")
        c.delete("banner_text")
        self._banner_item = None
        self._banner_display = None
        if self._banner_src is not None:
            try:
                composed = self._compose_banner(self._banner_src, w, h)
                self._banner_display = composed
                self._banner_photo = ImageTk.PhotoImage(composed)
                self._banner_item = c.create_image(
                    0, 0, anchor="nw", image=self._banner_photo, tags="banner_img")
            except Exception:
                self._banner_item = None
                self._banner_display = None

        c.create_text(26, 40, text="符卡作业簿", anchor="w", fill="#fffaf6",
                      font=(self.F_TITLE, 26), tags="banner_text")
        c.create_text(30, 74, text="～ 幻想郷・宿題退治 ～", anchor="w", fill=C["gold"],
                      font=(self.F_JP, 11), tags="banner_text")

    def _fade_to_banner(self, new_src, duration_ms: int = 200) -> None:
        """200ms 交叉淡入；圆角/布局仍由 header Canvas 负责。"""
        c = self.header
        w = max(200, c.winfo_width())
        h = int(c.cget("height"))
        if self._banner_item is None or self._banner_display is None:
            self._banner_src = new_src
            self._render_banner()
            return
        try:
            new_img = self._compose_banner(new_src, w, h)
        except Exception:
            self._banner_src = new_src
            self._render_banner()
            return
        old_img = self._banner_display
        if old_img.size != new_img.size:
            self._banner_src = new_src
            self._render_banner()
            return

        self._cancel_banner_fade()
        self._banner_src = new_src
        steps = 12
        interval = max(10, int(duration_ms / steps))
        state = {"i": 0}

        def step() -> None:
            if self._banner_item is None:
                self._banner_fade_job = None
                return
            state["i"] += 1
            t = min(1.0, state["i"] / steps)
            try:
                frame = Image.blend(old_img, new_img, t)
                photo = ImageTk.PhotoImage(frame)
                self._banner_photo = photo
                c.itemconfigure(self._banner_item, image=photo)
            except Exception:
                pass
            if t < 1.0:
                self._banner_fade_job = self.root.after(interval, step)
            else:
                self._banner_display = new_img
                self._banner_fade_job = None

        self._banner_fade_job = self.root.after(interval, step)

    def _apply_banner_phase(self, phase: str, fade: bool = True) -> None:
        if phase not in self.BANNER_FILES:
            phase = "afternoon"
        src = self._load_banner(phase)
        if src is None:
            return
        if phase == self._banner_phase and self._banner_src is not None:
            return
        self._banner_phase = phase
        if fade and self._banner_item is not None and self._banner_display is not None:
            self._fade_to_banner(src)
        else:
            self._cancel_banner_fade()
            self._banner_src = src
            self._render_banner()

    def _schedule_next_banner_tick(self) -> None:
        if self._banner_timer_job is not None:
            try:
                self.root.after_cancel(self._banner_timer_job)
            except Exception:
                pass
            self._banner_timer_job = None
        try:
            now = dt.datetime.now()
            nxt = banner_time.next_boundary(now)
            delay = max(500, int((nxt - now).total_seconds() * 1000) + 300)
        except Exception:
            delay = 60000
        self._banner_timer_job = self.root.after(delay, self._banner_phase_tick)

    def _banner_phase_tick(self) -> None:
        self._banner_timer_job = None
        try:
            self._apply_phase(banner_time.phase_for_now(), fade=True)
        except Exception:
            pass
        self._schedule_next_banner_tick()

    def _banner_watchdog(self) -> None:
        try:
            phase = banner_time.phase_for_now()
            if phase != self._banner_phase:
                self._apply_phase(phase, fade=True)
        except Exception:
            pass
        try:
            self._schedule_next_banner_tick()
        except Exception:
            pass
        try:
            self.root.after(60000, self._banner_watchdog)
        except Exception:
            pass

    def _on_banner_focus(self, _ev=None) -> None:
        try:
            phase = banner_time.phase_for_now()
            if phase != self._banner_phase:
                self._apply_phase(phase, fade=True)
            self._schedule_next_banner_tick()
            self._check_greeting_slot()
        except Exception:
            pass

    def _refresh_greeting(self, slot: str | None = None) -> None:
        slot = slot or greetings.slot_for_now()
        entry = greetings.pick_entry(slot, self._greet_recent, self._greet_last_avatar)
        full = entry["speaker"] + "：" + greetings.format_entry(entry, self._user_display)
        self._greet_slot = slot
        self._greet_last_avatar = entry["avatar"]
        self._greet_recent = (self._greet_recent + [entry["id"]])[-10:]
        if not hasattr(self, "greet_var"):
            return
        self._greet_full = full
        self._apply_greeting_text()
        photo = self._greet_avatars.get(entry["avatar"])
        if photo is not None:
            self.greet_avatar.configure(image=photo)
            self.greet_avatar.image = photo
        else:
            self.greet_avatar.configure(image="")
            self.greet_avatar.image = None
        if getattr(self, "_greet_tooltip", None) is not None:
            self._greet_tooltip.text = full

    def _layout_greeting(self) -> None:
        """窄窗口隐藏问候，优先保证按钮完整；宽窗口再显示。"""
        try:
            width = self.greet_frame.master.winfo_width()
            visible = bool(self.greet_frame.winfo_manager())
            if width < 1120 and visible:
                self.greet_frame.pack_forget()
            elif width >= 1120 and not visible:
                self.greet_frame.pack(side="right", padx=(12, 4), before=self.btn_capture)
        except Exception:
            pass

    def _on_greeting_bar_configure(self, _ev=None) -> None:
        self._layout_greeting()
        self._apply_greeting_text()

    def _apply_greeting_text(self) -> None:
        full = getattr(self, "_greet_full", "")
        if not full or not hasattr(self, "greet_var"):
            return
        limit = 50
        shown = full if len(full) <= limit else full[:limit - 1] + "…"
        self.greet_var.set(shown)

    def _schedule_greeting_rotation(self) -> None:
        if self._greet_rotate_job is not None:
            try:
                self.root.after_cancel(self._greet_rotate_job)
            except Exception:
                pass
            self._greet_rotate_job = None
        self._greet_rotate_job = self.root.after(
            greetings.ROTATE_SECONDS * 1000, self._rotate_greeting)

    def _rotate_greeting(self) -> None:
        self._greet_rotate_job = None
        try:
            if greetings.slot_for_now() == self._greet_slot:
                self._refresh_greeting()
        except Exception:
            pass
        self._schedule_greeting_rotation()

    def _check_greeting_slot(self) -> None:
        try:
            slot = greetings.slot_for_now()
            if slot != self._greet_slot:
                self._refresh_greeting(slot)
                self._schedule_greeting_rotation()
        except Exception:
            pass

    def _schedule_next_greeting_tick(self) -> None:
        if self._greet_timer_job is not None:
            try:
                self.root.after_cancel(self._greet_timer_job)
            except Exception:
                pass
            self._greet_timer_job = None
        try:
            now = dt.datetime.now()
            nxt = greetings.next_boundary(now)
            delay = max(500, int((nxt - now).total_seconds() * 1000) + 300)
        except Exception:
            delay = 60000
        self._greet_timer_job = self.root.after(delay, self._greeting_tick)

    def _greeting_tick(self) -> None:
        self._greet_timer_job = None
        self._check_greeting_slot()
        self._schedule_next_greeting_tick()

    def _greeting_watchdog(self) -> None:
        self._check_greeting_slot()
        try:
            self._schedule_next_greeting_tick()
        except Exception:
            pass
        try:
            self.root.after(60000, self._greeting_watchdog)
        except Exception:
            pass

    def _build_toolbar(self) -> None:
        bar = tk.Frame(self.root, bg=C["bg"])
        top_pad = 140 if self.theme == theme.THEME_NEW else 8
        bar.pack(fill="x", padx=14, pady=(top_pad, 6))
        self._toolbar_bar = bar

        self.btn_capture = tk.Button(
            bar, text="⛩  抽符 · 识别", command=lambda: self._run_action(self.action_capture),
            bg=C["accent"], fg="#ffffff", activebackground=C["accent_dark"],
            activeforeground="#ffffff", relief="flat", bd=0, padx=18, pady=8,
            cursor="hand2", font=(self.F_UI, 11, "bold"),
        )
        self.btn_capture.pack(side="left")
        Tooltip(self.btn_capture, "截屏识别：截取屏幕上的题目并识别（F8）")

        self.btn_actions = tk.Button(
            bar, text="☰  其他术式 ▾", command=self._toggle_actions,
            bg=C["panel2"], fg=C["gold"], activebackground="#322a52", activeforeground="#ffffff",
            relief="flat", bd=0, padx=12, pady=8, cursor="hand2",
            font=(self.F_UI, 10, "bold"),
        )
        self.btn_actions.pack(side="left", padx=(8, 0))
        Tooltip(self.btn_actions, "展开 / 收起：重抽、自动监视、张开结界、开始退治、收工")

        # 展开后的第二行：五个次要动作
        self.actions_row = tk.Frame(self.root, bg=C["bg"])
        self._actions_open = False

        btn_again = tk.Button(
            self.actions_row, text="↻  重抽此符",
            command=lambda: self._run_action(self.action_answer_only),
            bg=C["panel2"], fg=C["text"], activebackground="#322a52", activeforeground="#ffffff",
            relief="flat", bd=0, padx=14, pady=8, cursor="hand2", font=(self.F_UI, 10),
        )
        btn_again.pack(side="left")
        Tooltip(btn_again, "重新作答：用当前文本重新问一次（F9）")

        self.auto_var = tk.BooleanVar(value=False)
        self.btn_auto = tk.Checkbutton(
            self.actions_row, text="☯  自动监视", variable=self.auto_var,
            command=lambda: self._run_action(self._toggle_auto),
            indicatoron=False, bg=C["panel2"], fg=C["text"], selectcolor=C["accent_dark"],
            activebackground="#322a52", activeforeground="#ffffff", relief="flat", bd=0,
            padx=16, pady=8, cursor="hand2", font=(self.F_UI, 11),
        )
        self.btn_auto.pack(side="left", padx=(10, 0))
        Tooltip(self.btn_auto, "自动监听：题目一变就自动识别，不用手动按 F8")

        self.browser_var = tk.BooleanVar(value=False)
        self.btn_browser = tk.Checkbutton(
            self.actions_row, text="☂  张开结界", variable=self.browser_var,
            command=lambda: self._run_action(self._toggle_browser),
            indicatoron=False, bg=C["panel2"], fg=C["text"], selectcolor="#2e3a52",
            activebackground="#322a52", activeforeground="#ffffff", relief="flat", bd=0,
            padx=14, pady=8, cursor="hand2", font=(self.F_UI, 11),
        )
        self.btn_browser.pack(side="left", padx=(10, 0))
        Tooltip(self.btn_browser, "张开 / 关闭专用答题浏览器（带调试端口，才能自动答题）")

        self.web_var = tk.BooleanVar(value=False)
        self.btn_web = tk.Checkbutton(
            self.actions_row, text="⛩  开始退治", variable=self.web_var,
            command=lambda: self._run_action(self._toggle_web),
            indicatoron=False, bg=C["panel2"], fg=C["text"], selectcolor="#3a2b52",
            activebackground="#322a52", activeforeground="#ffffff", relief="flat", bd=0,
            padx=14, pady=8, cursor="hand2", font=(self.F_UI, 11),
        )
        self.btn_web.pack(side="left", padx=(8, 0))
        Tooltip(self.btn_web, "开始全自动网页答题：读题、填答案、交卷、翻页")

        btn_stop = tk.Button(
            self.actions_row, text="■  收工",
            command=lambda: self._run_action(self.action_stop),
            bg="#2c2036", fg=C["err"], activebackground="#3d2a44", activeforeground=C["err"],
            relief="flat", bd=0, padx=14, pady=8, cursor="hand2", font=(self.F_UI, 11),
        )
        btn_stop.pack(side="left", padx=(10, 0))
        Tooltip(btn_stop, "停止自动监听和自动答题")

        self.greet_frame = tk.Frame(bar, bg=C["bg"])
        self.greet_frame.pack(side="right", padx=(12, 4), before=self.btn_capture)
        self.greet_avatar = tk.Label(self.greet_frame, bg=C["bg"], bd=0, padx=0, pady=0)
        self.greet_avatar.pack(side="left", padx=(0, 8))
        self.greet_var = tk.StringVar()
        self.greet_label = tk.Label(
            self.greet_frame, textvariable=self.greet_var, bg=C["bg"], fg=C["muted"],
            font=(self.F_UI, 11), anchor="e", justify="right",
        )
        self.greet_label.pack(side="left")
        bar.bind("<Configure>", self._on_greeting_bar_configure, add="+")
        self._greet_tooltip = Tooltip(self.greet_label, "")
        self._refresh_greeting()

        # 第二行：目标 + 剪贴板开关
        row2 = tk.Frame(self.root, bg=C["bg"])
        row2.pack(fill="x", padx=14, pady=(0, 6))
        self.row2 = row2
        self._row2 = row2
        tk.Label(row2, text="目标", bg=C["bg"], fg=C["muted"], font=(self.F_UI, 10)).pack(side="left")
        self.window_var = tk.StringVar()
        self.window_box = ttk.Combobox(row2, textvariable=self.window_var, values=["整个屏幕"],
                                       state="readonly", width=30)
        self.window_box.pack(side="left", fill="x", expand=True, padx=(8, 8))
        self.window_box.bind("<<ComboboxSelected>>", self._on_window_selected)

        tk.Button(row2, text="框选", command=self._pick_region, bg=C["panel2"], fg=C["text"],
                  activebackground="#322a52", relief="flat", bd=0, padx=12, pady=5,
                  cursor="hand2", font=(self.F_UI, 10)).pack(side="left", padx=(0, 6))
        tk.Button(row2, text="刷新", command=self._refresh_windows_async, bg=C["panel2"], fg=C["muted"],
                  activebackground="#322a52", relief="flat", bd=0, padx=12, pady=5,
                  cursor="hand2", font=(self.F_UI, 10)).pack(side="left", padx=(0, 16))

        self.clip_var = tk.BooleanVar(value=True)
        tk.Checkbutton(row2, text="剪贴板", variable=self.clip_var,
                       bg=C["bg"], fg=C["muted"], selectcolor=C["panel2"],
                       activebackground=C["bg"], activeforeground=C["text"],
                       font=(self.F_UI, 10), cursor="hand2").pack(side="left")

        self._refresh_action_status()

    def _toggle_actions(self) -> None:
        if self._actions_open:
            self._collapse_actions()
        else:
            self._expand_actions()

    def _expand_actions(self) -> None:
        if self._actions_open:
            return
        self.actions_row.pack(fill="x", padx=14, pady=(0, 4), before=self.row2)
        self._actions_open = True
        self.btn_actions.configure(text="☰  其他术式 ▴")
        self._refresh_theme_layout()

    def _collapse_actions(self) -> None:
        if not getattr(self, "_actions_open", False):
            return
        self.actions_row.pack_forget()
        self._actions_open = False
        self.btn_actions.configure(text="☰  其他术式 ▾")
        self._refresh_theme_layout()

    def _refresh_theme_layout(self) -> None:
        """展开/收起第二行后重新计算新主题面板位置，避免盖住目标栏。"""
        if self.theme != theme.THEME_NEW:
            return
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        try:
            self.root.after_idle(self._layout_theme_panels)
        except Exception:
            pass

    def _run_action(self, fn) -> None:
        """执行动作后自动收起，并把开关状态写到窗口标题。"""
        self._collapse_actions()
        try:
            fn()
        finally:
            self._refresh_action_status()

    def _refresh_action_status(self) -> None:
        parts = []
        try:
            if self.auto_var.get():
                parts.append("自动监视")
            if self.browser_var.get():
                parts.append("结界")
            if self.web_var.get():
                parts.append("退治中")
        except Exception:
            pass
        title = APP_TITLE + ((" · " + " · ".join(parts)) if parts else "")
        try:
            self.root.title(title)
        except Exception:
            pass

    def _build_panels(self) -> None:
        if self.theme == theme.THEME_NEW:
            self._build_theme_panels()
            return
        pw = ttk.Panedwindow(self.root, orient="horizontal")
        pw.pack(fill="both", expand=True, padx=14, pady=(4, 6))
        self.panels: dict[str, tk.Text] = {}

        f1 = self._make_panel(pw, "① 魔理沙的摘录", "src", editable=True,
                              buttons=[("抹去", lambda: self._clear_panel("src"))])
        f2 = self._make_panel(pw, "② 慧音的翻译", "trans", editable=False,
                              buttons=[("誊抄", lambda: self._copy_panel("trans"))])
        f3 = self._make_panel(pw, "③ 灵梦的答案", "ans", editable=False,
                              buttons=[("誊抄", lambda: self._copy_panel("ans"))])
        pw.add(f1, weight=30)
        pw.add(f2, weight=22)
        pw.add(f3, weight=32)

    def _build_theme_panels(self) -> None:
        # 三块面板直接放在全窗口背景上，不再用 content Canvas，
        # 这样从标题到底部始终是同一张背景图。
        self.panels = {}
        f1 = self._make_panel(self.root, "① 魔理沙的摘录", "src", editable=True,
                              buttons=[("抹去", lambda: self._clear_panel("src"))])
        f2 = self._make_panel(self.root, "② 慧音的翻译", "trans", editable=False,
                              buttons=[("誊抄", lambda: self._copy_panel("trans"))])
        f3 = self._make_panel(self.root, "③ 灵梦的答案", "ans", editable=False,
                              buttons=[("誊抄", lambda: self._copy_panel("ans"))])
        self._theme_panel_frames = [f1, f2, f3]
        self.root.bind("<Configure>", self._schedule_theme_panels, add="+")
        self.root.after(120, self._layout_theme_panels)

    def _schedule_theme_panels(self, ev=None) -> None:
        if ev is not None and getattr(ev, "widget", None) is not self.root:
            return
        if self._theme_content_job is not None:
            try:
                self.root.after_cancel(self._theme_content_job)
            except Exception:
                pass
        self._theme_content_job = self.root.after(100, self._layout_theme_panels)

    def _layout_theme_panels(self) -> None:
        self._theme_content_job = None
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        rw = self.root.winfo_width()
        if rw < 120:
            return
        row2 = getattr(self, "_row2", None)
        status = getattr(self, "_status_bar", None)
        if row2 is None or status is None:
            return
        top = row2.winfo_y() + row2.winfo_height() + 10
        bottom = status.winfo_y() - 8
        h = bottom - top
        if h < 80:
            return
        margin = 18
        gap = 16
        avail = max(320, rw - 2 * margin - 2 * gap)
        w1 = max(220, int(avail * 30 / 84))
        w2 = max(180, int(avail * 22 / 84))
        w3 = max(220, avail - w1 - w2)
        specs = [
            (margin, top, w1, h),
            (margin + w1 + gap, top, w2, h),
            (margin + w1 + w2 + 2 * gap, top, w3, h),
        ]
        for frame, (x, y, w, hh) in zip(self._theme_panel_frames, specs):
            frame.place(x=x, y=y, width=w, height=hh)
            frame.lift()

    def _apply_phase(self, phase: str, fade: bool = True) -> None:
        if self.theme == theme.THEME_NEW:
            self._apply_theme_phase(phase, fade)
        else:
            self._apply_banner_phase(phase, fade)

    def _apply_theme_phase(self, phase: str, fade: bool = True) -> None:
        if phase not in theme.MAIN_FILES:
            phase = "afternoon"
        if phase == self._banner_phase and self._full_bg_item is not None:
            return
        self._banner_phase = phase
        self._render_full_bg()

    def _make_panel(self, parent, title: str, key: str, editable: bool,
                    buttons: list, hint: str = "") -> tk.Frame:
        f = tk.Frame(parent, bg=C["panel"], highlightbackground=C["border"], highlightthickness=1)
        hdr = tk.Frame(f, bg=C["panel"])
        hdr.pack(fill="x")
        avatar_key = {"src": "marisa", "trans": "keine", "ans": "reimu"}.get(key)
        avatar = self._avatars.get(avatar_key) if avatar_key else None
        if avatar is not None:
            tk.Label(hdr, image=avatar, bg=C["panel"], bd=0).pack(side="left", padx=(10, 4), pady=4)
        tk.Label(hdr, text=title, bg=C["panel"], fg=C["gold"], anchor="w",
                 font=(self.F_TITLE, 17)).pack(side="left", padx=(8, 8), pady=(8, 6))
        tipmap = {"抹去": "清空这个面板的内容", "誊抄": "复制面板内容到剪贴板"}
        for text, cmd in buttons:
            _b = tk.Button(hdr, text=text, command=cmd, bg=C["panel"], fg=C["muted"],
                           activebackground=C["panel2"], activeforeground=C["text"],
                           relief="flat", bd=0, padx=8, pady=2, cursor="hand2",
                           font=(self.F_UI, 10))
            _b.pack(side="right", padx=(0, 6), pady=(8, 6))
            if text in tipmap:
                Tooltip(_b, tipmap[text])
        if hint:
            tk.Label(hdr, text=hint, bg=C["panel"], fg=C["muted"],
                     font=(self.F_UI, 10)).pack(side="left", pady=(10, 2))

        if key == "ans":
            follow = tk.Frame(f, bg=C["panel"])
            follow.pack(side="bottom", fill="x", padx=(9, 6), pady=(0, 8))
            self.follow_var = tk.StringVar()
            tk.Label(follow, text="追问", bg=C["panel"], fg=C["muted"],
                     font=(self.F_UI, 9)).pack(side="left", padx=(2, 6))
            self.follow_entry = tk.Entry(follow, textvariable=self.follow_var, width=1, bg=C["panel2"],
                                         fg=C["text"], insertbackground=C["gold"], relief="flat",
                                         highlightthickness=1, highlightbackground=C["border"],
                                         highlightcolor=C["accent"], font=(self.F_UI, 10))
            self.follow_entry.pack(side="left", fill="x", expand=True, ipady=5)
            self.follow_entry.bind("<Return>", lambda _e: self._send_followup())
            tk.Button(follow, text="发送", command=self._send_followup, bg=C["accent"],
                      fg="#ffffff", relief="flat", bd=0, padx=10, pady=3, cursor="hand2",
                      font=(self.F_UI, 9, "bold")).pack(side="left", padx=(6, 0))

        body = tk.Frame(f, bg=C["panel"])
        body.pack(fill="both", expand=True, padx=(9, 4), pady=(0, 9))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        txt = tk.Text(body, width=1, height=1, bg=C["panel2"], fg=C["text"], insertbackground=C["gold"],
                      relief="flat", bd=0, wrap="word", padx=14, pady=12,
                      font=self.F_TEXT, spacing1=2, spacing2=2, spacing3=6,
                      selectbackground=C["accent"], selectforeground="#ffffff",
                      undo=True, maxundo=50)
        sb = ttk.Scrollbar(body, orient="vertical", command=txt.yview, style="Dark.Vertical.TScrollbar")
        txt.configure(yscrollcommand=sb.set)
        txt.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        sb.grid_remove()
        self._scrollbars[key] = sb

        txt.tag_configure("body", foreground=C["text"])
        txt.tag_configure("dim", foreground=C["muted"], font=(self.F_UI, 10))
        txt.tag_configure("head", foreground=C["ok"], font=(self.F_UI, 12, "bold"))
        txt.tag_configure("err", foreground=C["err"])
        txt.tag_configure("placeholder", foreground=C["muted"], font=(self.F_UI, 11))
        txt.configure(state="normal" if editable else "disabled")
        self.panels[key] = txt
        self._show_placeholder(key)
        return f

    def _build_status(self) -> None:
        bar = tk.Frame(self.root, bg=C["bg"])
        if self.theme == theme.THEME_NEW:
            bar.pack(side="bottom", fill="x", padx=16, pady=(0, 8))
        else:
            bar.pack(fill="x", padx=16, pady=(0, 8))
        self._status_bar = bar
        self.status_avatar = tk.Label(bar, bg=C["bg"], bd=0)
        self.status_avatar.pack(side="left", padx=(0, 8))
        _start_icon = getattr(self, "_status_icons", {}).get("reimu")
        if _start_icon is not None:
            self.status_avatar.configure(image=_start_icon)
        self.status_var = tk.StringVar(value=TIPS["ready"])
        self.status_label = tk.Label(bar, textvariable=self.status_var, bg=C["bg"], fg=C["muted"],
                                     font=(self.F_UI, 10), anchor="w")
        self.status_label.pack(side="left")
        self.meta_var = tk.StringVar(value="")
        tk.Label(bar, textvariable=self.meta_var, bg=C["bg"], fg=C["gold"],
                 font=(self.F_UI, 10), anchor="e").pack(side="right")

    # ------------------------------------------------------------------ 设置面板
    def _open_activation(self) -> None:
        from modules import license as lic

        if lic.status()[0]:
            messagebox.showinfo(APP_TITLE, "这台机器已经在博麗神社登记过了。")
            return
        show_activation(self.root, "灵梦：把新拿到的咒文贴进来吧。")

    def _fmt_tokens(self, n: int) -> str:
        n = int(n or 0)
        if n >= 1_000_000:
            return f"{n / 1_000_000:.2f}M"
        if n >= 1000:
            return f"{n / 1000:.1f}k"
        return str(n)

    def _cost_text(self, model: str, usage: dict) -> str:
        """本次调用的香火钱文案。"""
        try:
            from modules import usage as _usage

            pin, pout = _usage.price_for(model)
            u = usage or {}
            cost = ((u.get("prompt_tokens") or 0) / 1e6 * pin
                    + (u.get("completion_tokens") or 0) / 1e6 * pout)
            return f"香火钱 {self._fmt_cost(cost)}（本次调用花费）"
        except Exception:
            return ""

    def _fmt_cost(self, c: float) -> str:
        c = float(c or 0)
        return f"¥{c:.4f}" if c < 1 else f"¥{c:.2f}"

    def _on_usage_record(self, _row: dict) -> None:
        # 可能来自工作线程：只往队列里塞事件，由 _pump 在主线程刷新
        try:
            from modules import usage as _usage

            d = _usage.summary()
            text = (
                f"今日 {d['today']['calls']} 抽 · {self._fmt_tokens(d['today']['tokens'])} 灵"
                f" · {self._fmt_cost(d['today']['cost'])}"
            )
            self.q.put(("meta", text))
        except Exception:
            pass

    def _refresh_usage_meta(self) -> None:
        try:
            from modules import usage as _usage

            d = _usage.summary()
            self.meta_var.set(
                f"今日 {d['today']['calls']} 抽 · {self._fmt_tokens(d['today']['tokens'])} 灵"
                f" · {self._fmt_cost(d['today']['cost'])}"
            )
        except Exception:
            pass

    def _open_usage(self) -> None:
        from modules import usage as _usage

        win = tk.Toplevel(self.root)
        win.title("博麗神社 · 香火钱账本")
        win.configure(bg=C["bg"])
        win.transient(self.root)
        win.geometry(f"960x860+{self.root.winfo_rootx() + 30}+{self.root.winfo_rooty() + 10}")

        tk.Label(win, text="博麗神社 · 香火钱账本", bg=C["bg"], fg=C["gold"],
                 font=(self.F_UI, 18, "bold")).pack(pady=(14, 0))
        tk.Label(win, text="～ 用掉多少灵力，账上都有数 ～", bg=C["bg"], fg=C["muted"],
                 font=(self.F_JP, 10)).pack(pady=(0, 8))

        data = _usage.summary()

        cards = tk.Frame(win, bg=C["bg"])
        cards.pack(fill="x", padx=18)

        def card(title: str, value: str, note: str) -> None:
            f = tk.Frame(cards, bg=C["panel"], highlightbackground=C["border"],
                         highlightthickness=1)
            f.pack(side="left", expand=True, fill="x", padx=(0, 8))
            tk.Label(f, text=title, bg=C["panel"], fg=C["muted"],
                     font=(self.F_UI, 9)).pack(anchor="w", padx=12, pady=(8, 0))
            tk.Label(f, text=value, bg=C["panel"], fg=C["gold"],
                     font=(self.F_MONO, 16, "bold")).pack(anchor="w", padx=12)
            tk.Label(f, text=note, bg=C["panel"], fg=C["muted"],
                     font=(self.F_UI, 8)).pack(anchor="w", padx=12, pady=(0, 8))

        card("今日香火钱", self._fmt_cost(data["today"]["cost"]), "今天花掉多少（估算）")
        card("累计香火钱", self._fmt_cost(data["total"]["cost"]), "总共花掉多少（估算）")
        card("今日灵力", self._fmt_tokens(data["today"]["tokens"]), "今天的 tokens 消耗")
        card("累计抽符", str(data["total"]["calls"]), "一共调用了几次 API")

        chart = _usage.render_chart(data["by_day"])
        photo = ImageTk.PhotoImage(chart)
        lbl = tk.Label(win, image=photo, bg=C["bg"])
        lbl.image = photo
        lbl.pack(padx=18, pady=(10, 0), anchor="w")
        tk.Label(win, text="近 30 天香火钱（每天花掉多少）", bg=C["bg"], fg=C["muted"],
                 font=(self.F_UI, 9)).pack(anchor="w", padx=22)

        body = tk.Frame(win, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=18, pady=(8, 0))
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # 左：式神（模型）统计
        left = tk.Frame(body, bg=C["panel"], highlightbackground=C["border"],
                        highlightthickness=1)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        tk.Label(left, text="式神账目（每个模型的消耗）", bg=C["panel"], fg=C["gold"],
                 font=(self.F_UI, 10, "bold")).pack(anchor="w", padx=10, pady=(8, 4))
        head = tk.Frame(left, bg=C["panel"])
        head.pack(fill="x", padx=10)
        for text, w in (("式神", 18), ("抽符", 6), ("灵力", 8), ("香火钱", 9)):
            tk.Label(head, text=text, width=w, bg=C["panel"], fg=C["muted"],
                     font=(self.F_UI, 8), anchor="w").pack(side="left")
        for model, info in data["by_model"][:10]:
            row = tk.Frame(left, bg=C["panel"])
            row.pack(fill="x", padx=10, pady=1)
            tk.Label(row, text=model[:18], width=18, bg=C["panel"], fg=C["text"],
                     font=(self.F_MONO, 9), anchor="w").pack(side="left")
            tk.Label(row, text=str(info["calls"]), width=6, bg=C["panel"], fg=C["text"],
                     font=(self.F_MONO, 9), anchor="w").pack(side="left")
            tk.Label(row, text=self._fmt_tokens(info["tokens"]), width=8, bg=C["panel"],
                     fg=C["text"], font=(self.F_MONO, 9), anchor="w").pack(side="left")
            tk.Label(row, text=self._fmt_cost(info["cost"]), width=9, bg=C["panel"],
                     fg=C["gold"], font=(self.F_MONO, 9), anchor="w").pack(side="left")

        # 右：最近的抽符记录
        right = tk.Frame(body, bg=C["panel"], highlightbackground=C["border"],
                         highlightthickness=1)
        right.grid(row=0, column=1, sticky="nsew")
        tk.Label(right, text="最近的法术记录（每次调用）", bg=C["panel"], fg=C["gold"],
                 font=(self.F_UI, 10, "bold")).pack(anchor="w", padx=10, pady=(8, 4))
        txt = tk.Text(right, bg=C["panel2"], fg=C["text"], relief="flat", bd=0,
                      font=(self.F_MONO, 9), padx=8, pady=6, height=10)
        txt.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        lines = []
        for r in data["recent"]:
            ts = time.strftime("%m-%d %H:%M", time.localtime(int(r.get("t", 0))))
            lines.append(
                f"{ts}  {str(r.get('model', ''))[:14]:<14} "
                f"{self._fmt_tokens(r.get('tokens', 0)):>6} 灵 "
                f"{float(r.get('sec') or 0):>5.1f}s  {self._fmt_cost(r.get('cost', 0))}"
            )
        txt.insert("1.0", "\n".join(lines) if lines else "（还没有记录，先去退治一题吧）")
        txt.configure(state="disabled")

        btns = tk.Frame(win, bg=C["bg"])
        btns.pack(fill="x", padx=18, pady=10)

        def do_export() -> None:
            dest = filedialog.asksaveasfilename(
                parent=win, title="抄录香火钱账本", defaultextension=".csv",
                filetypes=[("CSV 账本", "*.csv")])
            if not dest:
                return
            try:
                n = _usage.export_csv(dest)
                messagebox.showinfo("香火钱账本", f"已抄录 {n} 条记录到：\n{dest}", parent=win)
            except Exception as e:
                messagebox.showerror("香火钱账本", f"抄录失败：{e}", parent=win)

        tk.Button(btns, text="抄录账本（导出 CSV）", command=do_export, bg=C["panel2"],
                  fg=C["text"], activebackground=C["accent_dark"], activeforeground="#ffffff",
                  relief="flat", bd=0, padx=16, pady=5, cursor="hand2",
                  font=(self.F_UI, 10)).pack(side="left")
        tk.Button(btns, text="关上账本", command=win.destroy, bg=C["accent"], fg="#ffffff",
                  activebackground=C["accent_dark"], activeforeground="#ffffff",
                  relief="flat", bd=0, padx=18, pady=5, cursor="hand2",
                  font=(self.F_UI, 10, "bold")).pack(side="right")
        tk.Label(win, text="灵力 = tokens；香火钱按参考单价估算，实际以平台账单为准。",
                 bg=C["bg"], fg=C["muted"], font=(self.F_UI, 8)).pack(anchor="w", padx=22, pady=(0, 8))

    # ------------------------------------------------------------ 首次安装/引路
    def _reload_credentials_into_ui(self) -> None:
        try:
            fresh = settings.load()
            for key in ("base_url", "api_key", "model", "vision_model",
                        "vision_base_url", "vision_api_key", "provider"):
                if key in fresh:
                    self.cfg[key] = fresh[key]
            self.base_var.set(str(self.cfg.get("base_url") or ""))
            self.key_var.set(str(self.cfg.get("api_key") or ""))
            self.model_var.set(str(self.cfg.get("model") or ""))
            self.vision_var.set(str(self.cfg.get("vision_model") or "（使用答题模型）"))
            self.vision_base_var.set(str(self.cfg.get("vision_base_url") or ""))
            self.vision_key_var.set(str(self.cfg.get("vision_api_key") or ""))
            if self.model_var.get():
                self._models = [self.model_var.get()]
        except Exception:
            pass

    def _on_setup_progress(self, step: int) -> None:
        try:
            self.cfg["onboarding_state"] = first_run.STATE_IN_PROGRESS
            self.cfg["onboarding_resume_step"] = max(1, min(9, int(step)))
            settings.save(self.cfg)
        except Exception:
            pass

    def start_setup_wizard(self, start_step: int = 1) -> None:
        if self._setup_win is not None and getattr(self._setup_win, "winfo_exists", lambda: False)():
            try:
                self._setup_win.lift()
            except Exception:
                pass
            return
        self._setup_win = setup_wizard.SetupWizard(
            self, self._on_setup_done, start_step=start_step,
            on_progress=self._on_setup_progress)

    def _on_setup_done(self, result: dict) -> None:
        self._setup_win = None
        if result.get("cancelled"):
            self._boot_log("first-run setup cancelled")
            try:
                self.root.destroy()
            except Exception:
                pass
            return
        if result.get("skipped"):
            self.cfg["onboarding_api_skipped"] = True
        else:
            self.cfg["onboarding_api_skipped"] = bool(result.get("api_skipped"))
            self._reload_credentials_into_ui()
        try:
            first_run.mark_in_progress(self.cfg, 4)
            settings.save(self.cfg)
        except Exception:
            pass
        self.root.after(180, lambda: self.open_onboarding(manual=False, start_step=1))

    def _on_onboarding_done(self, skipped: bool = False) -> None:
        self._onboarding_win = None
        if not self._manual_onboarding:
            try:
                first_run.mark_done(self.cfg, settings.APP_VERSION,
                                    bool(self.cfg.get("onboarding_api_skipped")))
                settings.save(self.cfg)
            except Exception:
                pass
        self._manual_onboarding = False
        self._reload_credentials_into_ui()
        try:
            if skipped:
                self._status("引路先跳过——之后随时可以在设置里重看。", "warn")
            else:
                self._status("引路完成。结界已记住你的选择。", "ok")
        except Exception:
            pass

    def _on_onboarding_progress(self, step: int) -> None:
        if self._manual_onboarding:
            return
        try:
            self.cfg["onboarding_state"] = first_run.STATE_IN_PROGRESS
            self.cfg["onboarding_resume_step"] = max(4, min(9, 3 + int(step)))
            settings.save(self.cfg)
        except Exception:
            pass

    def open_onboarding(self, manual: bool = True, start_step: int = 1) -> None:
        if self._onboarding_win is not None and getattr(
                self._onboarding_win, "winfo_exists", lambda: False)():
            try:
                self._onboarding_win.lift()
            except Exception:
                pass
            return
        self._manual_onboarding = bool(manual)
        self._onboarding_win = onboarding.OnboardingWizard(
            self, self._on_onboarding_done, start_step=start_step,
            on_progress=self._on_onboarding_progress)

    def maybe_start_first_run(self, pre_access: str, config_existed: bool) -> None:
        self._onboarding_pre_access = pre_access
        self._onboarding_config_existed = config_existed
        if not first_run.should_show(self.cfg, pre_access, config_existed):
            if (not str(self.cfg.get("onboarding_state") or "").strip()
                    and (config_existed or pre_access != "fresh")):
                try:
                    first_run.mark_legacy(self.cfg)
                    settings.save(self.cfg)
                except Exception:
                    pass
            return
        try:
            first_run.mark_pending(self.cfg)
            settings.save(self.cfg)
        except Exception:
            pass
        resume = int(self.cfg.get("onboarding_resume_step") or 1)
        self.root.after(350, lambda: self._start_first_run_resume(resume))

    def _start_first_run_resume(self, resume: int) -> None:
        if resume > first_run.SETUP_STEPS:
            self.open_onboarding(manual=False,
                                 start_step=max(1, min(first_run.ONBOARD_STEPS,
                                                       resume - first_run.SETUP_STEPS)))
        else:
            self.start_setup_wizard(start_step=max(1, min(first_run.SETUP_STEPS, resume)))

    def _open_settings(self) -> None:
        if self._settings_win is not None and self._settings_win.winfo_exists():
            self._settings_win.lift()
            return

        win = tk.Toplevel(self.root)
        self._settings_win = win
        win.title("博麗神社 · 补习班设置")
        win.configure(bg=C["bg"])
        win.transient(self.root)
        win.resizable(False, False)
        _sh = win.winfo_screenheight()
        _h = min(900, _sh - 150)
        win.geometry(f"820x{_h}+{self.root.winfo_rootx() + 60}+{max(8, self.root.winfo_rooty() + 8)}")

        def close_win():
            self._dlg_model_box = None
            self._dlg_vision_box = None
            self._dlg_model_var = None
            try:
                win.destroy()
            except Exception:
                pass


        # 底部按钮固定在窗口底部（不随内容滚动）
        foot = tk.Frame(win, bg=C["bg"])
        foot.pack(side="bottom", fill="x", padx=18, pady=10)

        # 设置内容可滚动，避免小屏幕上底部按钮被裁掉
        outer = tk.Frame(win, bg=C["bg"])
        outer.pack(fill="both", expand=True, padx=14, pady=(10, 0))
        canvas = tk.Canvas(outer, bg=C["bg"], highlightthickness=0, bd=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview,
                            style="Dark.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        wrap = tk.Frame(canvas, bg=C["bg"], padx=4, pady=4)
        _wrap_id = canvas.create_window((0, 0), window=wrap, anchor="nw")

        def _sync_scroll(_e=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _sync_width(e) -> None:
            canvas.itemconfigure(_wrap_id, width=e.width)

        wrap.bind("<Configure>", _sync_scroll)
        canvas.bind("<Configure>", _sync_width)

        def _on_wheel(e) -> None:
            canvas.yview_scroll(int(-e.delta / 120), "units")

        win.bind("<MouseWheel>", _on_wheel)

        def section(title: str) -> tk.Frame:
            box = tk.Frame(wrap, bg=C["bg"])
            box.pack(fill="x", pady=(0, 12))
            tk.Label(box, text=f"❀ {title}", bg=C["bg"], fg=C["gold"],
                     font=(self.F_TITLE, 14), anchor="w").pack(fill="x", pady=(0, 6))
            grid = tk.Frame(box, bg=C["bg"])
            grid.pack(fill="x")
            grid.columnconfigure(1, weight=1)
            return grid

        def add_row(grid: tk.Frame, row: int, label: str, widget, hint: str = "") -> None:
            tk.Label(grid, text=label, bg=C["bg"], fg=C["muted"], anchor="e", width=10,
                     font=(self.F_UI, 10)).grid(row=row, column=0, sticky="e", padx=(0, 10), pady=4)
            widget.grid(row=row, column=1, sticky="ew", pady=3)
            if hint:
                tk.Label(grid, text=hint, bg=C["bg"], fg=C["muted"],
                         font=(self.F_UI, 9)).grid(row=row, column=2, sticky="w", padx=(8, 0))

        # --- 主题 ---
        g_theme = section("主题")
        unlocked = bool(self.cfg.get("theme_unlocked"))
        theme_var = tk.StringVar(value=self.cfg.get("theme", theme.THEME_CLASSIC))
        trow = tk.Frame(g_theme, bg=C["bg"])
        trow.grid(row=0, column=0, columnspan=3, sticky="w", pady=2)
        tk.Radiobutton(
            trow, text="经典", variable=theme_var, value=theme.THEME_CLASSIC,
            bg=C["bg"], fg=C["text"], selectcolor=C["panel2"],
            activebackground=C["bg"], activeforeground=C["gold"],
            font=(self.F_UI, 10), cursor="hand2",
        ).pack(side="left", padx=(0, 20))
        rb_new = tk.Radiobutton(
            trow, text="新主题「晨午宵绘卷」" + ("" if unlocked else "  🔒"),
            variable=theme_var, value=theme.THEME_NEW,
            bg=C["bg"], fg=C["text"], selectcolor=C["panel2"],
            activebackground=C["bg"], activeforeground=C["gold"],
            font=(self.F_UI, 10), cursor="hand2",
        )
        rb_new.pack(side="left")
        if not unlocked:
            rb_new.configure(state="disabled")
            theme_var.set(theme.THEME_CLASSIC)
        tk.Label(
            g_theme, text="新主题随时段切换主界面与启动画面；解锁后可在经典/晨午宵绘卷之间切换。",
            bg=C["bg"], fg=C["muted"], font=(self.F_UI, 9),
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 4))

        # --- 接口 ---
        g1 = section("灵梦的通信术式（接口）")
        provider_var = tk.StringVar()
        base_var = tk.StringVar(value=self.base_var.get())
        key_var = tk.StringVar(value=self.key_var.get())
        self._dlg_key_var = key_var
        self._dlg_base_var = base_var
        model_var = tk.StringVar(value=self.model_var.get())
        vision_var = tk.StringVar(value=self.vision_var.get())
        effort_var = tk.StringVar(value=self.effort_var.get())
        ocr_var = tk.StringVar(value=self.ocr_var.get())
        trans_var = tk.BooleanVar(value=self.trans_var.get())
        temp_var = tk.DoubleVar(value=self.temp_var.get())
        extra_var = tk.StringVar(value=self.extra_var.get())

        prov = ttk.Combobox(g1, textvariable=provider_var, state="readonly",
                            values=[n for n, _ in llm.PROVIDER_PRESETS], width=18)
        add_row(g1, 0, "结界来源", prov, "模型平台：DeepSeek / OpenAI / 智谱 / 通义")

        def on_provider(_ev=None):
            for n, preset in llm.PROVIDER_PRESETS:
                if n == provider_var.get():
                    base_var.set(preset)

        prov.bind("<<ComboboxSelected>>", on_provider)
        for _n, _preset in llm.PROVIDER_PRESETS:
            if base_var.get().rstrip("/") == _preset.rstrip("/"):
                provider_var.set(_n)
                break
        add_row(g1, 1, "术式坐标", ttk.Entry(g1, textvariable=base_var), "Base URL：接口地址")

        key_row = tk.Frame(g1, bg=C["bg"])
        key_entry = ttk.Entry(key_row, textvariable=key_var, show="•")
        key_entry.pack(side="left", fill="x", expand=True)
        show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(key_row, text="显示", variable=show_var,
                        command=lambda: key_entry.configure(show="" if show_var.get() else "•")
                        ).pack(side="left", padx=(8, 0))
        add_row(g1, 2, "通行密钥", key_row, "API Key（Windows DPAPI 加密保存在本机）")

        model_row = tk.Frame(g1, bg=C["bg"])
        model_row.columnconfigure(0, weight=1)
        model_box = ttk.Combobox(model_row, textvariable=model_var, values=list(self._models))
        model_box.grid(row=0, column=0, sticky="ew")

        def refresh_models():
            base = base_var.get().strip()
            key = key_var.get().strip()

            def work():
                try:
                    models = llm.list_models(base, key)
                except Exception as e:
                    self.q.put(("models_error", str(e)))
                    return
                self.q.put(("models", models))

            self._status("魔理沙：正在向平台要模型列表…", "info")
            threading.Thread(target=work, daemon=True).start()

        ttk.Button(model_row, text="刷新", command=refresh_models, width=6).grid(row=0, column=1, padx=(8, 0))
        add_row(g1, 3, "退治式神", model_row, "答题用的模型")
        self._dlg_model_box = model_box
        self._dlg_model_var = model_var

        vision_box = ttk.Combobox(g1, textvariable=vision_var,
                                  values=["（使用答题模型）"] + list(self._models))
        add_row(g1, 4, "读图式神", vision_box, "识图用的多模态模型")
        self._dlg_vision_box = vision_box

        vision_base_var = tk.StringVar(value=self.vision_base_var.get())
        add_row(g1, 5, "读图坐标", ttk.Entry(g1, textvariable=vision_base_var), "视觉接口，留空=用主接口")

        vision_key_var = tk.StringVar(value=self.vision_key_var.get())
        vk_row = tk.Frame(g1, bg=C["bg"])
        vk_entry = ttk.Entry(vk_row, textvariable=vision_key_var, show="•")
        vk_entry.pack(side="left", fill="x", expand=True)
        vk_show = tk.BooleanVar(value=False)
        ttk.Checkbutton(vk_row, text="显示", variable=vk_show,
                        command=lambda: vk_entry.configure(show="" if vk_show.get() else "•")
                        ).pack(side="left", padx=(8, 0))
        add_row(g1, 6, "读图密钥", vk_row, "视觉 Key，留空=用主 Key")

        add_row(g1, 7, "灵力强度", ttk.Combobox(g1, textvariable=effort_var, state="readonly",
                                              values=[label for label, _ in llm.EFFORT_OPTIONS]),
                "推理强度（越高越慢、越稳）")
        add_row(g1, 8, "读符方式", ttk.Combobox(g1, textvariable=ocr_var, state="readonly",
                                               values=["自动", "视觉模型", "本地 OCR"]),
                "自动 = 视觉优先，失败转本地")

        row7 = tk.Frame(g1, bg=C["bg"])
        ttk.Checkbutton(row7, text="英文题自动翻译", variable=trans_var).pack(side="left")
        tk.Label(row7, text="温度", bg=C["bg"], fg=C["muted"], font=(self.F_UI, 10)).pack(side="left", padx=(18, 4))
        ttk.Spinbox(row7, from_=0.0, to=1.0, increment=0.1, textvariable=temp_var, width=5).pack(side="left")
        add_row(g1, 9, "其它术式", row7, "英文题自动翻译 / 温度")

        add_row(g1, 10, "附加咒文", ttk.Entry(g1, textvariable=extra_var), "JSON，可留空")

        balance_row = tk.Frame(g1, bg=C["bg"])
        balance_var = tk.StringVar(value="点上面的按钮，翻翻钱包还剩多少")
        balance_btn = ttk.Button(balance_row, text="查香火钱")
        balance_btn.pack(side="left")
        balance_lbl = tk.Label(g1, textvariable=balance_var, bg=C["bg"],
                               fg=C["muted"], font=(self.F_UI, 9), anchor="w",
                               justify="left", wraplength=600)
        balance_lbl.grid(row=12, column=1, columnspan=2, sticky="ew", pady=(2, 6))
        Tooltip(balance_btn, "查询 API 余额（DeepSeek / OpenAI / Moonshot / OpenRouter / 通用接口）")

        def do_balance() -> None:
            balance_var.set("灵梦：正在翻钱包…")
            balance_lbl.configure(fg=C["muted"])
            balance_btn.configure(state="disabled")

            def done(text: str, ok: bool) -> None:
                balance_var.set(text)
                balance_lbl.configure(fg=C["ok"] if ok else C["err"])
                try:
                    balance_btn.configure(state="normal")
                except Exception:
                    pass

            self._check_balance_async(key_var.get().strip(), base_var.get().strip(), done)

        balance_btn.configure(command=do_balance)
        add_row(g1, 11, "香火钱", balance_row, "API 余额（多平台）")

        # --- 文文的号外 ---
        g3 = section("文文的号外（自动检查更新）")
        upd_on = tk.BooleanVar(value=self.update_enabled_var.get())
        add_row(g3, 0, "自动打听",
                ttk.Checkbutton(g3, text="让文文定期去打听新版本", variable=upd_on),
                "关掉就完全手动")

        ch_var = tk.StringVar(value=self.update_channel_var.get())
        add_row(g3, 1, "报信路线",
                ttk.Combobox(g3, textvariable=ch_var, state="readonly",
                             values=list(self.CHANNEL_LABELS.values())),
                "Gitee 国内快，GitHub 是主仓库")

        int_row = tk.Frame(g3, bg=C["bg"])
        int_var = tk.StringVar(value=self.update_interval_var.get())
        ttk.Combobox(int_row, textvariable=int_var, state="readonly", width=10,
                     values=list(self.INTERVAL_LABELS.values()) + ["自定义"]).pack(side="left")
        custom_var = tk.IntVar(value=int(self.update_custom_var.get()))
        ttk.Spinbox(int_row, from_=1, to=720, textvariable=custom_var,
                    width=6).pack(side="left", padx=(8, 2))
        tk.Label(int_row, text="小时", bg=C["bg"], fg=C["muted"],
                 font=(self.F_UI, 9)).pack(side="left")
        add_row(g3, 2, "报信间隔", int_row, "多久打听一次；自定义填小时")

        sn_row = tk.Frame(g3, bg=C["bg"])
        self._snooze_var = tk.StringVar()
        tk.Label(sn_row, textvariable=self._snooze_var, bg=C["bg"], fg=C["gold"],
                 font=(self.F_UI, 9)).pack(side="left")
        for text, cmd in (("选日子", self._pick_snooze),
                          ("歇 3 天", lambda: self._snooze_days(3)),
                          ("歇 7 天", lambda: self._snooze_days(7))):
            tk.Button(sn_row, text=text, command=cmd, bg=C["panel2"], fg=C["text"],
                      activebackground=C["accent_dark"], activeforeground="#ffffff",
                      relief="flat", bd=0, padx=8, pady=1, cursor="hand2",
                      font=(self.F_UI, 9)).pack(side="left", padx=(8, 0))
        add_row(g3, 3, "封笔到", sn_row, "暂停自动打听；手动不受影响")

        lc_row = tk.Frame(g3, bg=C["bg"])
        self._update_last_var = tk.StringVar()
        tk.Label(lc_row, textvariable=self._update_last_var, bg=C["bg"], fg=C["muted"],
                 font=(self.F_UI, 9)).pack(side="left")
        tk.Button(lc_row, text="立即打听",
                  command=lambda: self._check_updates(manual=True),
                  bg=C["panel2"], fg=C["text"], activebackground=C["accent_dark"],
                  activeforeground="#ffffff", relief="flat", bd=0, padx=10, pady=1,
                  cursor="hand2", font=(self.F_UI, 9)).pack(side="left", padx=(10, 0))
        add_row(g3, 4, "上次打听", lc_row, "最近一次检查结果")

        thr_row = tk.Frame(g3, bg=C["bg"])
        thr_var = tk.IntVar(value=int(self.update_max_threads_var.get()))
        ttk.Spinbox(thr_row, from_=1, to=32, textvariable=thr_var,
                    width=6).pack(side="left")
        tk.Label(thr_row, text="个线程", bg=C["bg"], fg=C["muted"],
                 font=(self.F_UI, 9)).pack(side="left", padx=(6, 0))
        add_row(g3, 5, "最多分片", thr_row,
                "1–32；服务器不支持 Range 时自动降为 1 线程")
        self._refresh_update_labels()

        # --- 式神的传讯 ---
        g4 = section("式神的传讯（Windows 通知）")
        toast_on = tk.BooleanVar(value=self.toast_enabled_var.get())
        add_row(g4, 0, "传讯",
                ttk.Checkbutton(g4, text="启用式神传讯", variable=toast_on),
                "系统通知总开关")

        flags_row = tk.Frame(g4, bg=C["bg"])
        toast_upd = tk.BooleanVar(value=self.toast_update_var.get())
        toast_trial = tk.BooleanVar(value=self.toast_trial_var.get())
        toast_bal = tk.BooleanVar(value=self.toast_balance_var.get())
        toast_auto = tk.BooleanVar(value=self.toast_auto_var.get())
        for text, var in (("号外", toast_upd), ("结界", toast_trial),
                          ("香火钱", toast_bal), ("退治", toast_auto)):
            ttk.Checkbutton(flags_row, text=text, variable=var).pack(
                side="left", padx=(0, 12))
        add_row(g4, 1, "栏目", flags_row, "号外 / 试用 / 余额 / 退治")

        quiet_row = tk.Frame(g4, bg=C["bg"])
        quiet_start = tk.IntVar(value=self.toast_quiet_start_var.get())
        quiet_end = tk.IntVar(value=self.toast_quiet_end_var.get())
        tk.Label(quiet_row, text="从", bg=C["bg"], fg=C["muted"],
                 font=(self.F_UI, 9)).pack(side="left")
        ttk.Spinbox(quiet_row, from_=0, to=23, textvariable=quiet_start,
                    width=4).pack(side="left", padx=3)
        tk.Label(quiet_row, text="点到", bg=C["bg"], fg=C["muted"],
                 font=(self.F_UI, 9)).pack(side="left")
        ttk.Spinbox(quiet_row, from_=0, to=23, textvariable=quiet_end,
                    width=4).pack(side="left", padx=3)
        tk.Label(quiet_row, text="点", bg=C["bg"], fg=C["muted"],
                 font=(self.F_UI, 9)).pack(side="left")
        add_row(g4, 2, "打盹", quiet_row, "安静时段不打扰；结界到期除外")

        add_row(g4, 3, "试听",
                ttk.Button(g4, text="让式神传一声", command=self._test_toast),
                "弹一条测试通知")

        # --- 抓取 ---
        g2 = section("退治的结界术式（截取）")
        method_var = tk.StringVar(value=self.method_var.get())
        minimize_var = tk.BooleanVar(value=self.minimize_var.get())
        interval_var = tk.DoubleVar(value=self.interval_var.get())
        settle_var = tk.DoubleVar(value=self.settle_var.get())
        threshold_var = tk.DoubleVar(value=self.threshold_var.get())

        add_row(g2, 0, "抽符方式", ttk.Combobox(g2, textvariable=method_var, state="readonly",
                                              values=["屏幕抓取（所见即所得）", "后台抓取（可抓被遮挡窗口）"]))
        rowm = tk.Frame(g2, bg=C["bg"])
        ttk.Checkbutton(rowm, text="截图时本窗口自动让位",
                        variable=minimize_var).pack(side="left")
        add_row(g2, 1, "结界遮蔽", rowm, "截图时本窗口自动让位")

        rowauto = tk.Frame(g2, bg=C["bg"])
        for text, var, lo, hi, inc, w in (
            ("间隔", interval_var, 0.5, 10.0, 0.5, 4),
            ("静置", settle_var, 0.0, 5.0, 0.2, 4),
            ("阈值", threshold_var, 0.2, 20.0, 0.2, 4),
        ):
            tk.Label(rowauto, text=text, bg=C["bg"], fg=C["muted"], font=(self.F_UI, 10)).pack(side="left", padx=(0, 4))
            ttk.Spinbox(rowauto, from_=lo, to=hi, increment=inc, textvariable=var, width=w).pack(
                side="left", padx=(0, 14))
        add_row(g2, 2, "自动监视", rowauto, "间隔 / 静置 / 阈值（秒 / 分数）")

        clip_var = tk.BooleanVar(value=self.clip_var.get())
        rowclip = tk.Frame(g2, bg=C["bg"])
        ttk.Checkbutton(rowclip, text="剪贴板自动识别（Win+Shift+S）",
                        variable=clip_var).pack(side="left")
        add_row(g2, 3, "剪贴符纸", rowclip, "剪贴板自动识别（Win+Shift+S）")

        browser_var = tk.BooleanVar(value=self.browser_only_var.get())
        rowb = tk.Frame(g2, bg=C["bg"])
        ttk.Checkbutton(rowb, text="自动监听只扫浏览器前台",
                        variable=browser_var).pack(side="left")
        add_row(g2, 4, "结界范围", rowb, "自动监听只扫浏览器前台")

        web_port_var = tk.IntVar(value=int(self.web_port_var.get() or 9222))
        roww = tk.Frame(g2, bg=C["bg"])
        tk.Label(roww, text="调试端口", bg=C["bg"], fg=C["muted"], font=(self.F_UI, 10)).pack(side="left")
        ttk.Spinbox(roww, from_=1024, to=65535, textvariable=web_port_var, width=8).pack(
            side="left", padx=(6, 14))
        add_row(g2, 5, "结界入口", roww, "调试端口；『启动答题浏览器.bat』")

        cont_var = tk.BooleanVar(value=self.continue_wrong_var.get())
        rowfull = tk.Frame(g2, bg=C["bg"])
        ttk.Checkbutton(rowfull, text="答错也继续下一题", variable=cont_var).pack(side="left")
        add_row(g2, 6, "退治", rowfull, "答错是否继续下一题（全自动仍需手动点「开始退治」）")


        start_url_var = tk.StringVar(value=self.start_url_var.get())
        url_row = tk.Frame(g2, bg=C["bg"])
        ttk.Entry(url_row, textvariable=start_url_var).pack(side="left", fill="x", expand=True)
        add_row(g2, 8, "入口坐标", url_row, "点「张开结界」时打开这个页面")

        try:
            from modules import license as _lic

            _astate, _amsg, _adays = _lic.check_access(update=False)
            _atext = {"licensed": "已登记（永久许可）",
                      "trial": (f"试用中（还剩 {_adays} 天）" if _adays > 0 else "试用中（最后几小时）"),
                      "fresh": "未登记（可试用 5 天）",
                      "expired": "试用已结束，需要许可",
                      "tampered": "授权记录异常，需要重新登记"}.get(_astate, _amsg)
            _acolor = C["ok"] if _astate == "licensed" else (
                C["warn"] if _astate == "trial" else C["err"])
        except Exception:
            _atext, _acolor = "授权检查失败", C["err"]

        auth_row = tk.Frame(g2, bg=C["bg"])
        tk.Label(auth_row, text=_atext, bg=C["bg"], fg=_acolor,
                 font=(self.F_UI, 9)).pack(side="left")
        tk.Button(auth_row, text="查看许可", command=self._open_activation,
                  bg=C["panel2"], fg=C["text"], activebackground=C["accent_dark"],
                  activeforeground="#ffffff", relief="flat", bd=0,
                  padx=10, pady=1, cursor="hand2",
                  font=(self.F_UI, 9)).pack(side="left", padx=(10, 0))
        add_row(g2, 9, "神社登记", auth_row, f"本机灵符 {_lic.machine_code()}")

        # --- 引路与契约 ---
        g_onboard = section("引路与契约")
        _ostate = str(self.cfg.get("onboarding_state") or "").strip()
        _olabel = {
            first_run.STATE_DONE: "已看过新手引导",
            first_run.STATE_LEGACY: "老用户升级，不自动弹出",
            first_run.STATE_IN_PROGRESS: "契约/引路还没走完",
            first_run.STATE_PENDING: "契约/引路还没走完",
        }.get(_ostate, "尚未走过契约与引路")
        tk.Label(g_onboard, text="新手引导只在首次安装出现；想再看一遍，可以随时从这里重新打开。",
                 bg=C["bg"], fg=C["muted"], anchor="w", justify="left",
                 font=(self.F_UI, 9)).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        _orow = tk.Frame(g_onboard, bg=C["bg"])
        _orow.grid(row=1, column=0, columnspan=3, sticky="w")
        tk.Button(_orow, text="重看新手引导", command=lambda: (
            close_win(), self.open_onboarding(manual=True)),
                  bg=C["gold"], fg="#241b12", activebackground="#f0d486",
                  activeforeground="#241b12", relief="flat", bd=0,
                  padx=14, pady=5, cursor="hand2",
                  font=(self.F_UI, 9, "bold")).pack(side="left")
        if _ostate in (first_run.STATE_PENDING, first_run.STATE_IN_PROGRESS):
            tk.Button(_orow, text="继续契约", command=lambda: (
                close_win(), self._start_first_run_resume(
                    int(self.cfg.get("onboarding_resume_step") or 1))),
                      bg=C["panel2"], fg=C["text"], activebackground=C["accent_dark"],
                      activeforeground="#ffffff", relief="flat", bd=0,
                      padx=12, pady=5, cursor="hand2",
                      font=(self.F_UI, 9)).pack(side="left", padx=(10, 0))
        tk.Label(_orow, text=_olabel, bg=C["bg"], fg=C["muted"],
                 font=(self.F_UI, 9)).pack(side="left", padx=(12, 0))

        # foot 已在窗口底部创建
        foot_label = tk.Label(foot, text="通行密钥用 DPAPI 加密保存在本机（即 API Key）。",
                              bg=C["bg"], fg=C["muted"], font=(self.F_UI, 9))

        def save():
            old_theme = self.theme
            self.base_var.set(base_var.get().strip())
            self.key_var.set(key_var.get().strip())
            self.model_var.set(model_var.get().strip())
            self.vision_var.set(vision_var.get().strip() or "（使用答题模型）")
            self.vision_base_var.set(vision_base_var.get().strip())
            self.vision_key_var.set(vision_key_var.get().strip())
            self.effort_var.set(effort_var.get())
            self.ocr_var.set(ocr_var.get())
            self.trans_var.set(bool(trans_var.get()))
            self.temp_var.set(float(temp_var.get() or 0.2))
            self.extra_var.set(extra_var.get().strip())
            self.method_var.set(method_var.get())
            self.minimize_var.set(bool(minimize_var.get()))
            self.interval_var.set(float(interval_var.get() or 1.5))
            self.settle_var.set(float(settle_var.get() or 0.8))
            self.threshold_var.set(float(threshold_var.get() or 1.5))
            self.clip_var.set(bool(clip_var.get()))
            self.browser_only_var.set(bool(browser_var.get()))
            self.web_port_var.set(int(web_port_var.get() or 9222))
            self.continue_wrong_var.set(bool(cont_var.get()))
            self.start_url_var.set(start_url_var.get().strip() or "https://kysu.edu")
            self.update_enabled_var.set(bool(upd_on.get()))
            self.update_channel_var.set(ch_var.get())
            self.update_interval_var.set(int_var.get())
            try:
                self.update_custom_var.set(int(custom_var.get()))
                self.update_max_threads_var.set(max(1, min(32, int(thr_var.get()))))
            except Exception:
                pass
            self.toast_enabled_var.set(bool(toast_on.get()))
            self.toast_update_var.set(bool(toast_upd.get()))
            self.toast_trial_var.set(bool(toast_trial.get()))
            self.toast_balance_var.set(bool(toast_bal.get()))
            self.toast_auto_var.set(bool(toast_auto.get()))
            try:
                self.toast_quiet_start_var.set(int(quiet_start.get()))
                self.toast_quiet_end_var.set(int(quiet_end.get()))
            except Exception:
                pass
            chosen = theme_var.get()
            if chosen == theme.THEME_NEW and not self.cfg.get("theme_unlocked"):
                chosen = theme.THEME_CLASSIC
            self.cfg["theme"] = chosen
            self._save_config()
            close_win()
            self._status(TIPS["saved"], "ok")
            if chosen != old_theme:
                self._request_theme_change(chosen)

        # 打开设置就自动拉一次模型列表（有地址和 key 时）
        if base_var.get().strip() and key_var.get().strip():
            win.after(250, refresh_models)

        btn_row = tk.Frame(foot, bg=C["bg"])
        btn_row.pack(side="right")
        ttk.Button(btn_row, text="保存", command=save).pack(side="right", padx=(8, 0))
        ttk.Button(btn_row, text="取消", command=close_win).pack(side="right")
        foot_label.pack(side="left", fill="x", expand=True)

        win.protocol("WM_DELETE_WINDOW", close_win)
        win.bind("<Escape>", lambda _e: close_win())

    # ------------------------------------------------------------------ 关于
    def _open_url(self, url: str) -> None:
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception:
            pass

    def _about_app(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("关于程序")
        win.configure(bg=C["bg"])
        win.transient(self.root)
        win.geometry(f"660x500+{self.root.winfo_rootx() + 220}+{self.root.winfo_rooty() + 120}")
        win.resizable(False, False)

        tk.Label(win, text="符卡作业簿", bg=C["bg"], fg=C["gold"],
                 font=(self.F_TITLE, 30)).pack(pady=(22, 2))
        tk.Label(win, text="～ 抽符 · 退治 · 收卡 ～", bg=C["bg"], fg=C["muted"],
                 font=(self.F_JP, 11)).pack()
        tk.Label(win, text=f"v{settings.APP_VERSION} · MIT License", bg=C["bg"], fg=C["muted"],
                 font=(self.F_MONO, 10)).pack(pady=(2, 4))
        tk.Label(win, text="本程序代码以 MIT 协议开源，详见项目根目录的 LICENSE 文件。",
                 bg=C["bg"], fg=C["muted"], font=(self.F_UI, 9)).pack(pady=(0, 10))

        body = tk.Frame(win, bg=C["bg"], padx=30)
        body.pack(fill="x")
        lines = [
            ("功能", "截屏识题 · 英文翻译 · AI 作答 · 全自动网页答题"),
            ("号外", f"{self._channel_label()} · 上次打听 {self._last_check_text()}"),
            ("技术", "Python 3 + tkinter + Pillow + CDP 浏览器调试协议"),
            ("支持", "DeepSeek / OpenAI / 智谱 / 通义 / OpenRouter 等兼容接口"),
        ]
        for k, v in lines:
            row = tk.Frame(body, bg=C["bg"])
            row.pack(fill="x", pady=3)
            tk.Label(row, text=k, bg=C["bg"], fg=C["gold"], width=5, anchor="e",
                     font=(self.F_UI, 10, "bold")).pack(side="left")
            tk.Label(row, text=v, bg=C["bg"], fg=C["text"], anchor="w",
                     font=(self.F_UI, 10), justify="left", wraplength=470).pack(
                side="left", padx=(10, 0), fill="x", expand=True)

        tk.Frame(win, bg=C["border"], height=1).pack(fill="x", padx=30, pady=14)
        try:
            from modules import license as _lic

            _ok, _msg = _lic.status()
            if not _ok:
                _state, _amsg, _ = _lic.check_access(update=False)
                _msg = _amsg
            _machine = _lic.machine_code()
        except Exception:
            _msg, _machine = "未授权", "-"

        tk.Label(win, text="© 2025 Shinichi · Fastrof · 会哈气の祥. 保留所有权利。",
                 bg=C["bg"], fg=C["text"], font=(self.F_UI, 10)).pack()
        tk.Label(win, text=f"授权：{_msg}    本机机器码：{_machine}",
                 bg=C["bg"], fg=C["gold"], font=(self.F_MONO[0], 9)).pack(pady=(4, 0))

        gh_row = tk.Frame(win, bg=C["bg"])
        gh_row.pack(pady=(6, 0))
        tk.Label(gh_row, text="GitHub：", bg=C["bg"], fg=C["muted"],
                 font=(self.F_UI, 9)).pack(side="left")
        for idx, (label, url) in enumerate((("Shinichi", "https://github.com/Jerry9335"),
                                             ("Fastrof", "https://github.com/Fastrof"),
                                             ("会哈气の祥", "https://github.com/lic402514-gif"))):
            if idx:
                tk.Label(gh_row, text="  |  ", bg=C["bg"], fg=C["muted"],
                         font=(self.F_UI, 9)).pack(side="left")
            lb = tk.Label(gh_row, text=label, bg=C["bg"], fg=C["gold"], cursor="hand2",
                          font=(self.F_UI, 9, "underline"))
            lb.pack(side="left")
            lb.bind("<Button-1>", lambda _e, u=url: self._open_url(u))
        tk.Label(win,
                 text="东方 Project 角色立绘 / 同人素材版权归 ZUN、上海爱丽丝幻乐团及原作者所有，仅供个人学习使用。",
                 bg=C["bg"], fg=C["muted"], font=(self.F_UI, 9), wraplength=560,
                 justify="center").pack(pady=(6, 0))
        tk.Button(win, text="关闭", command=win.destroy, bg=C["panel2"], fg=C["text"],
                  relief="flat", bd=0, padx=20, pady=5, cursor="hand2",
                  font=(self.F_UI, 10)).pack(pady=16)

        def _fit_about() -> None:
            try:
                win.update_idletasks()
                _sw, _sh = win.winfo_screenwidth(), win.winfo_screenheight()
                _w = min(max(660, win.winfo_reqwidth() + 4), _sw - 40)
                _h = min(max(620, win.winfo_reqheight() + 4), _sh - 80)
                win.geometry(f"{_w}x{_h}+{max(0, (_sw - _w) // 2)}+{max(0, (_sh - _h) // 2)}")
            except Exception:
                pass

        win.after(50, _fit_about)

    def _about_authors(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("关于作者")
        win.configure(bg=C["bg"])
        win.transient(self.root)
        win.geometry(f"720x780+{self.root.winfo_rootx() + 230}+{self.root.winfo_rooty() + 80}")
        win.resizable(False, False)

        tk.Label(win, text="关于作者", bg=C["bg"], fg=C["gold"],
                 font=(self.F_TITLE, 24)).pack(pady=(14, 8))

        cards = tk.Frame(win, bg=C["bg"])
        cards.pack(fill="x")
        people = [
            ("shinichi", "Shinichi", "主开发者", "程序主体 / 截屏识别 / 全自动化",
             "https://github.com/Jerry9335", "GitHub · Jerry9335"),
            ("fastrof", "Fastrof", "副开发者", "界面美术 / 测试 / 素材整理",
             "https://github.com/Fastrof", "GitHub · Fastrof"),
            ("xiang", "会哈气の祥", "开发组成员", "公式调色板 / 矩阵输入 / Bug 修复",
             "https://github.com/lic402514-gif", "GitHub · lic402514-gif"),
        ]
        for key, name, role, desc, gh_url, gh_label in people:
            card = tk.Frame(cards, bg=C["panel"], highlightbackground=C["border"],
                            highlightthickness=1, padx=14, pady=8)
            card.pack(fill="x", padx=72, pady=5)
            img = self._author_imgs.get(key)
            if img is not None:
                tk.Label(card, image=img, bg=C["panel"], bd=0).pack(side="left", padx=(2, 16))
            info = tk.Frame(card, bg=C["panel"])
            info.pack(side="left", fill="both", expand=True, pady=4)
            tk.Label(info, text=name, bg=C["panel"], fg=C["text"],
                     font=(self.F_TITLE, 18), anchor="w").pack(fill="x")
            tk.Label(info, text=role, bg=C["panel"], fg=C["gold"],
                     font=(self.F_UI, 10, "bold"), anchor="w").pack(fill="x", pady=(1, 3))
            tk.Label(info, text=desc, bg=C["panel"], fg=C["muted"],
                     font=(self.F_UI, 9), anchor="w").pack(fill="x")
            link = tk.Label(info, text=gh_label, bg=C["panel"], fg=C["gold"],
                            cursor="hand2", font=(self.F_UI, 9, "underline"), anchor="w")
            link.pack(fill="x", pady=(5, 0))
            link.bind("<Button-1>", lambda _e, u=gh_url: self._open_url(u))

        tk.Label(win, text="感谢游玩，愿幻想乡的作业都被温柔地退治掉。",
                 bg=C["bg"], fg=C["muted"], font=(self.F_UI, 10)).pack(pady=(12, 0))
        tk.Button(win, text="关闭", command=win.destroy, bg=C["panel2"], fg=C["text"],
                  relief="flat", bd=0, padx=20, pady=5, cursor="hand2",
                  font=(self.F_UI, 10)).pack(pady=12)

        def _fit_authors() -> None:
            try:
                win.update_idletasks()
                _sw, _sh = win.winfo_screenwidth(), win.winfo_screenheight()
                _w = min(max(640, win.winfo_reqwidth() + 4), _sw - 40)
                _h = min(max(560, win.winfo_reqheight() + 4), _sh - 80)
                win.geometry(f"{_w}x{_h}+{max(0, (_sw - _w) // 2)}+{max(0, (_sh - _h) // 2)}")
            except Exception:
                pass

        win.after(50, _fit_authors)

        seq = theme.KeySequence()

        def _on_author_key(e):
            key = e.keysym
            if key in ("Up", "Down", "Left", "Right"):
                self._author_shake(win, key)
            elif key in ("b", "B"):
                self._author_flash(win, "灵符「梦想封印」", C["accent"])
            elif key in ("a", "A"):
                self._author_flash(win, "恋符「Master Spark」", "#7a5cff")
            try:
                if seq.feed(key):
                    self._unlock_theme(win)
            except Exception:
                pass

        win.bind("<Key>", _on_author_key)
        win.after(150, win.focus_force)

    def _author_shake(self, win: tk.Toplevel, key: str) -> None:
        """方向键让关于作者窗口轻轻晃一下。"""
        offsets = {
            "Up": (0, -10), "Down": (0, 10),
            "Left": (-10, 0), "Right": (10, 0),
        }
        if key not in offsets:
            return
        try:
            if not win.winfo_exists():
                return
            base = getattr(win, "_shake_base", None)
            if base is None:
                base = (win.winfo_x(), win.winfo_y())
                win._shake_base = base
            for job in getattr(win, "_shake_jobs", []):
                try:
                    win.after_cancel(job)
                except Exception:
                    pass
            win._shake_jobs = []
            dx, dy = offsets[key]
            steps = [(dx, dy), (int(dx * 0.55), int(dy * 0.55)), (0, 0)]

            def step(i: int = 0) -> None:
                if not win.winfo_exists():
                    return
                ox, oy = steps[i]
                win.geometry(f"+{base[0] + ox}+{base[1] + oy}")
                if i + 1 < len(steps):
                    job = win.after(28, lambda: step(i + 1))
                    win._shake_jobs.append(job)
                else:
                    win._shake_jobs = []
                    win.after(300, lambda: setattr(win, "_shake_base", None))

            step()
        except Exception:
            pass

    def _author_flash(self, win: tk.Toplevel, spell: str, color: str) -> None:
        """B / A 闪一下并显示对应符卡名。"""
        try:
            if not win.winfo_exists():
                return
            old = getattr(win, "_spell_flash", None)
            if old is not None:
                try:
                    old.destroy()
                except Exception:
                    pass
            frame = tk.Frame(win, bg=color, bd=0, highlightthickness=0)
            frame.place(x=0, y=0, relwidth=1, relheight=1)
            frame.lift()
            label = tk.Label(frame, text=spell, bg=color, fg="#fffaf6",
                             font=(self.F_TITLE, 24, "bold"))
            label.pack(expand=True)
            win._spell_flash = frame

            def step(i: int) -> None:
                if not frame.winfo_exists():
                    return
                bg = color if i % 2 == 0 else "#fffaf6"
                fg = "#fffaf6" if i % 2 == 0 else "#1a1020"
                frame.configure(bg=bg)
                label.configure(bg=bg, fg=fg)
                if i < 3:
                    win.after(70, lambda: step(i + 1))
                else:
                    win.after(160, _end)

            def _end() -> None:
                try:
                    if frame.winfo_exists():
                        frame.destroy()
                except Exception:
                    pass
                try:
                    win._spell_flash = None
                except Exception:
                    pass

            step(0)
        except Exception:
            pass

    def _unlock_theme(self, parent: tk.Toplevel) -> None:
        if self.cfg.get("theme_unlocked") and self.theme == theme.THEME_NEW:
            self._status("紫：晨午宵绘卷早就解锁了，别把结界敲坏。", "info")
            return
        self.cfg["theme_unlocked"] = True
        self.cfg["theme"] = theme.THEME_NEW
        self._save_config()
        self._status("紫：新主题「晨午宵绘卷」已解锁。正在换装……", "ok")
        self._request_theme_change(theme.THEME_NEW)

    # ------------------------------------------------------------------ 配置
    def _apply_config(self) -> None:
        c = self.cfg
        self.base_var = tk.StringVar(value=c.get("base_url", "https://api.deepseek.com/v1"))
        self.key_var = tk.StringVar(value=c.get("api_key", ""))
        self.model_var = tk.StringVar(value=c.get("model", ""))
        vision = c.get("vision_model") or "（使用答题模型）"
        self.vision_var = tk.StringVar(value=vision)
        effort = c.get("effort", "自动（默认）")
        if effort not in [label for label, _ in llm.EFFORT_OPTIONS]:
            effort = "自动（默认）"
        self.effort_var = tk.StringVar(value=effort)
        ocr = c.get("ocr_mode")
        self.ocr_var = tk.StringVar(value=ocr if ocr in ("自动", "视觉模型", "本地 OCR") else "自动")
        self.trans_var = tk.BooleanVar(value=bool(c.get("translate", True)))
        self.temp_var = tk.DoubleVar(value=float(c.get("temperature", 0.2)))
        self.extra_var = tk.StringVar(value=c.get("extra_json", ""))
        _m = c.get("capture_method") or ""
        if _m.startswith("后台") or _m == "window":
            _m = "后台抓取（可抓被遮挡窗口）"
        else:
            _m = "屏幕抓取（所见即所得）"
        self.method_var = tk.StringVar(value=_m)
        self.minimize_var = tk.BooleanVar(value=bool(c.get("minimize_on_capture", False)))
        self.interval_var = tk.DoubleVar(value=float(c.get("auto_interval", 1.5)))
        self.settle_var = tk.DoubleVar(value=float(c.get("auto_settle", 0.8)))
        self.threshold_var = tk.DoubleVar(value=float(c.get("auto_threshold", 1.5)))
        self.vision_base_var = tk.StringVar(value=c.get("vision_base_url", "") or "")
        self.vision_key_var = tk.StringVar(value=c.get("vision_api_key", "") or "")
        self.web_port_var = tk.IntVar(value=int(c.get("web_port", 9222) or 9222))
        self.continue_wrong_var = tk.BooleanVar(value=bool(c.get("web_continue_on_wrong", True)))
        # 全自动必须手动点「开始退治」才启动；旧配置里的 web_autostart 不再生效。
        self.autostart_var = tk.BooleanVar(value=False)
        self.start_url_var = tk.StringVar(value=c.get("web_start_url", "https://kysu.edu") or "https://kysu.edu")
        if getattr(self, "clip_var", None) is None:
            self.clip_var = tk.BooleanVar(value=bool(c.get("clipboard_on", True)))
        else:
            self.clip_var.set(bool(c.get("clipboard_on", True)))
        self._clip_enabled = bool(c.get("clipboard_on", True))
        self.browser_only_var = tk.BooleanVar(value=bool(c.get("auto_browser_only", True)))

        # 更新
        _ch = c.get("update_channel") or "auto"
        self.update_enabled_var = tk.BooleanVar(value=bool(c.get("update_enabled", True)))
        self.update_channel_var = tk.StringVar(value=self.CHANNEL_LABELS.get(_ch, self.CHANNEL_LABELS["auto"]))
        _hrs = int(c.get("update_interval_hours") or 5)
        self.update_interval_var = tk.StringVar(value=self.INTERVAL_LABELS.get(_hrs, "自定义"))
        self.update_custom_var = tk.IntVar(value=_hrs if _hrs not in self.INTERVAL_LABELS else 5)
        self._update_last_check = int(c.get("update_last_check") or 0)
        self._update_snooze_until = int(c.get("update_snooze_until") or 0)
        self._update_last_version = str(c.get("update_last_version") or "")
        self.update_max_threads_var = tk.IntVar(
            value=max(1, min(32, int(c.get("update_max_threads") or 8))))
        self._toast_seen = dict(c.get("toast_seen") or {})
        # 通知
        self.toast_enabled_var = tk.BooleanVar(value=bool(c.get("toast_enabled", True)))
        self.toast_update_var = tk.BooleanVar(value=bool(c.get("toast_update", True)))
        self.toast_trial_var = tk.BooleanVar(value=bool(c.get("toast_trial", True)))
        self.toast_balance_var = tk.BooleanVar(value=bool(c.get("toast_balance", True)))
        self.toast_auto_var = tk.BooleanVar(value=bool(c.get("toast_auto", True)))
        self.toast_quiet_start_var = tk.IntVar(value=int(c.get("toast_quiet_start", 23)))
        self.toast_quiet_end_var = tk.IntVar(value=int(c.get("toast_quiet_end", 8)))

        reg = c.get("region")
        if isinstance(reg, list) and len(reg) == 4:
            self.region = tuple(int(v) for v in reg)  # type: ignore[assignment]
        self.target_title = c.get("window_title", "") or ""

        self.provider_var = tk.StringVar()
        self._models: list[str] = [self.model_var.get()] if self.model_var.get() else []
        if self.region:
            self.window_var.set("整个屏幕")

    def _snapshot_cfg(self) -> dict:
        cfg = dict(self.cfg)
        cfg.update(
            base_url=self.base_var.get().strip(),
            api_key=self.key_var.get(),
            model=self.model_var.get().strip(),
            vision_model="" if self.vision_var.get().startswith("（使用") else self.vision_var.get().strip(),
            vision_base_url=self.vision_base_var.get().strip(),
            vision_api_key=self.vision_key_var.get().strip(),
            effort=self.effort_var.get(),
            ocr_mode=self.ocr_var.get(),
            translate=bool(self.trans_var.get()),
            temperature=float(self.temp_var.get() or 0.2),
            extra_json=self.extra_var.get().strip(),
            capture_method=self.method_var.get(),
            region=list(self.region) if self.region else None,
            window_title=self.target_title,
            auto_enabled=bool(self.auto_var.get()),
            auto_interval=float(self.interval_var.get() or 1.5),
            auto_settle=float(self.settle_var.get() or 0.8),
            auto_threshold=float(self.threshold_var.get() or 1.5),
            minimize_on_capture=bool(self.minimize_var.get()),
            web_port=int(self.web_port_var.get() or 9222),
            web_autostart=False,
            web_start_url=self.start_url_var.get().strip(),
            web_continue_on_wrong=bool(self.continue_wrong_var.get()),
            clipboard_on=bool(self.clip_var.get()),
            auto_browser_only=bool(self.browser_only_var.get()),
            update_enabled=bool(self.update_enabled_var.get()),
            update_channel=self._channel_code(),
            update_interval_hours=self._interval_hours(),
            update_max_threads=int(self.update_max_threads_var.get() or 8),
            update_last_check=int(getattr(self, "_update_last_check", 0) or 0),
            update_snooze_until=int(getattr(self, "_update_snooze_until", 0) or 0),
            update_last_version=str(getattr(self, "_update_last_version", "")),
            toast_enabled=bool(self.toast_enabled_var.get()),
            toast_update=bool(self.toast_update_var.get()),
            toast_trial=bool(self.toast_trial_var.get()),
            toast_balance=bool(self.toast_balance_var.get()),
            toast_auto=bool(self.toast_auto_var.get()),
            toast_quiet_start=int(self.toast_quiet_start_var.get()),
            toast_quiet_end=int(self.toast_quiet_end_var.get()),
            toast_seen=dict(getattr(self, "_toast_seen", {}) or {}),
            theme=str(self.cfg.get("theme", theme.THEME_CLASSIC)),
            theme_unlocked=bool(self.cfg.get("theme_unlocked", False)),
            geometry=self.root.geometry(),
        )
        return cfg

    def _save_config(self) -> None:
        try:
            self.cfg = self._snapshot_cfg()
            settings.save(self.cfg)
        except Exception:
            pass

    def _request_theme_change(self, name: str) -> None:
        if name not in (theme.THEME_CLASSIC, theme.THEME_NEW):
            name = theme.THEME_CLASSIC
        if name == self.theme:
            self._pending_theme = None
            return
        self._pending_theme = name
        try:
            busy = bool(self.busy or self.web_on or self.auto_var.get())
        except Exception:
            busy = False
        if busy:
            self._status("紫：正在退治，等这一轮结束再换主题。", "info")
            return
        self._maybe_apply_pending_theme()

    def _maybe_apply_pending_theme(self) -> None:
        name = self._pending_theme
        if not name:
            return
        try:
            if self.busy or self.web_on or self.auto_var.get():
                return
        except Exception:
            pass
        self._pending_theme = None
        self.cfg["theme"] = name
        self._save_config()
        self._status("紫：晨午宵绘卷——换装中，马上重新打开。", "ok")
        self.root.after(500, self._relaunch_for_theme)

    def _relaunch_for_theme(self) -> None:
        if self._relaunching:
            return
        self._relaunching = True
        try:
            if getattr(sys, "frozen", False):
                cmd = [sys.executable] + sys.argv[1:]
            else:
                py = sys.executable
                pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
                if os.path.exists(pyw):
                    py = pyw
                cmd = [py, os.path.join(HERE, "app.pyw")] + sys.argv[1:]
            flags = 0x00000008 if os.name == "nt" else 0
            subprocess.Popen(cmd, cwd=HERE, creationflags=flags)
        except Exception as e:
            self._relaunching = False
            self._status(f"紫：主题重启失败……{e}", "err")
            return
        try:
            self.root.destroy()
        except Exception:
            pass

    # ------------------------------------------------------------------ 更新 / 通知
    CHANNEL_LABELS = {
        "auto": "自动（Gitee 优先）",
        "gitee": "仅 Gitee（人间之里）",
        "github": "仅 GitHub（外界神社）",
    }
    INTERVAL_LABELS = {0: "每次启动", 5: "5 小时", 24: "每天", 72: "每三天", 168: "每周"}

    def _channel_code(self) -> str:
        label = self.update_channel_var.get() if getattr(self, "update_channel_var", None) else ""
        for code, text in self.CHANNEL_LABELS.items():
            if text == label:
                return code
        return "auto"

    def _channel_label(self) -> str:
        return self.CHANNEL_LABELS.get(self._channel_code(), self.CHANNEL_LABELS["auto"])

    def _interval_hours(self) -> int:
        label = (self.update_interval_var.get()
                 if getattr(self, "update_interval_var", None) else "5 小时")
        for hours, text in self.INTERVAL_LABELS.items():
            if text == label:
                return hours
        try:
            return max(1, min(720, int(self.update_custom_var.get())))
        except Exception:
            return 5

    def _last_check_text(self) -> str:
        ts = int(getattr(self, "_update_last_check", 0) or 0)
        if not ts:
            return "还没打听"
        try:
            return time.strftime("%m-%d %H:%M", time.localtime(ts))
        except Exception:
            return "还没打听"

    def _refresh_update_labels(self) -> None:
        try:
            var = getattr(self, "_snooze_var", None)
            if var is not None:
                until = int(getattr(self, "_update_snooze_until", 0) or 0)
                if until and until > time.time():
                    d = time.localtime(until)
                    left = max(0, int((until - time.time()) // 86400))
                    var.set(f"封笔到 {d.tm_mon} 月 {d.tm_mday} 日（还剩 {left} 天）")
                else:
                    var.set("未封笔")
            var2 = getattr(self, "_update_last_var", None)
            if var2 is not None:
                src = getattr(self, "_update_last_source", "")
                var2.set(self._last_check_text() + (f" · {src}" if src else ""))
        except Exception:
            pass

    def _notify(self, kind: str, title: str, body: str,
                key: str = "", critical: bool = False,
                avatar: str = "reimu", force: bool = False) -> None:
        """线程安全：丢进队列，由主线程决定弹不弹。"""
        self.q.put(("notify", kind, title, body, key, critical, avatar, force))

    def _do_notify(self, kind: str, title: str, body: str,
                   key: str = "", critical: bool = False,
                   avatar: str = "reimu", force: bool = False) -> None:
        from modules import toast as _toast

        if not getattr(self, "toast_enabled_var", None) or not self.toast_enabled_var.get():
            return
        flags = {
            "update": self.toast_update_var,
            "trial": self.toast_trial_var,
            "balance": self.toast_balance_var,
            "auto": self.toast_auto_var,
        }
        flag = flags.get(kind)
        if not force and flag is not None and not flag.get():
            return
        seen = dict(getattr(self, "_toast_seen", {}) or {})
        if not force:
            if not critical and _toast.in_quiet(self.cfg):
                return
            if key and str(seen.get(kind) or "") == key:
                return
        if key:
            seen[kind] = key
            self._toast_seen = seen
            self.cfg["toast_seen"] = seen
            self._save_config()
        threading.Thread(target=_toast.show, args=(title, body), kwargs={"avatar": avatar}, daemon=True).start()

    def _test_toast(self) -> None:
        from modules import toast as _toast
        threading.Thread(
            target=_toast.show,
            args=("博麗神社 · 式神", "灵梦：试音试音——能听见就说明式神没偷懒。"),
            kwargs={"avatar": "reimu"},
            daemon=True,
        ).start()

    def _update_tick(self) -> None:
        try:
            from modules import update as _up
            due = _up.due(self.cfg)
            # 「每次启动」：本次启动查过就不再自动查
            if due and self._interval_hours() == 0 and                     self._update_last_check >= getattr(self, "_launch_time", 0):
                due = False
            if due and not self._update_checking:
                self._check_updates(manual=False)
        except Exception:
            pass
        try:
            self.root.after(30 * 60 * 1000, self._update_tick)
        except Exception:
            pass

    def _check_updates(self, manual: bool = False) -> None:
        if self._update_checking:
            if manual:
                self._status("文文：我还在跑呢，别催。", "info")
            return
        self._update_checking = True
        channel = self._channel_code()
        if manual:
            self._status("文文：这就去打听…", "info")

        def work():
            from modules import update as _up
            try:
                info = _up.check(channel)
                self.q.put(("update_result", info, "", manual))
            except Exception as e:
                self.q.put(("update_result", None, str(e), manual))

        threading.Thread(target=work, daemon=True).start()

    def _on_update_result(self, info, err, manual) -> None:
        from modules import update as _up

        self._update_checking = False
        now = int(time.time())
        self._update_last_check = now
        self.cfg["update_last_check"] = now
        if info:
            self._update_last_source = info.get("source", "")
            tag = info.get("tag", "")
            self.cfg["update_last_version"] = tag
            if _up.is_newer(tag, settings.APP_VERSION):
                first_offer = tag != self._update_offered
                if first_offer:
                    self._update_offered = tag
                    self._status(f"文文：新号外！{tag} 已经印出来了。", "ok")
                    self._show_update_dialog(info)
                elif manual:
                    self._status(f"文文：{tag} 的号外已经给你看过了，去下载吧。", "info")

                if manual:
                    if first_offer:
                        toast_body = f"文文：新号外印好了——{tag} 上架。要现在去取吗？"
                    else:
                        toast_body = f"文文：{tag} 的号外还压在文文那儿，去取吧。"
                    self._notify("update", "博麗神社 · 号外", toast_body,
                                 avatar="aya", force=True)
                elif first_offer:
                    self._notify(
                        "update", "博麗神社 · 号外",
                        f"文文：新号外印好了——{tag} 上架。要现在去取吗？",
                        key=tag, avatar="aya",
                    )
            elif manual:
                self._status(f"文文：没有新号外，v{settings.APP_VERSION} 还是最新的。", "info")
                self._notify(
                    "update", "博麗神社 · 号外",
                    f"文文：今天的号外翻遍了，v{settings.APP_VERSION} 还是最新的一期。",
                    avatar="aya", force=True,
                )
        else:
            self._update_last_source = "没打听到"
            if manual:
                msg = err or "连接没有回应"
                self._status(f"文文：路被结界挡住了……（{msg[:80]}）", "warn")
                self._notify(
                    "update", "博麗神社 · 号外",
                    f"文文：路被结界挡住了……（{msg[:60]}）",
                    avatar="aya", force=True,
                )
        self._refresh_update_labels()
        self._save_config()

    def _show_update_dialog(self, info: dict) -> None:
        win = tk.Toplevel(self.root)
        win.title("博麗神社 · 号外")
        win.configure(bg=C["bg"])
        win.transient(self.root)
        win.geometry(f"600x560+{self.root.winfo_rootx() + 300}+{self.root.winfo_rooty() + 120}")
        win.resizable(False, False)

        tk.Label(win, text="文文：新号外印好了——", bg=C["bg"], fg=C["gold"],
                 font=(self.F_TITLE, 20)).pack(pady=(18, 2))
        tk.Label(win, text=f"{settings.APP_VERSION}  →  {info.get('version', info.get('tag', ''))}",
                 bg=C["bg"], fg=C["text"], font=(self.F_MONO, 12)).pack()
        src = "Gitee（人间之里）" if info.get("source") == "gitee" else "GitHub（外界神社）"
        tk.Label(win, text=f"来源：{src}    {info.get('date', '')}",
                 bg=C["bg"], fg=C["muted"], font=(self.F_UI, 9)).pack(pady=(2, 8))

        tk.Label(win, text="【更新内容】", bg=C["bg"], fg=C["muted"],
                 font=(self.F_UI, 9), anchor="w").pack(fill="x", padx=24)
        body_wrap = tk.Frame(win, bg=C["bg"])
        body_wrap.pack(fill="both", expand=True, padx=24, pady=(4, 10))
        body = tk.Text(body_wrap, height=10, bg=C["input"], fg=C["text"], bd=0,
                       font=(self.F_UI, 9), wrap="word", padx=8, pady=6)
        sb = ttk.Scrollbar(body_wrap, orient="vertical", command=body.yview,
                           style="Dark.Vertical.TScrollbar")
        body.configure(yscrollcommand=sb.set)
        body.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        notes = (info.get("notes") or "").strip() or "（这次没有写说明，反正更新就对了。）"
        body.insert("1.0", notes[:4000])
        body.configure(state="disabled")

        row = tk.Frame(win, bg=C["bg"])
        row.pack(fill="x", padx=24, pady=(0, 16))

        def go_download() -> None:
            win.destroy()
            self._start_update_download(info)

        def open_release() -> None:
            self._open_url(info.get("url") or info.get("download") or "")

        def snooze() -> None:
            win.destroy()
            self._pick_snooze()

        tk.Button(row, text="让文文去取", command=go_download, bg=C["accent"], fg="white",
                  relief="flat", bd=0, padx=16, pady=5, cursor="hand2",
                  font=(self.F_UI, 10, "bold")).pack(side="left")
        tk.Button(row, text="打开号外页", command=open_release, bg=C["panel2"],
                  fg=C["text"], relief="flat", bd=0, padx=12, pady=5,
                  cursor="hand2", font=(self.F_UI, 10)).pack(side="left", padx=(8, 0))
        tk.Button(row, text="晚点再说", command=win.destroy, bg=C["panel2"], fg=C["muted"],
                  relief="flat", bd=0, padx=14, pady=5, cursor="hand2",
                  font=(self.F_UI, 10)).pack(side="left", padx=(10, 0))
        tk.Button(row, text="封笔到…", command=snooze, bg=C["panel2"], fg=C["text"],
                  relief="flat", bd=0, padx=14, pady=5, cursor="hand2",
                  font=(self.F_UI, 10)).pack(side="right")

    def _start_update_download(self, info: dict) -> None:
        from modules import update_ui

        try:
            info = dict(info)
            info["max_threads"] = max(1, min(32, int(self.update_max_threads_var.get())))
        except Exception:
            info = dict(info)
            info["max_threads"] = 8
        if not str(info.get("download") or "").lower().startswith(("http://", "https://")):
            self._status("文文：这张号外没带安装包地址，先去号外页看看。", "warn")
            self._open_url(info.get("url") or "")
            return
        avatar = os.path.join(ASSETS, "char", "toast", "avatar_aya.png")
        try:
            self._download_win = update_ui.start_download(
                self.root, info, C, self.F_UI, self.F_TITLE, avatar,
                self._begin_update_install)
            self._status("文文：号外正在取件，取件匣已经打开。", "info")
        except Exception as e:
            self._status(f"文文：取件匣打不开了……{e}", "err")

    def _begin_update_install(self, installer: str) -> None:
        from modules import update_install

        if not os.path.exists(installer):
            self._status("文文：号外已经不在取件匣里了。", "warn")
            return
        if not getattr(sys, "frozen", False):
            self._status("文文：开发版先不自动张贴，安装包已放在取件匣。", "info")
            try:
                os.startfile(os.path.dirname(installer))
            except Exception:
                pass
            return
        try:
            update_install.start_install(
                installer, os.path.dirname(sys.executable), sys.executable)
            self._status("文文：号外验好了，正在张贴……", "ok")
            self.root.after(700, self.root.destroy)
        except Exception as e:
            self._status(f"紫：张贴失败……{e}", "err")

    def _pick_snooze(self) -> None:
        import datetime as _dt

        from modules import calendar_dialog, update as _up

        initial = None
        if self._update_snooze_until > time.time():
            initial = _dt.date.fromtimestamp(self._update_snooze_until)
        d = calendar_dialog.pick_date(self.root, initial=initial, colors=C,
                                      title="封笔日历")
        if not d:
            return
        self._update_snooze_until = _up.snooze_until(d)
        self.cfg["update_snooze_until"] = self._update_snooze_until
        self._refresh_update_labels()
        self._save_config()
        self._status(f"灵梦：行吧，让文文歇到 {d.month} 月 {d.day} 日。别到时候又忘了。", "ok")

    def _snooze_days(self, days: int) -> None:
        import datetime as _dt

        from modules import update as _up

        d = _dt.date.today() + _dt.timedelta(days=days)
        self._update_snooze_until = _up.snooze_until(d)
        self.cfg["update_snooze_until"] = self._update_snooze_until
        self._refresh_update_labels()
        self._save_config()
        self._status(f"灵梦：行吧，让文文歇到 {d.month} 月 {d.day} 日。别到时候又忘了。", "ok")

    def _trial_reminder(self) -> None:
        try:
            from modules import license as _lic, trial_reminder as _tr
            state, _msg, days = _lic.check_access(update=False)
            rem = _tr.due(state, days, seen=getattr(self, "_toast_seen", {}))
            if rem:
                key, body = rem
                self._notify("trial", "博麗神社 · 结界", body, key=key,
                             critical=True, avatar="yukari")
                self._status(body, "warn")
        except Exception:
            pass

    # ------------------------------------------------------------------ 窗口/区域
    def _refresh_windows_async(self) -> None:
        def work():
            try:
                self.q.put(("windows", capture.list_windows()))
            except Exception as e:
                self.q.put(("status", f"紫：境界那边乱了……{e}", "err"))

        threading.Thread(target=work, daemon=True).start()

    def _apply_windows(self, wins: list[capture.WindowInfo]) -> None:
        self.windows = wins
        labels = ["整个屏幕"] + [w.label() for w in wins]
        self.window_box.configure(values=labels)
        if self.window_var.get() in labels:
            return
        for w in wins:
            if w.title == self.target_title:
                self.window_var.set(w.label())
                self.target_hwnd = w.hwnd
                return
        self.window_var.set("整个屏幕")
        self.target_title = ""
        self.target_hwnd = 0

    def _on_window_selected(self, _ev=None) -> None:
        label = self.window_var.get()
        if label == "整个屏幕":
            self.target_title = ""
            self.target_hwnd = 0
            self._status("灵梦：好，整块屏幕都归我管。", "info")
            return
        for w in self.windows:
            if w.label() == label:
                self.target_title = w.title
                self.target_hwnd = w.hwnd
                self._status(f"灵梦：就是这扇窗户吧？——{w.title[:50]}", "ok")
                return

    def _pick_region(self) -> None:
        try:
            rect = region.select_region(self.root)
        except Exception as e:
            self._status(f"灵梦：框选没成功——{e}", "err")
            return
        if not rect:
            self._status("灵梦：不框了？那算了。", "info")
            return
        self.region = rect
        self.target_title = ""
        self.target_hwnd = 0
        self.window_var.set("整个屏幕")
        self._status(f"灵梦：就盯着这块地方了（{rect[2]}×{rect[3]}）。", "ok")

    def _resolve_target(self) -> capture.WindowInfo | None:
        if self.target_title:
            for w in capture.list_windows():
                if w.title == self.target_title:
                    return w
            raise RuntimeError("紫：那扇窗户跑到境界外面去了……请点『刷新』重选")
        return None

    def _own_rect(self) -> tuple[int, int, int, int]:
        return (self.root.winfo_rootx(), self.root.winfo_rooty(),
                self.root.winfo_width(), self.root.winfo_height())

    def _own_hwnd(self) -> int:
        try:
            return int(self.root.wm_frame(), 16)
        except Exception:
            return self.root.winfo_id()

    def _grab_now(self, allow_yield: bool = True):
        if self.region:
            return capture.grab_region(self.region)
        win = self._resolve_target()
        method = "window" if self.method_var.get().startswith("后台") else "screen"
        if win is None:
            return capture.grab(None, method)

        need_yield = (allow_yield and method == "screen" and self.minimize_var.get()
                      and capture.overlap(self._own_rect(), win.rect))
        if need_yield:
            self.root.iconify()
            self.root.update()
            time.sleep(0.35)
            try:
                return capture.grab(win, method)
            finally:
                self.root.deiconify()
                self.root.lift()
        return capture.grab(win, method)

    # ------------------------------------------------------------------ 热键
    def _start_hotkeys(self) -> None:
        self.hotkeys = hotkey.HotkeyManager(
            {VK_F8: "capture", VK_F9: "answer"},
            on_hotkey=lambda name: self.q.put(("hotkey", name)),
            on_error=lambda msg: self.q.put(("status", msg, "warn")),
        )
        self.hotkeys.start()

    # ------------------------------------------------------------------ 剪贴板
    def _start_clipboard(self) -> None:
        self.clip_watcher = clipboard.ClipboardWatcher(
            on_image=lambda img: self.q.put(("clip_image", img)),
            enabled=lambda: bool(getattr(self, "_clip_enabled", False)) and not self.busy and not self.web_on,
        )
        self.clip_watcher.start()

    # ------------------------------------------------------------------ 任务
    def _ctx(self) -> dict:
        extra = {}
        raw = self.extra_var.get().strip()
        if raw:
            try:
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    raise ValueError('必须是 JSON 对象，例如 {"top_k": 20}')
                extra = parsed
            except Exception as e:
                raise llm.LLMError(f"自定义参数不是合法 JSON：{e}") from None
        vision = self.vision_var.get().strip()
        if vision.startswith("（使用"):
            vision = ""
        return {
            "base": self.base_var.get().strip(),
            "key": self.key_var.get().strip(),
            "model": self.model_var.get().strip(),
            "vision": vision or self.model_var.get().strip(),
            "vision_base": self.vision_base_var.get().strip() or self.base_var.get().strip(),
            "vision_key": self.vision_key_var.get().strip() or self.key_var.get().strip(),
            "effort": llm.EFFORT_MAP.get(self.effort_var.get()),
            "temperature": float(self.temp_var.get() or 0.2),
            "extra": extra,
            "translate": bool(self.trans_var.get()),
            "ocr_mode": self.ocr_var.get(),
        }

    def action_capture(self) -> None:
        if self.busy:
            self._status("灵梦：别催，我正在处理。（可点『停止』）", "warn")
            return
        try:
            cap = self._grab_now()
        except Exception as e:
            self._status(str(e), "err")
            return
        self._start_job("recognize", image=cap.image, source=cap.source)

    def action_answer_only(self) -> None:
        if self.busy:
            self._status("灵梦：别催，我正在处理。", "warn")
            return
        text = self._panel_text("src").strip()
        if not text:
            self._status(TIPS["empty"], "warn")
            return
        self._start_job("answer", text=text)

    def action_stop(self) -> None:
        if not self.busy and not self.web_on and not self.auto_var.get():
            self._status("灵梦：现在没什么要处理的东西。", "info")
            return
        self.cancel.set()
        self.web_stop.set()
        self._web_user_stop = True
        if self.auto_var.get():
            self.auto_var.set(False)
        if self.web_on:
            self.web_var.set(False)
            self.web_on = False
        try:
            self.btn_web.configure(text="⛩  开始退治")
        except Exception:
            pass
        self._refresh_action_status()
        self._status("灵梦：收工——自动监听和退治都停了。", "warn")

    def _start_job(self, kind: str, image=None, text: str = "", source: str = "", dedupe: bool = False) -> None:
        try:
            ctx = self._ctx()
        except Exception as e:
            self._status(str(e), "err")
            return
        self.cancel.clear()
        self.busy = True
        threading.Thread(target=self._job, args=(kind, ctx, image, text, source, dedupe),
                         daemon=True).start()

    def _job(self, kind: str, ctx: dict, image, text: str, source: str, dedupe: bool) -> None:
        try:
            if kind == "recognize":
                text = self._do_recognize(ctx, image, source)
                if not text.strip():
                    raise RuntimeError("魔理沙：这张符卡上什么都没写……换个区域或窗口再试试")
                if dedupe and text == self.last_text and self.last_answer:
                    self.q.put(("status", "灵梦：题目没变，没必要重打一遍。", "info"))
                    return
                self.last_text = text
            self.last_answer = ""
            translation = ""
            if ctx["translate"] and ocr_local.looks_english(text):
                translation = self._do_translate(ctx, text)
            self._do_answer(ctx, text, translation)
        except llm.LLMError as e:
            self.q.put(("status", str(e), "err"))
            self.q.put(("append", "ans", f"\n[出错了] {e}\n", "err"))
        except Exception as e:
            self.q.put(("status", f"魔理沙：呜哇，出岔子了……{e}", "err"))
            self.q.put(("append", "ans", f"\n[出错] {e}\n", "err"))
        finally:
            self.q.put(("busy", False))

    def _stream_cb(self, panel: str, tag: str):
        """流式回调：把 LaTeX 实时转成可读数学符号，半个公式先缓冲。"""
        f = latex.MathStream()
        self._streams[(panel, tag)] = f

        def cb(chunk: str) -> None:
            out = f.feed(chunk)
            if out:
                self.q.put(("append", panel, out, tag))

        return cb

    def _flush_stream(self, panel: str, tag: str) -> None:
        f = self._streams.pop((panel, tag), None)
        if f is None:
            return
        out = f.flush()
        if out:
            self.q.put(("append", panel, out, tag))

    def _do_recognize(self, ctx: dict, image, source: str) -> str:
        mode = ctx["ocr_mode"]
        for p in ("src", "trans", "ans"):
            self.q.put(("clear", p))
        self.q.put(("status", f"魔理沙：正在摘录…（{source}）", "info"))
        self.q.put(("meta", ""))

        if mode != "本地 OCR" and ctx["vision"]:
            try:
                self.q.put(("append", "src", "· 正在展开符卡…\n\n", "dim"))
                data_url = capture.to_data_url(image)
                res = llm.chat_stream(
                    ctx.get("vision_base") or ctx["base"], ctx.get("vision_key") or ctx["key"],
                    ctx["vision"], prompts.ocr_messages(data_url),
                    reasoning_effort=None, temperature=0.0, extra_body=ctx["extra"] or None,
                    on_delta=self._stream_cb("src", "body"), cancel=self.cancel,
                )
                self._flush_stream("src", "body")
                if res.text.strip():
                    return res.text.strip()
                raise llm.LLMError("视觉模型没有返回内容")
            except Exception as e:
                self._flush_stream("src", "body")
                if mode == "视觉模型":
                    raise
                self.q.put(("clear", "src"))
                self.q.put(("status", f"魔理沙：符卡没展开，换本地 OCR——{e}", "warn"))

        if self.cancel.is_set():
            raise llm.LLMError("已停止")
        ocr = ocr_local.recognize(image)
        if not ocr.ok:
            raise RuntimeError(ocr.error)
        self.q.put(("append", "src", latex.latex_to_text(ocr.text), "body"))
        return ocr.text

    def _do_translate(self, ctx: dict, text: str) -> str:
        self.q.put(("clear", "trans"))
        self.q.put(("status", TIPS["translate"], "info"))
        try:
            res = llm.chat_stream(
                ctx["base"], ctx["key"], ctx["model"], prompts.translate_messages(text),
                reasoning_effort=None, temperature=0.2, extra_body=ctx["extra"] or None,
                on_delta=self._stream_cb("trans", "body"), cancel=self.cancel,
            )
            return res.text.strip()
        except Exception as e:
            self.q.put(("append", "trans", f"[翻译失败] {e}", "err"))
            return ""
        finally:
            self._flush_stream("trans", "body")

    def _do_answer(self, ctx: dict, text: str, translation: str) -> None:
        self.q.put(("clear", "ans"))
        label = ctx["model"] or "(未选模型)"
        if ctx["effort"]:
            label += f" · {ctx['effort']}"
        self.q.put(("status", f"灵梦：交给我吧。（{label}）", "info"))
        state = {"reason": False, "content": False}

        reason_cb = self._stream_cb("ans", "dim")
        body_cb = self._stream_cb("ans", "body")

        def on_reason(chunk: str) -> None:
            if not state["reason"]:
                state["reason"] = True
                self.q.put(("append", "ans", "【思考过程】\n", "dim"))
            reason_cb(chunk)

        def on_delta(chunk: str) -> None:
            if not state["content"]:
                state["content"] = True
                self._flush_stream("ans", "dim")
                if state["reason"]:
                    self.q.put(("append", "ans", "\n\n", "body"))
            body_cb(chunk)

        t0 = time.time()
        try:
            res = llm.chat_stream(
                ctx["base"], ctx["key"], ctx["model"],
                prompts.answer_messages(text, from_ocr=True, translated=translation),
                reasoning_effort=ctx["effort"], temperature=ctx["temperature"],
                extra_body=ctx["extra"] or None,
                on_delta=on_delta, on_reasoning=on_reason, cancel=self.cancel,
            )
        finally:
            self._flush_stream("ans", "dim")
            self._flush_stream("ans", "body")
        self.last_answer = res.text
        self.messages = [
            {"role": "user", "content": text},
            {"role": "assistant", "content": res.text},
        ]
        usage = res.usage or {}
        self.q.put(("meta", self._cost_text(ctx["model"], usage)))
        if res.text.strip():
            self.q.put(("status", TIPS["done"], "ok"))
        else:
            self.q.put(("append", "ans", "（模型没有返回内容，检查模型是否支持该参数）", "err"))

    # ------------------------------------------------------------------ 自动监听
    def _toggle_auto(self) -> None:
        if not self.auto_var.get():
            self._status(TIPS["auto_off"], "info")
            return
        if not self.region and not self.target_title:
            self.auto_var.set(False)
            self._status("灵梦：先告诉我要退治哪个窗口（或框选一块区域）。", "warn")
            return
        self._auto_prev = None
        self._auto_changed = False
        self._auto_last_change = 0.0
        self._auto_last_trigger = 0.0
        self._status(TIPS["auto"], "ok")
        self.root.after(300, self._auto_tick)

    def _auto_tick(self) -> None:
        if not self.auto_var.get():
            return
        interval = max(0.5, float(self.interval_var.get() or 1.5))
        try:
            self._auto_tick_once()
        except Exception as e:
            self._status(f"魔理沙：自动符卡失控了……{e}", "err")
            self.auto_var.set(False)
            self._refresh_action_status()
            return
        self.root.after(int(interval * 1000), self._auto_tick)

    def _auto_tick_once(self) -> None:
        if self.browser_only_var.get():
            exe = capture.process_name(capture.foreground_window())
            if exe not in ("chrome.exe", "msedge.exe", "msedgebeta.exe", "firefox.exe",
                           "brave.exe", "vivaldi.exe", "opera.exe"):
                return
        method = "window" if self.method_var.get().startswith("后台") else "screen"
        if method == "screen" and capture.foreground_window() == self._own_hwnd():
            self._status("灵梦：你正挡着我呢，切回题目窗口我就继续。", "warn")
            return

        try:
            cap = self._grab_now(allow_yield=False)
        except RuntimeError:
            # 目标窗口最小化/暂时抓不到：这一拍跳过，别把「自动监视」自己关掉
            return
        now = time.time()
        threshold = float(self.threshold_var.get() or 1.5)
        settle = float(self.settle_var.get() or 0.8)
        cooldown = 4.0

        if self._auto_prev is None:
            self._auto_prev = cap.image
            self._auto_last_change = now
            return

        score = capture.diff_score(cap.image, self._auto_prev)
        self._auto_prev = cap.image
        if score >= threshold:
            self._auto_last_change = now
            self._auto_changed = True
        if not self._auto_changed:
            return
        if now - self._auto_last_change < settle:
            return
        if now - self._auto_last_trigger < cooldown or self.busy:
            return

        self._auto_changed = False
        self._auto_last_trigger = now
        self._start_job("recognize", image=cap.image, source=cap.source, dedupe=True)

    # ------------------------------------------------------------------ 网页模式
    def _toggle_web(self) -> None:
        try:
            self._toggle_web_impl()
        except Exception as e:
            try:
                self.web_var.set(False)
                self.btn_web.configure(text="⛩  开始退治")
                self.web_on = False
                self.web_stop.set()
            except Exception:
                pass
            self._status(f"魔理沙：开启退治失败——{e}", "err")
        finally:
            self._refresh_action_status()

    def _toggle_web_impl(self) -> None:
        if self.web_var.get():
            if not self.key_var.get().strip():
                self.web_var.set(False)
                self._status("灵梦：全自动模式要先去设置里填 API Key。", "warn")
                return
            try:
                ctx = self._ctx()
            except Exception as e:
                self.web_var.set(False)
                self._status(str(e), "err")
                return
            self._web_ctx = ctx
            self._web_port = int(self.web_port_var.get() or 9222)
            self._web_seen = set()
            self._web_try = {}
            self._web_hint = ""
            self._web_prev = {}
            self._web_graph_done = set()
            self._web_blocked = []
            self._web_partial_done = set()
            self._web_all_done = False
            self._web_question = 0
            self._web_ok = 0
            self._web_fail = 0
            self._web_continue_wrong = bool(self.continue_wrong_var.get())
            self._web_user_stop = False
            self._web_round_failed = False
            self.web_done = ""
            if self.auto_var.get():
                self.auto_var.set(False)
                self._status("灵梦：全自动接管了，自动监听先关掉。", "info")
            self.web_on = True
            self.web_stop.clear()
            self.btn_web.configure(text="⛩  退治中…")
            port = int(self.web_port_var.get() or 9222)
            if not self._web_port_open(port):
                self._status("紫：结界还没开——先点左边的「张开结界」（或者自己打开答题浏览器）。", "warn")
            else:
                self._status("紫：正在从境界的缝隙里连你的浏览器…", "info")
            self._web_gen = getattr(self, "_web_gen", 0) + 1
            self.web_thread = threading.Thread(target=self._web_loop, daemon=True)
            self.web_thread.start()
            self._status("紫：全自动已开启——等题目出现就会自动读题、作答、交卷、翻页。", "ok")
            self._notify("auto", "博麗神社 · 退治",
                         "灵梦：退治开始——结界已连通，接下来交给我。",
                         force=True, avatar="reimu")
        else:
            self.web_on = False
            self._web_user_stop = True
            self.web_stop.set()
            self.btn_web.configure(text="⛩  开始退治")
            self._status("全自动模式已关闭", "info")
            self._notify("auto", "博麗神社 · 退治",
                         "魔理沙：退治已停止，结界先留着。",
                         force=True, avatar="marisa")

    def _barrier_toast(self, body: str, avatar: str = "yukari") -> None:
        """结界/退治动作的即时 Toast：不被静音时段或去重键吞掉。"""
        try:
            self._notify("auto", "博麗神社 · 结界", body, force=True, avatar=avatar)
        except Exception:
            pass

    def _watch_barrier(self) -> None:
        """轮询调试端口：手动开/关浏览器时也推送结界 Toast。"""
        try:
            port = int(self.web_port_var.get() or 9222)
            open_now = self._web_port_open(port)
            last = getattr(self, "_barrier_last", None)
            launching = bool(getattr(self, "_barrier_launching", False))
            if open_now:
                self._barrier_launching = False
                self._barrier_last = True
                try:
                    self.browser_var.set(True)
                    self.btn_browser.configure(text="☂  关闭结界")
                except Exception:
                    pass
            elif launching and time.time() < float(getattr(self, "_barrier_launch_until", 0)):
                # 启动浏览器需要几秒，别在它起来前把勾去掉/文案打回。
                self._barrier_last = False
                return
            else:
                if launching:
                    self._barrier_launching = False
                    self._barrier_toast("魔理沙：结界张开超时，浏览器可能没起来。",
                                        avatar="marisa")
                self._barrier_last = False
                try:
                    self.browser_var.set(False)
                    self.btn_browser.configure(text="☂  张开结界")
                except Exception:
                    pass
            if last is not None and open_now != last:
                if open_now:
                    self._barrier_toast("紫：结界已张开，专用答题浏览器已连上调试端口。")
                else:
                    self._barrier_toast("紫：结界已关闭，调试端口已断开。")
                    if getattr(self, "web_on", False):
                        self.web_var.set(False)
                        self._toggle_web()
                        self._status("紫：浏览器关掉了，全自动也先停了。", "warn")
        except Exception:
            pass
        finally:
            try:
                self.root.after(1500, self._watch_barrier)
            except Exception:
                pass

    def _close_answer_browser(self, port: int) -> bool:
        """通过 CDP Browser.close 关闭专用答题浏览器，避免误杀普通 Edge。"""
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{int(port)}/json/version", timeout=2.0) as r:
                info = json.loads(r.read().decode("utf-8", "replace"))
            ws = info.get("webSocketDebuggerUrl") or ""
            if ws:
                cdp = web.CDP(ws, timeout=2.0)
                try:
                    cdp.call("Browser.close", timeout=1.2)
                except Exception:
                    pass
                finally:
                    cdp.close()
        except Exception:
            pass
        for _ in range(12):
            if not self._web_port_open(int(port)):
                return True
            time.sleep(0.2)
        return False

    def _toggle_browser(self) -> None:
        """☂ 张开/关闭结界：专用浏览器（带调试端口）。"""
        port = int(self.web_port_var.get() or 9222)
        if self.browser_var.get():
            if self._web_port_open(port):
                self.btn_browser.configure(text="☂  关闭结界")
                self._barrier_last = True
                self._barrier_toast("紫：结界已张开，专用答题浏览器已经在跑。")
                self._status("紫：结界早就张开了（浏览器已经在跑）。", "info")
                return
            ok = self._launch_answer_browser()
            if ok:
                self._barrier_launching = True
                self._barrier_launch_until = time.time() + 12.0
                self.btn_browser.configure(text="☂  结界正在张开")
                self._status("紫：结界张开——专用浏览器正在启动，起来后会再通知你。", "ok")
            else:
                self.browser_var.set(False)
                self._status("魔理沙：找不到「启动答题浏览器.bat」。", "err")
                self._barrier_toast("魔理沙：结界张开失败，找不到「启动答题浏览器.bat」。",
                                    avatar="marisa")
        else:
            if getattr(self, "web_on", False):
                self.web_var.set(False)
                self._toggle_web()
            self.btn_browser.configure(text="☂  正在关闭结界")
            self._barrier_closing = True
            self._barrier_launching = False
            ok = self._close_answer_browser(port)
            self._barrier_closing = False
            if ok:
                # 不在这里改 _barrier_last：让 _watch_barrier 观察到
                # True→False 的变化，统一只推一条“结界已关闭”。
                was_open = bool(getattr(self, "_barrier_last", False))
                self.browser_var.set(False)
                self.btn_browser.configure(text="☂  张开结界")
                self._status("紫：结界已关闭，专用答题浏览器已退出。", "info")
                if not was_open:
                    self._barrier_toast("紫：结界已关闭。")
            else:
                self.browser_var.set(True)
                self.btn_browser.configure(text="☂  关闭结界")
                self._status("魔理沙：结界关不掉——浏览器可能还在跑，你再试一次。", "warn")
                self._barrier_toast("魔理沙：结界关闭失败，浏览器可能还在跑。", avatar="marisa")

    def _web_port_open(self, port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", int(port)), timeout=0.4):
                return True
        except OSError:
            return False

    def _launch_answer_browser(self) -> bool:
        """自动打开答题浏览器（就是那个 bat），返回是否发出启动。"""
        bat = os.path.join(HERE, "启动答题浏览器.bat")
        if not os.path.exists(bat):
            return False
        try:
            url = (self.start_url_var.get() or "").strip() or "https://kysu.edu"
            subprocess.Popen(
                ["cmd", "/c", bat, url], cwd=HERE,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return True
        except Exception:
            return False

    def _web_status(self, text: str, level: str = "info") -> None:
        self.q.put(("status", text, level))
        # 自动答题轨迹：方便测试后定位卡在哪一题/哪一小问
        try:
            logdir = os.path.join(os.environ.get("APPDATA", ""), "SpellCardHomework")
            os.makedirs(logdir, exist_ok=True)
            log = os.path.join(logdir, "auto.log")
            if os.path.exists(log) and os.path.getsize(log) > 2 * 1024 * 1024:
                try:
                    os.replace(log, log + ".1")
                except Exception:
                    pass
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{level}] {text}\n")
        except Exception:
            pass

    def _web_loop(self) -> None:
        """全自动主循环：连不上就等，断了就重连，一直做到没有下一题。"""
        drv = None
        errs = 0
        try:
            while not self.web_stop.is_set():
                if drv is None:
                    try:
                        drv = web.WebPlayer(getattr(self, "_web_port", 9222),
                                            log=lambda m: self._web_status(f"紫：{m}"))
                        drv.connect()
                        errs = 0
                    except Exception as e:
                        drv = None
                        self._web_status(
                            f"灵梦：还没连上浏览器（{e}）——先点☂张开结界，3 秒后重试…", "warn")
                        if self.web_stop.wait(3):
                            break
                        continue

                try:
                    if not self._web_step(drv):
                        if self.web_stop.is_set():
                            break
                        if self._web_recover_blocked(drv):
                            errs = 0
                            continue
                        break
                    errs = 0
                except Exception as e:
                    errs += 1
                    self._web_status(f"魔理沙：全自动出错——{e}", "err")
                    if drv is not None:
                        drv.ctx = None
                    if errs >= 3:
                        try:
                            drv.close()
                        except Exception:
                            pass
                        drv = None
                    if errs >= 12:
                        self._web_round_failed = True
                        self._web_status("魔理沙：连着出错太多次，先关了全自动。", "err")
                        break
                    if self.web_stop.wait(2):
                        break
                    continue

                if self.web_stop.wait(0.25):
                    break
        finally:
            if drv is not None:
                try:
                    drv.close()
                except Exception:
                    pass
            if not getattr(self, "_web_user_stop", True):
                _ok = int(getattr(self, "_web_ok", 0))
                _fail = int(getattr(self, "_web_fail", 0))
                _blocked = [] if getattr(self, "_web_all_done", False) else list(getattr(self, "_web_blocked", []))
                if _blocked:
                    _body = (f"魔理沙：这一轮跑完了。对 {_ok} 错 {_fail}；"
                             f"第 {','.join('Q'+str(n) for n in _blocked)} 题留给人工。")
                elif _fail or (getattr(self, "_web_round_failed", False)
                               and not getattr(self, "_web_all_done", False)):
                    _body = (f"魔理沙：啧，这一轮没退治干净……对 {_ok} 错 {_fail}，"
                             "你自己看着办。")
                else:
                    _body = f"魔理沙：这一轮退治完了。对 {_ok} 错 {_fail}，还行嘛。"
                self._notify("auto", "博麗神社 · 退治", _body,
                             key=f"auto:{int(time.time())}", force=True, avatar="marisa")
            if not getattr(self, "_web_user_stop", True):
                if _blocked:
                    self._web_status(
                        f"魔理沙：全自动收工——对 {_ok} / 错 {_fail}；"
                        f"第 {','.join('Q'+str(n) for n in _blocked)} 题留给人工。", "ok")
                elif getattr(self, "_web_round_failed", False) \
                        and not getattr(self, "_web_all_done", False):
                    self._web_status(
                        "魔理沙：全自动停下了——当前题没答完，停在原题，没有跳题。",
                        "err")
                else:
                    self._web_status(
                        f"灵梦：全自动收工——没有更多题了（对 {_ok} / 错 {_fail}）。", "ok")
            self.q.put(("web_off", getattr(self, "_web_gen", 0)))

    def _web_recover_blocked(self, drv) -> bool:
        """单题失败不要退出全自动：标记待人工，跳到下一道未完成题。"""
        if getattr(self, "_web_ledger_failed", False):
            self._web_status("魔理沙：跳过账本没写成，停在原题等人工，不再跳过。", "err")
            return False
        try:
            st = drv.state() or {}
        except Exception:
            return False
        qs = [q for q in (st.get("questions") or []) if int(q.get("n") or 0) > 0]
        if qs and all(self._web_q_done(q) for q in qs):
            self._web_all_done = True
            return False
        qno = int(st.get("qno") or 0)
        if qno and qno not in self._web_blocked:
            try:
                skip_ledger.record_once(
                    qno, st.get("part") or [], reason="自动流程未能完成",
                    source="pearson")
            except Exception as exc:
                # 入账失败时不能把题号塞进“待人工”冒充已记录，直接停。
                self._web_ledger_failed = True
                self._web_round_failed = True
                self._web_status(
                    f"魔理沙：待人工账本写入失败（{exc}），停在原题。", "err")
                return False
            self._web_blocked.append(qno)
        blocked = set(self._web_blocked)
        cand = [q for q in qs if int(q["n"]) not in blocked
                and not self._web_q_done(q)
                and int(q["n"]) > qno]
        if not cand:
            cand = [q for q in qs if int(q["n"]) not in blocked
                    and not self._web_q_done(q)]
        if not cand:
            if qs and all(self._web_q_done(q) for q in qs):
                self._web_all_done = True
            return False
        target = sorted(cand, key=lambda q: int(q["n"]))[0]
        tn = int(target["n"])
        self._web_status(
            f"魔理沙：第 {qno} 题先标记待人工，跳到第 {tn} 题继续。", "warn")
        try:
            if drv.goto_question(tn) != "ok":
                return False
        except Exception:
            return False
        # 注意：调用本函数前当前题已经写入 skip ledger，才允许 Yes 离开。
        self._web_leave_if_prompt(drv, allow=True)
        time.sleep(1.1)
        try:
            return int((drv.state() or {}).get("qno") or 0) == tn
        except Exception:
            return False

    def _web_key(self, st: dict) -> str:
        text = (st.get("text") or "")[:1200]
        part = tuple(st.get("part") or [])
        ids = [f["id"] for f in st.get("fields", [])]
        ids += [r["id"] for r in st.get("radios", [])]
        ids += [r["id"] for r in st.get("checks", [])]
        ids += [i["id"] for i in st.get("inputs", [])]
        ids += [d["id"] for d in st.get("dropdowns", [])]
        ids += [s["id"] for s in st.get("selects", [])]
        labels = [str(f.get("label") or "")[:80] for f in st.get("fields", [])]
        labels += [str(r.get("label") or "")[:80] for r in st.get("radios", [])]
        labels += [str(c.get("label") or "")[:80] for c in st.get("checks", [])]
        qno = int(st.get("qno") or 0)
        raw = f"{qno}|{part}|{text}|{','.join(ids)}|{'|'.join(labels)}"
        return hashlib.md5(raw.encode()).hexdigest()

    @staticmethod
    def _web_status_kind(status: str) -> str:
        """把 Pearson 题目列表里的各种状态归一成可判断的几类。

        注意不能直接 `"correct" in s`：`Incorrect` 也包含 correct 子串，
        会把答错的题误判成已完成。
        """
        s = (status or "").strip().lower()
        if not s:
            return "blank"
        if "partial" in s:
            return "partial"
        if "incorrect" in s or "not correct" in s:
            return "incorrect"
        if re.search(r"\bcorrect\b", s):
            return "correct"
        if "not answered" in s or "unanswered" in s or "incomplete" in s:
            return "blank"
        return "other"

    @classmethod
    def _web_done_status(cls, status: str) -> bool:
        return cls._web_status_kind(status) in ("correct", "incorrect")

    def _web_is_blocked(self, q: dict) -> bool:
        try:
            return int(q.get("n") or 0) in (getattr(self, "_web_blocked", None) or [])
        except Exception:
            return False

    def _web_q_done(self, q: dict) -> bool:
        """部分对的题如果已经无法再改（没有 Check），也视为处理过，避免来回补题死循环。"""
        try:
            n = int(q.get("n") or 0)
        except Exception:
            n = 0
        return self._web_done_status(q.get("status")) \
            or n in getattr(self, "_web_partial_done", set())

    def _web_mark_partial_done(self, qno: int) -> None:
        try:
            if not hasattr(self, "_web_partial_done"):
                self._web_partial_done = set()
            self._web_partial_done.add(int(qno))
        except Exception:
            pass

    def _web_pick_unanswered(self, st: dict) -> dict | None:
        """当前题之后最近的未完成题；没有则回头找。"""
        qs = [q for q in (st.get("questions") or []) if int(q.get("n") or 0) > 0]
        cur = int(st.get("qno") or 0)
        if not qs:
            return None
        after = [q for q in qs if int(q["n"]) > cur
                 and not self._web_q_done(q) and not self._web_is_blocked(q)]
        if after:
            return sorted(after, key=lambda q: int(q["n"]))[0]
        before = [q for q in qs if int(q["n"]) < cur
                  and not self._web_q_done(q) and not self._web_is_blocked(q)]
        if before:
            return sorted(before, key=lambda q: int(q["n"]), reverse=True)[0]
        return None

    def _web_first_unfinished(self, st: dict) -> dict | None:
        qs = [q for q in (st.get("questions") or []) if int(q.get("n") or 0) > 0]
        left = [q for q in qs if not self._web_q_done(q) and not self._web_is_blocked(q)]
        return min(left, key=lambda q: int(q["n"])) if left else None

    def _web_leave_if_prompt(self, drv, allow: bool = False) -> bool:
        """处理 Pearson 的“离开未完成题”警告。

        默认永远点 No：只有调用方已经把当前题写进待人工账本（或当前题已判分）
        才允许点 Yes。返回 True 表示已经可以继续导航。
        """
        try:
            if not drv.leave_prompt():
                return True
        except Exception:
            return True
        try:
            ls = drv.leave_state()
        except Exception:
            ls = {}
        if not ls.get("visible"):
            # 识别到文字但没有结构化弹窗：宁可停下来让用户处理
            self._web_status("灵梦：出现离开确认，但认不出按钮，先停在这里。", "warn")
            return False
        if not allow:
            try:
                r = drv.click_leave("no")
            except Exception:
                r = "error"
            if r == "ok":
                self._web_status("灵梦：这是离开未完成题的警告，先点 No 留下来。", "info")
                time.sleep(0.7)
            else:
                self._web_status(f"灵梦：离开警告点 No 失败（{r}），停在这里。", "warn")
            return False
        if ls.get("kind") == "unchecked" and ls.get("yes_count") != 1:
            self._web_status("灵梦：离开警告的 Yes 不唯一，不敢点，停在这里。", "warn")
            return False
        try:
            r = drv.click_leave("yes")
        except Exception:
            r = "error"
        if r != "ok":
            self._web_status(f"灵梦：离开警告点 Yes 失败（{r}），停在这里。", "warn")
            return False
        time.sleep(0.8)
        return True

    def _web_jump_first_unfinished(self, drv, st: dict) -> bool:
        """如果前面还有没做完的题（比如 Q7 Partially correct），先回去补。"""
        cur = int(st.get("qno") or 0)
        first = self._web_first_unfinished(st)
        if not first or int(first["n"]) >= cur:
            return False
        n = int(first["n"])
        self._web_status(f"灵梦：前面第 {n} 题还没做完，先回去补。", "info")
        for _attempt in range(3):
            try:
                if drv.goto_question(n) != "ok":
                    time.sleep(0.8)
                    continue
                # 当前题尚未完成时不允许 Yes 离开；这里只用 No 处理警告。
                self._web_leave_if_prompt(drv)
                time.sleep(1.2)
                st2 = drv.state() or {}
                if int(st2.get("qno") or 0) == n:
                    return True
            except Exception:
                pass
        return False

    def _web_jump_next_unanswered(self, drv, st: dict | None = None) -> bool:
        """当前题已经答完时，直接点题号跳到下一道未完成题，而不是傻等 Next。"""
        try:
            st = st or drv.state() or {}
        except Exception:
            return False
        qno = int(st.get("qno") or 0)
        if qno <= 0:
            return False
        q = next((x for x in (st.get("questions") or [])
                  if int(x.get("n") or 0) == qno), None)
        if not q or not self._web_q_done(q):
            return False
        target = self._web_pick_unanswered(st)
        if not target:
            qs = [q for q in (st.get("questions") or []) if int(q.get("n") or 0) > 0]
            self._web_all_done = bool(qs) and all(self._web_q_done(q) for q in qs)
            return False
        tn = int(target["n"])
        self._web_status(f"灵梦：第 {qno} 题已经答过，转到第 {tn} 题继续…", "info")
        for _attempt in range(3):
            try:
                if drv.goto_question(tn) != "ok":
                    time.sleep(0.8)
                    continue
            except Exception:
                time.sleep(0.8)
                continue
            # 当前题已判分，才允许 Yes 离开未检查的残留答案。
            self._web_leave_if_prompt(drv, allow=True)
            time.sleep(1.1)
            try:
                st2 = drv.state() or {}
                if int(st2.get("qno") or 0) == tn:
                    self._web_status(f"灵梦：已到第 {tn} 题。", "info")
                    return True
            except Exception:
                pass
        return False

    def _web_wait_change(self, drv, old_key: str, timeout: float = 15.0) -> bool:
        """等页面换题（文本/控件变化），最多 timeout 秒。"""
        deadline = time.time() + timeout
        while time.time() < deadline and not self.web_stop.is_set():
            time.sleep(0.6)
            try:
                st = drv.state() or {}
            except Exception:
                return True
            key = self._web_key(st) if st else ""
            if key and key != old_key:
                return True
        return False

    @staticmethod
    def _web_sig(st: dict) -> str:
        """页面快照指纹；P0 用它发现“模型思考期间换题/换控件”。"""
        try:
            return str((st or {}).get("signature") or "")
        except Exception:
            return ""

    def _web_snapshot_intact(self, drv, st: dict) -> bool:
        """确认页面仍是同一份快照、且所有待填控件 UID 仍存在。

        这是 P0 的最后一道闸：模型算完后页面如果换题，宁可丢弃答案重读，
        也绝不把上一题的 (5,25) 填到下一题的同名输入框里。
        """
        try:
            now = drv.state() or {}
        except Exception:
            return True
        old_sig = self._web_sig(st)
        new_sig = self._web_sig(now)
        if old_sig and new_sig and old_sig != new_sig:
            return False
        present = getattr(drv, "field_present", None)
        if not callable(present):
            return True
        for key in ("fields", "inputs", "radios", "checks", "selects", "dropdowns"):
            for c in (st.get(key) or []):
                uid = str((c or {}).get("uid") or "")
                if not uid:
                    continue
                try:
                    if not present(uid):
                        return False
                except Exception:
                    pass
        return True

    @staticmethod
    def _web_player_kind(ps: dict) -> str:
        """把 Dojo player 的 _correctness 归一成 correct/incorrect/partial。"""
        if not isinstance(ps, dict) or not ps.get("ok"):
            return ""
        raw = ps.get("correctness")
        if raw is True:
            return "correct"
        if raw is False:
            return "incorrect"
        text = str(raw or "").strip().lower()
        if not text:
            return ""
        if "incorrect" in text or text in ("wrong", "false", "no"):
            return "incorrect"
        if "partial" in text:
            return "partial"
        if "correct" in text or text in ("yes", "true"):
            return "correct"
        return ""

    def _web_click_check(self, drv) -> bool:
        """Check answer 唯一且启用才点；绝不点旧 Check 或弹窗背后的按钮。

        P0：先看 Dojo player 的判分状态；再用 checkCandidates 保证唯一性。
        """
        for _ in range(12):
            try:
                st = drv.state() or {}
            except Exception:
                st = {}
            try:
                ps = drv.player_state() if hasattr(drv, "player_state") else {}
            except Exception:
                ps = {}
            # 只信“反馈弹窗正在打开”的 Dojo 状态；resultPosted 可能是上一题
            # 残留的 revision，不能单独作为“本题已判分”的依据。
            if ps.get("feedbackOpen") and self._web_player_kind(ps):
                return False
            try:
                cs = drv.completion_state() if hasattr(drv, "completion_state") else {}
            except Exception:
                cs = {}
            kind = str((cs or {}).get("kind") or "")
            if kind in ("correct", "incorrect", "finished"):
                return False
            if kind == "leave":
                # 「确定离开本题吗」：点 No 留下，再重试 Check，绝不盲目提交/跳题
                try:
                    drv.click_text(r"^\s*no\s*$")
                except Exception:
                    pass
                time.sleep(0.9)
                continue
            # 页面上同时出现多个 Check（旧小问残留）时绝不猜，停下来等调用方处理
            try:
                cks = drv.check_state() if hasattr(drv, "check_state") else {}
            except Exception:
                cks = {}
            if int((cks or {}).get("count") or 0) > 1:
                self._web_status("灵梦：页面上出现多个 Check 按钮，先不乱点，停一步检查。", "warn")
                self._web_round_failed = True
                return False
            if cks.get("ok"):
                try:
                    res = drv.click_check_unique()
                    if res == "ok":
                        return True
                    if res in ("multiple", "none"):
                        # 页面在下一步又变了，重读状态再试
                        time.sleep(0.35)
                        continue
                except Exception:
                    pass
            if st.get("canCheck", st.get("hasCheck")):
                try:
                    res = drv.click_text(r"^(check answer|final check)$")
                    if res != "ok" and hasattr(drv, "click_text_native"):
                        res = drv.click_text_native(r"^(check answer|final check)$")
                    if res == "ok":
                        time.sleep(0.45)
                        return True
                except Exception:
                    pass
            time.sleep(0.45)
        return False

    def _web_feedback(self, drv, timeout: float = 15.0) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                # Dojo player 的内部判分优先；它比 DOM 弹窗更稳定
                ps = drv.player_state() if hasattr(drv, "player_state") else {}
                pk = self._web_player_kind(ps)
                if pk and (ps.get("feedbackOpen") or ps.get("resultPosted")):
                    if pk == "correct":
                        return "correct"
                    if pk == "incorrect":
                        return "incorrect"
                    if pk == "partial":
                        # 当前调用方只区分 correct/incorrect；partial 视为可重试
                        return "incorrect"
                cs = drv.completion_state() if hasattr(drv, "completion_state") else {}
                kind = str((cs or {}).get("kind") or "")
                if kind in ("correct", "finished"):
                    return "correct"
                if kind == "incorrect":
                    return "incorrect"
                fb = (drv.feedback() or "").strip()
            except Exception:
                fb = ""
            if fb:
                return fb
            time.sleep(0.7)
        return ""

    @staticmethod
    def _part_of(text: str) -> tuple[int, int]:
        m = re.search(r"Part\s+(\d+)\s+of\s+(\d+)", text or "", re.I)
        return (int(m.group(1)), int(m.group(2))) if m else (1, 1)

    def _web_next(self, drv, old_key: str) -> bool:
        """点下一题并等页面变化。还有小问没做完时不点。

        如果当前有反馈弹窗，只点弹窗内部的 Next；绝不点弹窗背后的旧 Next/Check。
        """
        try:
            st = drv.state() or {}
            pv = st.get("part") or []
            n, m = (int(pv[0]), int(pv[1])) if len(pv) == 2 else (0, 0)
            if 0 < n < m:
                self._web_status(f"灵梦：还有第 {n + 1} 小问（共 {m} 问），先不翻页", "info")
                return False
        except Exception:
            pass
        try:
            cs = drv.completion_state() if hasattr(drv, "completion_state") else {}
            if cs and cs.get("kind") not in ("", "none"):
                if not cs.get("hasNext"):
                    return False
                res = drv.click_completion("next") if hasattr(drv, "click_completion") else "no"
            else:
                res = drv.click_text(r"^next( question)?$")
            if res != "ok":
                return False
            time.sleep(0.6)
            if drv.leave_prompt():
                drv.click_text(r"^\s*no\s*$")
                return False
        except Exception:
            return False
        return self._web_wait_change(drv, old_key)

    def _web_targets(self, st: dict, part_n: int) -> list[dict]:
        """当前小问可填的框：未作答（placeholder）优先，其次按小问号。

        多小问题里每个 part 会动态增加输入框，所以不能假设“第 N 问=第 N 个框”。
        """
        boxes = list(st.get("fields") or []) + list(st.get("inputs") or [])
        usable = [b for b in boxes
                  if not b.get("readonly") and not b.get("disabled")]
        ph = [b for b in usable
              if "enter your response" in str(b.get("label") or "").lower()]
        if ph:
            return ph + [b for b in usable if b not in ph]
        order: list[dict] = []
        if part_n and 0 < part_n <= len(usable):
            order.append(usable[part_n - 1])
        order += [b for b in usable if b not in order]
        return order

    def _web_skip(self, drv, key: str) -> bool:
        """这题答不了：先写入 review 账本，再让主循环跳到下一道未完成题。"""
        self._web_round_failed = True
        try:
            self._web_dismiss(drv)
        except Exception:
            pass
        qno = 0
        part = []
        try:
            _st = drv.state() or {}
            qno = int(_st.get("qno") or 0)
            part = list(_st.get("part") or [])
        except Exception:
            qno = 0
        try:
            skip_ledger.record_once(qno, part, reason="自动流程跳过", source="pearson")
            _pending = skip_ledger.pending_count()
            _extra = f"（累计待人工 {_pending} 题）" if _pending else ""
            self._web_ledger_failed = False
        except Exception as exc:
            # P0 铁律：没有成功入账就不允许离开本题。宁可停下等人工，
            # 也不能出现“跳过但谁都不知道”的静默漏题。
            self._web_ledger_failed = True
            self._web_round_failed = True
            self._web_status(
                f"魔理沙：跳过账本写入失败（{exc}），先停下，不离开本题。", "err")
            return False
        if qno:
            self._web_status(
                f"魔理沙：第 {qno} 题先留给人工，自动跳到下一道未完成题。{_extra}", "warn")
        else:
            self._web_status(
                f"魔理沙：这道题先留给人工，自动继续找下一题。{_extra}", "warn")
        return False

    def _web_dismiss(self, drv) -> None:
        """点掉当前判分弹窗内部的 OK，并等它真的消失。"""
        try:
            if hasattr(drv, "dismiss_feedback"):
                drv.dismiss_feedback()
            else:
                drv.click_text(r"^\s*ok\s*$")
        except Exception:
            pass
        for _ in range(12):
            try:
                cs = drv.completion_state() if hasattr(drv, "completion_state") else {}
                if not cs or cs.get("kind") in ("", "none"):
                    return
            except Exception:
                return
            time.sleep(0.3)

    def _web_fill(self, drv, fid: str, text: str) -> bool:
        """填一个框，并确认真的填进去了（编辑器偶尔会吞输入）。"""
        for _ in range(3):
            try:
                drv.focus_field(fid)
                time.sleep(0.35)
                drv.clear_field()
                time.sleep(0.35)
                # 粘贴用真符号（∞ ∪ √），粘贴失败才退回按键快捷键
                if not drv.paste_math(latex.to_paste_input(text)):
                    drv.insert_math(latex.to_editor_input(text))
                time.sleep(0.6)
            except Exception:
                continue
            exp = latex.normalize_answer(text)
            for _ in range(10):
                time.sleep(0.25)
                try:
                    txt = drv.field_text(fid)
                except Exception:
                    txt = ""
                got = latex.normalize_answer(txt)
                if exp and got and (exp == got or exp in got):
                    return True
        # 最后兜底：有些 eqEditor 只认 Input.insertText
        for _ in range(4):
            try:
                drv.focus_field(fid)
                time.sleep(0.2)
                drv.clear_field()
                time.sleep(0.2)
                drv.insert(latex.to_paste_input(text))
                time.sleep(0.8)
                txt = drv.field_text(fid)
                exp = latex.normalize_answer(text)
                got = latex.normalize_answer(txt)
                if exp and got and (exp == got or exp in got):
                    return True
            except Exception:
                pass
        return False


    def _ask_cancellable(self, base: str, api_key: str, model: str, msgs: list,
                         ctx: dict, timeout: float = 120.0,
                         temperature: float = 0.2) -> str:
        """可被「收工」立即打断的模型调用：流式收集，cancel 用 web_stop。"""
        buf: list[str] = []

        def on_delta(chunk: str) -> None:
            buf.append(chunk)

        res = llm.chat_stream(
            base, api_key, model, msgs,
            reasoning_effort=ctx.get("effort"),
            temperature=temperature,
            extra_body=ctx.get("extra") or None,
            timeout=timeout,
            on_delta=on_delta,
            cancel=self.web_stop,
        )
        return (res.text or "".join(buf) or "").strip()

    @staticmethod
    def _web_part_text(text: str, n: int) -> str:
        if n <= 0:
            return text or ""
        try:
            m = re.search(rf"Part\s+{n}\b(.*?)(?=Part\s+{n + 1}\b|\Z)",
                          text or "", re.S | re.I)
            return (m.group(1) if m else (text or ""))
        except Exception:
            return text or ""

    @staticmethod
    def _web_clip(s: str, limit: int) -> str:
        s = s or ""
        if len(s) <= limit:
            return s
        head = max(200, limit - 500)
        return s[:head] + "\n……\n" + s[-500:]

    @staticmethod
    def _web_focus_text(text: str, n: int) -> str:
        """多小问同页时，只把题干 + 当前小问交给模型，避免它顺手回答旧小问。"""
        if n <= 0:
            return text or ""
        raw = text or ""
        seg = App._web_part_text(raw, n).strip()
        stem = ""
        try:
            _pieces = re.split(r"Part\s+1\b", raw, maxsplit=2, flags=re.I)
            if len(_pieces) >= 3:
                stem = _pieces[1].strip()
        except Exception:
            stem = ""
        if n == 1 and stem and seg.startswith(stem[:60]):
            seg = seg[len(stem):].lstrip()
        if not seg or seg == raw:
            return raw
        stem = App._web_clip(stem, 1200)
        seg = App._web_clip(seg, 2000)
        return (f"当前是第 {n} 小问，只回答这一小问。\n"
                + (stem + "\n\n" if stem else "") + seg)

    @staticmethod
    def _web_quadratic_points(text: str, graph: dict) -> list[tuple[float, float]] | None:
        """从题干里解析二次函数，返回作图所需的三个点。"""
        poly = None
        try:
            funcs = verify_math.extract_functions(text or "")
            poly = next((f["poly"] for f in funcs if abs(f["poly"][0]) > 1e-9), None)
        except Exception:
            poly = None
        if poly is None:
            try:
                poly = verify_math.parse_poly(text or "")
            except Exception:
                poly = None
        if not poly or abs(poly[0]) < 1e-9:
            return None
        a, b, c = poly
        try:
            xmin = float(graph.get("xmin", -6))
            xmax = float(graph.get("xmax", 6))
            ymin = float(graph.get("ymin", -20))
            ymax = float(graph.get("ymax", 10))
        except Exception:
            xmin, xmax, ymin, ymax = -6, 6, -20, 10
        vx = -b / (2 * a)
        vy = verify_math.poly_eval(poly, vx)
        for delta in (1.0, 0.5, 2.0, 0.25):
            pts = [(vx, vy),
                   (vx - delta, verify_math.poly_eval(poly, vx - delta)),
                   (vx + delta, verify_math.poly_eval(poly, vx + delta))]
            if all(xmin - 1e-6 <= x <= xmax + 1e-6 and ymin - 1e-6 <= y <= ymax + 1e-6
                   for x, y in pts):
                return [(round(x, 4), round(y, 4)) for x, y in pts]
        return None

    @staticmethod
    def _web_poly(expr: str):
        """返回 (a,b,c) 或 None；统一转给 verify_math.parse_poly。"""
        try:
            return verify_math.parse_poly(expr)
        except Exception:
            return None

    @staticmethod
    def _web_graph_objects(text: str, graph: dict) -> list[dict]:
        """从题干里找 R(x)/C(x)/y= 等函数，生成 GraphControl 对象。"""
        try:
            funcs = verify_math.extract_functions(text or "")
        except Exception:
            funcs = []
        try:
            xmin, xmax = float(graph.get("xmin", -6)), float(graph.get("xmax", 6))
            ymin, ymax = float(graph.get("ymin", -20)), float(graph.get("ymax", 10))
        except Exception:
            xmin, xmax, ymin, ymax = -6, 6, -20, 10
        if xmax <= xmin:
            xmin, xmax = -6, 6
        if ymax <= ymin:
            ymin, ymax = -20, 10
        objs = []
        for fn in funcs:
            a, b, c = fn["poly"]
            if abs(a) > 1e-9:
                vx = -b / (2 * a)
                vy = verify_math.poly_eval((a, b, c), vx)
                # 顶点在可见范围内时取顶点 ± 2；否则在可见区间均匀取三点
                d = 2.0
                if not (xmin <= vx - d and vx + d <= xmax):
                    xs = [xmin, (xmin + xmax) / 2.0, xmax]
                else:
                    xs = [vx, vx - d, vx + d]
                pts = [(x, verify_math.poly_eval((a, b, c), x)) for x in xs]
                objs.append({"objectType": "quadratic",
                             "points": [{"x": round(x, 3), "y": round(y, 3)} for x, y in pts],
                             "params": {}})
            else:
                # 线性：优先取图形范围两端；超出 y 范围时按 y 范围截取
                pts = [(xmin, b * xmin + c), (xmax, b * xmax + c)]
                ys = [p[1] for p in pts]
                if abs(b) > 1e-9 and (min(ys) < ymin or max(ys) > ymax):
                    x1 = (ymin - c) / b
                    x2 = (ymax - c) / b
                    if x1 > x2:
                        x1, x2 = x2, x1
                    lo, hi = max(xmin, x1), min(xmax, x2)
                    if hi > lo:
                        pts = [(lo, b * lo + c), (hi, b * hi + c)]
                objs.append({"objectType": "line",
                             "points": [{"x": round(x, 3), "y": round(y, 3)} for x, y in pts],
                             "params": {}})
        return objs

    def _web_finish_graph_only(self, drv, key: str) -> bool:
        """图形题只有作图时，画完直接点 Check，不再让文本模型抢答。"""
        try:
            st = drv.state() or {}
        except Exception:
            st = {}
        if not st.get("canCheck"):
            if st.get("hasCheck"):
                self._web_status("灵梦：图形还没被 Pearson 接受，Check 还是灰的。", "warn")
            else:
                self._web_status("灵梦：找不到 Check answer，停在图形题。", "warn")
            self._web_round_failed = True
            return False
        if not self._web_click_check(drv):
            self._web_status("灵梦：图形题的 Check answer 点不到。", "warn")
            self._web_round_failed = True
            return False
        fb = self._web_feedback(drv)
        if fb == "correct":
            self._web_ok += 1
            self._web_status(f"灵梦：第 {self._web_question} 题答对了。（对 {self._web_ok} / 错 {self._web_fail}）", "ok")
            try:
                if drv.dialog_next() and self._web_next(drv, key):
                    return True
            except Exception:
                pass
            try:
                self._web_dismiss(drv)
            except Exception:
                pass
            time.sleep(0.7)
            if self._web_wait_change(drv, key, timeout=15):
                return True
            if self._web_next(drv, key):
                return True
            if self._web_jump_next_unanswered(drv):
                return True
            self._web_status("灵梦：图形题后面没有下一题了。", "ok")
            return False
        if fb == "incorrect":
            self._web_fail += 1
            self._web_round_failed = True
            self._web_status("魔理沙：图形题被判错，停在原题检查。", "err")
            return False
        # 判分弹窗没出来：先看题号状态
        try:
            if self._web_jump_next_unanswered(drv):
                return True
        except Exception:
            pass
        self._web_status("灵梦：图形题没看到判分，停在原题。", "warn")
        self._web_round_failed = True
        return False

    def _web_step(self, drv: "web.WebPlayer") -> bool:
        """处理一道题。返回 False 表示该停了（做完/被卡住）。"""
        st = drv.state()
        # 整份作业每一题都已判过分（含 part 0.4 的 Partially correct）：不再动页面，
        # 避免重启后把已经提交的答案又重填一遍，甚至把部分题改坏。
        try:
            _qs0 = [q for q in (st.get("questions") or []) if int(q.get("n") or 0) > 0]
            _kinds0 = [self._web_status_kind(q.get("status")) for q in _qs0]
            if _qs0 and all(k in ("correct", "incorrect", "partial") for k in _kinds0):
                self._web_all_done = True
                if not self._web_ok and not self._web_fail:
                    self._web_ok = _kinds0.count("correct")
                    self._web_fail = sum(1 for k in _kinds0
                                         if k in ("incorrect", "partial"))
                self._web_status(
                    f"灵梦：整份作业都处理完了（对 {self._web_ok} / 错 {self._web_fail}）。", "ok")
                return False
        except Exception:
            pass
        # 图形题会先出图、后出选项/输入框；先等控件加载，避免拿空状态去问模型
        if st.get("graph") and not (
                st.get("fields") or st.get("inputs") or st.get("radios")
                or st.get("checks") or st.get("selects") or st.get("dropdowns")):
            for _wait in range(10):
                time.sleep(0.45)
                st2 = drv.state()
                if st2 and (st2.get("fields") or st2.get("inputs") or st2.get("radios")
                            or st2.get("checks") or st2.get("selects") or st2.get("dropdowns")):
                    st = st2
                    break
        # 严格字段 inventory：页面渲染出的答题控件必须全部被快照捕获。
        # 少一个就说明还有控件没识别（诱饵框/自定义控件/异步加载），此时绝不
        # 让模型盲答——刷新几次仍不完整就记账跳过，留给人工。
        try:
            if st.get("incomplete"):
                _inv = st.get("inventory") or {}
                self._web_status(
                    f"魔理沙：页面控件没认全（渲染 {_inv.get('rendered')} / 捕获 "
                    f"{_inv.get('captured')}，缺组 {_inv.get('missing')}），先刷新再读…",
                    "info")
                for _retry in range(3):
                    time.sleep(0.8)
                    st2 = drv.state() or {}
                    if not st2.get("incomplete"):
                        st = st2
                        break
                else:
                    self._web_status(
                        "魔理沙：控件清单仍不完整，这题不盲答，记待人工后跳下一题。",
                        "warn")
                    return self._web_skip(drv, self._web_key(st) if st else "")
        except Exception:
            pass
        key = self._web_key(st) if st else ""
        # 当前题已经答对：不要死等 Next，直接找下一道没答完的题
        try:
            _qno = int(st.get("qno") or 0)
            _q = next((x for x in (st.get("questions") or [])
                       if int(x.get("n") or 0) == _qno), None)
            _fb_open = ""
            try:
                _fb_open = (drv.feedback() or "").strip()
            except Exception:
                _fb_open = ""
            if _q and not _fb_open and self._web_done_status(_q.get("status")):
                if self._web_jump_next_unanswered(drv, st):
                    return True
                self._web_status(
                    f"灵梦：第 {_qno} 题已答过，后面也没有未完成的题了。", "ok")
                return False
            if _q and not _fb_open and not self._web_done_status(_q.get("status")):
                if self._web_jump_first_unfinished(drv, st):
                    return True
        except Exception:
            pass
        # 多小问没做完却点了下一题时，Pearson 会弹「确定离开本题吗」——选 No
        try:
            if drv.leave_prompt():
                self._web_leave_if_prompt(drv, allow=False)
                time.sleep(0.8)
                return True
        except Exception:
            pass
        # 上一题的判分弹窗还开着：先翻到下一题
        try:
            fb_open = (drv.feedback() or "").strip()
        except Exception:
            fb_open = ""
        if fb_open and key not in self._web_seen:
            # 不是当前题的反馈，先关掉，避免读到上一题的判分结果
            self._web_dismiss(drv)
            time.sleep(0.4)
            try:
                st = drv.state() or st
            except Exception:
                pass

        if fb_open and key in self._web_seen:
            self._web_status("灵梦：上一题的判分弹窗还开着，先处理掉…", "info")
            pv = st.get("part") or []
            multi = len(pv) == 2 and 0 < int(pv[0]) < int(pv[1])
            if multi:
                # 多小问：只点掉 OK，等下一小问出现；没有出现就停在原题，绝不点 Next
                self._web_dismiss(drv)
                time.sleep(0.6)
                if self._web_wait_change(drv, key, timeout=12):
                    return True
                self._web_status("灵梦：下一小问没有出现，先停在原题检查。", "warn")
                self._web_round_failed = True
                return False
            if drv.dialog_next():
                clicked = drv.click_text(r"^next( question)?$")
                if clicked == "ok" and self._web_wait_change(drv, key, timeout=10):
                    return True
            else:
                # 单问：点掉弹窗；下一题出现就继续，否则翻下一题
                self._web_dismiss(drv)
                time.sleep(0.6)
                if self._web_wait_change(drv, key, timeout=15):
                    return True
                if self._web_next(drv, key):
                    return True
            if self._web_jump_next_unanswered(drv):
                return True
            self._web_status(
                f"灵梦：没有下一题了，全自动收工（对 {self._web_ok} / 错 {self._web_fail}）。", "ok")
            return False

        has_inputs = (bool(st.get("fields")) or bool(st.get("inputs"))
                      or bool(st.get("selects")) or bool(st.get("dropdowns")))
        has_choices = bool(st.get("radios")) or bool(st.get("checks"))
        has_graph = bool(st.get("graph"))
        # 图形题：只要当前小问是“画图”而不是选项，画完直接 Check，不交给文本模型
        if has_graph:
            try:
                _pn = int((st.get("part") or [0, 0])[0] or 0)
            except Exception:
                _pn = 0
            _gseg = self._web_part_text(st.get("text") or "", _pn).lower()
            _graph_only = any(k in _gseg for k in (
                "graph the parabola", "graph both functions", "graph the functions",
                "use the graphing tool", "use the graphing tool to graph"))
            # 有些题既画图又同时有顶点/截距填空，必须交给模型一起答；
            # 只有“纯画图题”才走快速通道。
            if _graph_only and not has_inputs and not has_choices:
                if key not in self._web_graph_done:
                    _graph = st.get("graph") or {}
                    _objs = self._web_graph_objects(st.get("text") or "", _graph)
                    if _objs:
                        self._web_status("灵梦：正在用图形工具画函数…", "info")
                        try:
                            _res = (drv.add_graph_objects_inline(_objs)
                                    if hasattr(drv, "add_graph_objects_inline")
                                    else drv.add_graph_objects(_objs))
                            if str(_res) != "ok":
                                _res = drv.add_graph_objects(_objs)
                        except Exception as e:
                            _res = f"exception:{e}"
                    else:
                        _pts = self._web_quadratic_points(_gseg, _graph)
                        if not _pts:
                            self._web_status("灵梦：图形题解析不出函数，停在原题。", "warn")
                            self._web_round_failed = True
                            return False
                        self._web_status("灵梦：正在用图形工具画抛物线…", "info")
                        _objq = [{"objectType": "quadratic",
                                  "points": [{"x": round(x, 3), "y": round(y, 3)}
                                             for x, y in _pts], "params": {}}]
                        try:
                            _res = (drv.add_graph_objects_inline(_objq)
                                    if hasattr(drv, "add_graph_objects_inline")
                                    else drv.draw_quadratic(_pts))
                            if str(_res) != "ok":
                                _res = drv.draw_quadratic(_pts)
                        except Exception as e:
                            _res = f"exception:{e}"
                    if str(_res) != "ok":
                        self._web_status(f"魔理沙：图形没画成（{_res}），停在原题。", "warn")
                        self._web_round_failed = True
                        return False
                    self._web_graph_done.add(key)
                    self._web_status("灵梦：图形已画好。", "ok")
                    # 内嵌图有些 Pearson 版本只画图不提交；Check 还是灰的就改用放大弹窗重画并 Save
                    try:
                        _st2 = drv.state() or {}
                        if _st2.get("hasCheck") and _st2.get("canCheck") is False and _objs:
                            self._web_status("灵梦：Check 还是灰的，改用放大图形框重画一次…", "warn")
                            _res2 = drv.add_graph_objects(_objs)
                            if str(_res2) == "ok":
                                self._web_status("灵梦：图形已在放大框里保存。", "ok")
                                time.sleep(1.2)
                    except Exception:
                        pass
                return self._web_finish_graph_only(drv, key)

        # 登录过期 / 人机验证：不要傻等
        low_text = (st.get("text") or "").lower()
        if not has_inputs and not has_choices and any(
            k in low_text for k in ("verify you are human", "captcha", "session expired",
                                    "your session has timed out", "sign in to continue",
                                    "please sign in")):
            self._web_status("灵梦：登录状态可能过期了，或者弹出了人机验证，先停下。", "err")
            self._web_round_failed = True
            return False

        if not st or (not has_inputs and not has_choices and not has_graph):
            now = time.time()
            if getattr(self, "_web_empty_since", 0) == 0:
                self._web_empty_since = now
            waited = now - self._web_empty_since
            if waited > 30:
                self._web_status("灵梦：等了 30 秒还没看到题目，先跳过这一页。", "warn")
                self._web_empty_since = 0
                return self._web_skip(drv, key)
            self._web_status(f"灵梦：等题目出现…（{int(waited)}s）")
            return True
        self._web_empty_since = 0

        if key in self._web_seen:
            self._web_status("灵梦：这题处理过了，等页面变化…")
            if self._web_wait_change(drv, key, timeout=8.0):
                return True
            _qs = [q for q in (st.get("questions") or []) if int(q.get("n") or 0) > 0]
            if _qs and all(self._web_q_done(q) for q in _qs):
                self._web_all_done = True
                self._web_status(
                    f"灵梦：全部题都处理完了（对 {self._web_ok} / 错 {self._web_fail}）。", "ok")
                return False
            # 同一题反复处理又不动：先入账再跳，绝不能卡死，也不能静默漏题。
            self._web_status("灵梦：页面一直没变化，这题先记待人工，自动继续下一题。", "warn")
            return self._web_skip(drv, key)
        if not has_inputs and not has_choices and not has_graph and st.get("radios_disabled"):
            self._web_status("灵梦：这页选项是禁用的（Review 页），试试能不能翻页…", "warn")
            if self._web_next(drv, key):
                return True
            self._web_status("灵梦：Review 页翻不动，先停下。", "warn")
            self._web_round_failed = True
            return False

        _is_retry = bool(self._web_hint)
        self._web_seen.add(key)
        if not _is_retry:
            self._web_question += 1
        text = (st.get("text") or "").strip()
        # 公式补读：MathML/KaTeX/MathJax 的可读文本常常不在 innerText 里（学自 Auto-Pearson）
        try:
            _math = drv.math_text()
        except Exception:
            _math = []
        if _math:
            _missing = [m for m in _math if m not in text]
            if _missing:
                _formula = "\n\n【公式】\n" + "\n".join(_missing[:10])
                st["text"] = text + _formula
                text += _formula
        if self._web_hint:
            text = self._web_hint + "\n\n" + text
            self._web_hint = ""
        part_n, part_m = 0, 0
        try:
            pv = st.get("part") or []
            if len(pv) == 2 and pv[1]:
                part_n, part_m = int(pv[0]), int(pv[1])
        except Exception:
            part_n, part_m = 0, 0
        drops = st.get("dropdowns") or []
        if drops:
            blocks = []
            for _i, _dd in enumerate(drops):
                try:
                    drv.dropdown_open(_dd["id"])
                    _opts = drv.dropdown_options()
                    drv.dropdown_close()
                except Exception:
                    _opts = []
                if _opts:
                    lines = " / ".join(f"{j + 1}) {o}" for j, o in enumerate(_opts))
                    ctx_label = (_dd.get("label") or "")[:120]
                    blocks.append(f"【下拉框 {_i + 1}】{ctx_label}\n可选：{lines}")
            if blocks:
                text += ("\n\n" + "\n".join(blocks)
                         + "\n（这是下拉框题：DROPDOWN 按顺序写每个下拉框要选的编号，用 ; 分隔）")

        if part_n:
            seg = ""
            try:
                mm = re.search(rf"Part {part_n}\b(.*?)(?=Part {part_n + 1}\b|\Z)", text, re.S)
                if mm:
                    seg = mm.group(1).strip()[:300]
            except Exception:
                seg = ""
            text = (f"当前是第 {part_n} 小问（共 {part_m} 问），只回答这一小问。\n"
                    + (seg + "\n\n" if seg else "") + text)
        focus_text = self._web_focus_text(st.get("text") or "", part_n)
        if self._web_hint:
            focus_text = self._web_hint + "\n\n" + focus_text
        self._web_current_key = key
        self.q.put(("clear", "src"))
        self.q.put(("append", "src", text, "body"))
        self.q.put(("clear", "trans"))
        ctx_t = self._web_ctx
        if ctx_t.get("translate") and ocr_local.looks_english(text):
            # 翻译放后台线程，和答案同时跑，不再互相等
            def _translate(_text=text, _ctx=ctx_t, _key=key):
                buf: list[str] = []
                try:
                    llm.chat_stream(_ctx["base"], _ctx["key"], _ctx["model"],
                                    prompts.translate_messages(_text),
                                    reasoning_effort=None, temperature=0.2,
                                    extra_body=_ctx["extra"] or None,
                                    on_delta=lambda c: buf.append(c),
                                    cancel=self.web_stop)
                except Exception as exc:
                    if getattr(self, "_web_current_key", "") == _key:
                        self.q.put(("append", "trans", f"[翻译失败] {exc}", "err"))
                    return
                if getattr(self, "_web_current_key", "") == _key and buf:
                    self.q.put(("append", "trans", "".join(buf), "body"))

            threading.Thread(target=_translate, daemon=True).start()
            self._web_status(f"慧音＋灵梦：第 {self._web_question} 题，翻译和答案一起上…", "info")
        else:
            self._web_status(f"慧音：第 {self._web_question} 题，正在读题…", "info")

        ctx = self._web_ctx
        imgs = st.get("imgs") or []
        use_img = bool(imgs) and bool(ctx.get("vision"))
        packet = question_reader.build_packet(st, focus_text)
        self._web_model_fails = getattr(self, "_web_model_fails", 0)
        spec = {}
        try:
            def _ask_engine(msgs, temperature=0.7, tag="sample"):
                return self._ask_cancellable(
                    ctx["base"], ctx["key"], ctx["model"], msgs, ctx,
                    temperature=temperature)

            engine = answer_engine.AnswerEngine(
                _ask_engine, samples=3, escalate=2, review=True, reasoner=True,
                on_status=lambda t: self._web_status(t, "info"),
                cancel=self.web_stop)
            result = engine.solve(packet)
            spec = result.spec
            self.q.put(("append", "ans",
                        f"（置信度 {result.confidence}，一致度 {result.agreement:.0%}，"
                        f"验算 {result.verified}）\n", "dim"))
            self._web_status(f"灵梦：答案置信度 {result.confidence}，"
                             f"一致度 {result.agreement:.0%}。", "info")
            self._web_model_fails = 0
        except answer_engine.SolveCancelled:
            return False
        except Exception as e:
            if self.web_stop.is_set():
                return False
            self._web_model_fails += 1
            self._web_status(f"魔理沙：多路求解失败——{e}（第 {self._web_model_fails} 次）", "err")
            if use_img:
                # 文字模型实在答不出时，才把截图交给视觉模型兜底
                try:
                    xs = [i["x"] for i in imgs]
                    ys = [i["y"] for i in imgs]
                    xe = [i["x"] + i["w"] for i in imgs]
                    ye = [i["y"] + i["h"] for i in imgs]
                    x = max(0, min(xs) - 40)
                    y = max(0, min(ys) - 160)
                    w = min(1600, max(xe) - x + 60)
                    h = min(1400, max(ye) - y + 60)
                    png = drv.capture_clip(x, y, w, h)
                    data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
                    self._web_status("灵梦：文字模型答不出，改看题目截图…", "info")
                    raw = self._ask_cancellable(
                        ctx.get("vision_base") or ctx["base"],
                        ctx.get("vision_key") or ctx["key"],
                        ctx["vision"],
                        prompts.web_messages_image(text, data_url),
                        {"effort": None, "extra": ctx["extra"]},
                    )
                    spec = prompts.parse_web_answer(raw)
                except Exception as e2:
                    self._web_status(f"魔理沙：视觉兜底也失败——{e2}", "warn")
            if not (spec.get("choices") or spec.get("value") or spec.get("matrix")
                    or spec.get("drops") or spec.get("values")):
                if self._web_model_fails >= 3:
                    self._web_model_fails = 0
                    self._web_status("魔理沙：连续失败三次，先把这题留给人工。", "warn")
                return self._web_skip(drv, key)

        # 如果模型思考期间又加载出新控件，当前答案可能不完整；用最新状态重算一次
        try:
            _live = drv.state() or {}
            _lf = [f for f in (_live.get("fields") or [])
                   if not f.get("disabled") and not f.get("readonly")]
            _li = [i for i in (_live.get("inputs") or [])
                   if not i.get("disabled") and not i.get("readonly")]
            _new = bool((_live.get("radios") or _live.get("checks"))
                        and not spec.get("choices"))
            _new = _new or bool((_lf or _li or _live.get("selects")
                                 or _live.get("dropdowns"))
                                and not (spec.get("values") or spec.get("matrix")
                                         or spec.get("value") or spec.get("drops")))
            if _new:
                self._web_status("魔理沙：选项刚加载出来，按最新页面重算…", "info")
                st = _live
                has_inputs = bool(_lf or _li or st.get("selects") or st.get("dropdowns"))
                has_choices = bool(st.get("radios")) or bool(st.get("checks"))
                drops = st.get("dropdowns") or []
                try:
                    _lp = st.get("part") or [0, 0]
                    _lpn = int(_lp[0]) if len(_lp) == 2 and _lp[1] else 0
                except Exception:
                    _lpn = 0
                packet2 = question_reader.build_packet(
                    st, self._web_focus_text(_live.get("text") or text, _lpn))
                try:
                    result2 = answer_engine.AnswerEngine(
                        _ask_engine, samples=2, escalate=1, review=False, reasoner=False,
                        on_status=lambda t: self._web_status(t, "info"),
                        cancel=self.web_stop).solve(packet2)
                    spec = result2.spec
                except Exception:
                    pass
        except Exception:
            pass

        # P0 竞态保护：模型思考期间页面可能已经换题/换控件。此时旧答案
        # 绝不能填到新页面；丢弃这一轮，下一轮会拿新快照重新求解。
        try:
            _guard_st = drv.state() or {}
            _old_sig = self._web_sig(st)
            _new_sig = self._web_sig(_guard_st)
            if _old_sig and _new_sig and _old_sig != _new_sig:
                self._web_status("灵梦：等答案时页面已经变了，丢掉旧答案重新读题…", "warn")
                self._web_seen.discard(key)
                time.sleep(0.5)
                return True
            if _guard_st.get("fields") or _guard_st.get("inputs") \
                    or _guard_st.get("radios") or _guard_st.get("checks"):
                st = _guard_st
        except Exception:
            pass

        if not spec.get("raw"):
            self._web_status("魔理沙：模型没回内容，先把这题留给人工", "warn")
            return self._web_skip(drv, key)

        _sig_parts = []
        if spec.get("choices"):
            _sig_parts.append("C:" + ",".join(spec["choices"]))
        if spec.get("values"):
            _sig_parts.append("V:" + "|".join(spec["values"]))
        if spec.get("matrix"):
            _sig_parts.append("M:" + str(spec["matrix"]))
        if spec.get("drops"):
            _sig_parts.append("D:" + ",".join(str(x) for x in spec["drops"]))
        _sig = ";".join(_sig_parts)
        if _sig and _sig in self._web_prev.get(key, set()):
            self._web_status("魔理沙：算出来还是同一个答案，不重复交了。", "warn")
            try:
                self._web_dismiss(drv)
            except Exception:
                pass
            # 能翻页就翻页；多小问翻不动就记待人工、去下一题，绝不死循环
            if not self._web_next(drv, key):
                if self._web_jump_next_unanswered(drv):
                    return True
                return self._web_skip(drv, key)
            return True

        if not (spec.get("choices") or spec.get("value") or spec.get("matrix")
                or spec.get("drops") or spec.get("values")):
            if use_img:
                self._web_status(
                    "灵梦：视觉模型没答出来——设置里把「视觉模型」配成多模态模型（如 glm-4v-flash），"
                    "并填「视觉接口 / 视觉 Key」", "warn")
                self.q.put(("append", "ans", "（视觉模型没给出答案，可能是纯文字模型看不懂图）\n", "err"))
            else:
                self._web_status("魔理沙：模型没给出答案，先跳过这题", "warn")
            return self._web_skip(drv, key)
        parts = []
        if spec.get("choices"):
            parts.append(("多选 " if len(spec["choices"]) > 1 else "选 ") + ",".join(spec["choices"]))
        if spec["matrix"]:
            r_, c_, vals = spec["matrix"]
            parts.append(f"{r_}×{c_} 矩阵 " + ", ".join(vals))
        if spec["value"]:
            parts.append("填 " + spec["value"])
        self.q.put(("append", "ans",
                    f"【第 {self._web_question} 题】" + ("；".join(parts) or spec["raw"][:80]) + "\n",
                    "head"))

        # ---- 选项（单选 / 多选）
        if st.get("radios") or st.get("checks"):
            letters = spec.get("choices") or ([spec["choice"]] if spec["choice"] else [])
            if not letters:
                self._web_status("灵梦：这题要选选项，但模型没给 CHOICE，跳过", "warn")
                return self._web_skip(drv, key)
            picked = drv.pick_multi(letters) if len(letters) > 1 else drv.pick_choice(letters[0])
            if picked != "ok":
                self._web_status(f"魔理沙：选项 {','.join(letters)} 没点上（{picked}），跳过", "warn")
                return self._web_skip(drv, key)
            time.sleep(0.7)
            # 有些 Pearson 题先选选项才会启用填空框，必须重新读一次当前小问
            try:
                _st_after = drv.state() or {}
                # 即使这题没有填空，也要刷新 st：radio 的 checked 进入 signature，
                # 不刷新会被下面的 P0 快照闸门误判成“页面又变了”。
                if _st_after:
                    st = _st_after
                    _af = [f for f in (st.get("fields") or [])
                           if not f.get("disabled") and not f.get("readonly")]
                    _ai = [i for i in (st.get("inputs") or [])
                           if not i.get("disabled") and not i.get("readonly")]
                    has_inputs = bool(_af or _ai or st.get("selects") or st.get("dropdowns"))
                    has_choices = bool(st.get("radios")) or bool(st.get("checks"))
                    drops = st.get("dropdowns") or []
            except Exception:
                pass

        # P0：填任何控件前再核对一次快照。Pearson 在选项加载/小问切换时
        # 经常替换 DOM；如果控件 UID/签名已经变了，旧答案必须丢弃重读。
        if not self._web_snapshot_intact(drv, st):
            self._web_status("灵梦：控件在填写前又变了，丢掉这轮答案重新读题…", "warn")
            self._web_seen.discard(key)
            time.sleep(0.4)
            return True

        # ---- Pearson 下拉框（xlFillinItem）：可以和填空同时存在
        boxes = st.get("fields") or st.get("inputs")
        if drops and spec.get("drops"):
            # 只把“真的有选项”的下拉框算进来；旧小问留下的空下拉框会打乱编号
            active = []
            for _dd in drops:
                try:
                    drv.dropdown_open(_dd["id"])
                    time.sleep(0.45)
                    _opts = drv.dropdown_options()
                    drv.dropdown_close()
                    if _opts:
                        active.append(_dd)
                except Exception:
                    try:
                        drv.dropdown_close()
                    except Exception:
                        pass
            picked = 0
            for _i, _dd in enumerate(active):
                if _i >= len(spec["drops"]):
                    continue
                try:
                    idx = int(spec["drops"][_i]) - 1
                except Exception:
                    continue
                for _try in range(3):
                    try:
                        drv.dropdown_open(_dd["id"])
                        time.sleep(0.4)
                        r = drv.dropdown_pick(idx)
                        time.sleep(0.4)
                        drv.dropdown_close()
                        if r == "ok":
                            picked += 1
                            break
                    except Exception:
                        try:
                            drv.dropdown_close()
                        except Exception:
                            pass
                        time.sleep(0.4)
            need = min(len(active), len(spec["drops"]))
            if need and picked < need:
                self._web_status(
                    f"魔理沙：下拉框只选中 {picked}/{need}，再等一会儿重试…", "warn")
                time.sleep(1.5)
                # 再试一次空下拉框
                for _i, _dd in enumerate(active):
                    if _i >= len(spec["drops"]):
                        continue
                    try:
                        idx = int(spec["drops"][_i]) - 1
                    except Exception:
                        continue
                    try:
                        drv.dropdown_open(_dd["id"])
                        time.sleep(0.5)
                        r = drv.dropdown_pick(idx)
                        time.sleep(0.4)
                        drv.dropdown_close()
                        if r == "ok":
                            picked += 1
                    except Exception:
                        pass
                if picked < need:
                    self._web_status(
                        f"魔理沙：下拉框 {picked}/{need} 还是没选上，停在原题重试。", "warn")
                    self._web_round_failed = True
                    self._web_seen.discard(key)
                    return False
            if need:
                self.q.put(("append", "ans", "已选下拉框\n", "dim"))

        # ---- 原生下拉框（select）：可能不止一个
        if st.get("selects"):
            sels = st["selects"]
            vals = spec.get("values") or ([spec["value"]] if spec["value"] else [])
            ok_all = True
            any_done = False
            for _i, sel in enumerate(sels):
                v = vals[_i] if _i < len(vals) else (vals[0] if len(sels) == 1 and vals else "")
                if spec.get("drops") and _i == 0:
                    opts = sel.get("options") or []
                    try:
                        idx = int(spec["drops"][0]) - 1
                    except Exception:
                        idx = -1
                    if 0 <= idx < len(opts):
                        v = opts[idx]
                if not v:
                    continue
                any_done = True
                if drv.select_option(sel["id"], v) != "ok":
                    ok_all = False
                    break
                time.sleep(0.3)
            if any_done and not ok_all:
                self._web_status("魔理沙：有一个下拉框没选上，先跳过这题", "warn")
                return self._web_skip(drv, key)

        # ---- 填空
        if has_inputs and boxes and (spec["matrix"] or spec.get("values") or spec["value"]):
            targets = self._web_targets(st, part_n)
            _blank = [b for b in targets
                      if "enter your response" in str(b.get("label") or "").lower()]
            if _blank:
                targets = _blank + [b for b in targets if b not in _blank]
            vals = spec.get("values") or ([spec["value"]] if spec["value"] else [])

            if spec["matrix"]:
                rows, cols, cells = spec["matrix"]
                if len(cells) < rows * cols:
                    self._web_status("魔理沙：矩阵数值不够，跳过这题", "warn")
                    return self._web_skip(drv, key)
                fid = targets[0]["id"] if targets else boxes[0]["id"]
                cells = [latex.to_editor_input(v) for v in cells]
                err = drv.fill_matrix(fid, rows, cols, cells)
                if err:
                    self._web_status("魔理沙：填矩阵失败——" + err, "warn")
                    return self._web_skip(drv, key)
                self.q.put(("append", "ans", "已填入矩阵\n", "dim"))

            elif len(vals) > 1:
                _only = _blank or targets
                if len(_only) < len(vals):
                    self._web_status("魔理沙：空框不够，跳过这题", "warn")
                    return self._web_skip(drv, key)
                for b, v in zip(_only[:len(vals)], vals):
                    if not self._web_fill(drv, b["id"], v):
                        self._web_status("魔理沙：多空答案没填全，先跳过", "warn")
                        return self._web_skip(drv, key)
                self.q.put(("append", "ans", "已填入： " + " ; ".join(vals) + "\n", "dim"))

            else:
                if not targets:
                    self._web_status("魔理沙：找不到输入框，跳过", "warn")
                    return self._web_skip(drv, key)
                fid = targets[0]["id"]
                if not self._web_fill(drv, fid, spec["value"]):
                    self._web_status("魔理沙：答案没填进去（编辑器吞输入），先跳过这题", "warn")
                    return self._web_skip(drv, key)
                self.q.put(("append", "ans", "已填入：" + str(drv.field_label(fid))[:60] + "\n", "dim"))

        # ---- 图形题：用 Pearson 的 GraphControl API 画二次函数
        if has_graph:
            try:
                _pn, _pm = (st.get("part") or [0, 0])[:2]
                _seg = self._web_part_text(st.get("text") or "", int(_pn or 0)).lower()
            except Exception:
                _seg = (st.get("text") or "").lower()
            _need_graph = any(k in _seg for k in (
                "graph the parabola", "graph both", "graph the functions",
                "graph the equation", "use the graphing tool", "graph f",
                "graph y"))
            if _need_graph:
                if key not in self._web_graph_done:
                    _graph = st.get("graph") or {}
                    _multi = ("graph both functions" in _seg
                              or "graph the functions" in _seg
                              or "graph both" in _seg)
                    _objs = self._web_graph_objects(st.get("text") or "", _graph) if _multi else []
                    if _objs:
                        self._web_status("灵梦：正在用图形工具画两条函数…", "info")
                        try:
                            _res = drv.add_graph_objects(_objs)
                        except Exception as e:
                            _res = f"exception:{e}"
                    else:
                        _pts = self._web_quadratic_points(_seg, _graph)
                        if not _pts:
                            self._web_status(
                                "灵梦：这道图形题的公式没解析出来，停在原题。", "warn")
                            self._web_round_failed = True
                            return False
                        self._web_status("灵梦：正在用图形工具画抛物线…", "info")
                        try:
                            _res = drv.draw_quadratic(_pts)
                        except Exception as e:
                            _res = f"exception:{e}"
                    if str(_res) != "ok":
                        self._web_status(
                            f"魔理沙：图形没画成（{_res}），停在原题。", "warn")
                        self._web_round_failed = True
                        return False
                    self._web_graph_done.add(key)
                    self._web_status("灵梦：图形已画好。", "ok")
                    # Pearson 保存图形后 Check 有时延迟 1~3 秒才启用，等它一下
                    for _wait in range(10):
                        try:
                            _stg = drv.state() or {}
                        except Exception:
                            _stg = {}
                        if not _stg.get("hasCheck") or _stg.get("canCheck") is not False:
                            break
                        time.sleep(0.35)

        # ---- 交卷（重新读一次：有些题选了答案后 Check 按钮才出现）
        try:
            st_now = drv.state() or st
        except Exception:
            st_now = st

        if st_now.get("hasCheck"):
            if st_now.get("canCheck") is False:
                self._web_status(
                    "灵梦：Check 还是灰的，说明还有空没填全；停在原题重来。", "warn")
                self._web_round_failed = True
                self._web_seen.discard(key)
                return False
            self._web_status("灵梦：点 Check answer…", "info")
            if not self._web_click_check(drv):
                # 再给 Pearson 一次渲染时间，避免刚换题时误判
                time.sleep(1.2)
                if not self._web_click_check(drv):
                    self._web_status("灵梦：Check 按钮一直没出现，停在原题等一下。", "warn")
                    self._web_round_failed = True
                    return False
            fb = self._web_feedback(drv)
            if not fb:
                # 有时第一次点击被页面吞掉；按钮还在就再点一次
                try:
                    if (drv.state() or {}).get("hasCheck"):
                        self._web_status("灵梦：没等到判分，再点一次 Check answer…", "warn")
                        try:
                            drv.click_text_native(r"^(check answer|final check)$")
                        except Exception:
                            self._web_click_check(drv)
                        fb = self._web_feedback(drv, timeout=10.0)
                except Exception:
                    pass
            if fb == "correct":
                self._web_ok += 1
                self._web_round_failed = False
                self._web_status(
                    f"灵梦：第 {self._web_question} 题答对了。（对 {self._web_ok} / 错 {self._web_fail}）", "ok")
                if st_now.get("inDialog"):
                    self._web_status("魔理沙：练习题答对了（弹窗里不点 Next，避免翻掉真题）", "ok")
                    return False
                if drv.dialog_next():
                    if self._web_next(drv, key):
                        return True
                # 多小问：弹窗只有 OK -> 点掉；下一小问出现就继续，否则翻下一题
                self._web_dismiss(drv)
                time.sleep(0.6)
                if self._web_wait_change(drv, key, timeout=15):
                    return True
                if self._web_next(drv, key):
                    return True
                if self._web_jump_next_unanswered(drv):
                    return True
                self._web_status(
                    f"灵梦：没有下一题了，全自动收工（对 {self._web_ok} / 错 {self._web_fail}）。", "ok")
                return False

            if fb == "incorrect":
                self._web_fail += 1
                self._web_round_failed = True
                fb_text = drv.feedback_text()
                wrong = ("多选 " + ",".join(spec["choices"])) if spec.get("choices") else \
                    str(spec.get("values") or spec.get("value") or "")
                self._web_prev.setdefault(key, set()).add(_sig)
                tries = self._web_try.get(key, 0) + 1
                self._web_try[key] = tries
                self.q.put(("append", "ans", f"× 判错（第 {tries} 次）：{fb_text[:60]}\n", "err"))
                drv.click_text(r"^\s*ok\s*$")
                time.sleep(0.8)
                if tries <= 2 and not st_now.get("inDialog"):
                    self._web_hint = (f"上一次填的答案是 【{wrong}】，被判错了。"
                                      f"题目给的提示是：【{fb_text[:120]}】。"
                                      "请换个思路重新计算，务必给出正确结果。")
                    self._web_seen.discard(key)
                    self._web_status(
                        f"魔理沙：答错了，带着提示再算一次（第 {tries} 次重试）…", "warn")
                    return True
                if not self._web_continue_wrong:
                    self._web_status(
                        f"魔理沙：第 {self._web_question} 题答错了，停下来给你看。", "err")
                    return False
                self._web_status(
                    f"魔理沙：第 {self._web_question} 题答错了，继续下一题。（对 {self._web_ok} / 错 {self._web_fail}）",
                    "warn")
                if drv.dialog_next():
                    self._web_next(drv, key)
                else:
                    self._web_dismiss(drv)
                    time.sleep(0.6)
                    if not self._web_wait_change(drv, key, timeout=15):
                        self._web_next(drv, key)
                return True

            drv.click_text(r"^\s*ok\s*$")
            self._web_status("灵梦：没看到判分结果，先检查题目标记…", "warn")
            try:
                for _ in range(3):
                    if self._web_jump_next_unanswered(drv):
                        return True
                    time.sleep(0.7)
            except Exception:
                pass
            self._web_status(
                "灵梦：没看到判分结果，停在原题检查，不跳题。", "warn")
            self._web_round_failed = True
            return False
        if st_now.get("hasNext"):
            try:
                _qn = int(st_now.get("qno") or 0)
                _q = next((x for x in (st_now.get("questions") or [])
                           if int(x.get("n") or 0) == _qn), None)
                if _q and "partial" in str(_q.get("status") or "").lower():
                    self._web_mark_partial_done(_qn)
            except Exception:
                pass
            self._web_status("灵梦：这题没有 Check answer，直接下一题", "info")
            if not self._web_next(drv, key):
                time.sleep(1.2)
                if not self._web_next(drv, key) and not self._web_jump_next_unanswered(drv):
                    self._web_status("灵梦：翻不到下一题，停在原题。", "warn")
                    return False
            return True

        if self._web_jump_next_unanswered(drv):
            return True
        self._web_status(
            f"灵梦：没有下一题了，全自动收工（对 {self._web_ok} / 错 {self._web_fail}）。", "ok")
        return False

    # ------------------------------------------------------------------ 追问 / 余额
    def _send_followup(self) -> None:
        text = self.follow_var.get().strip()
        if not text:
            return
        if self.busy:
            self._status("灵梦：等我把这题说完。", "warn")
            return
        if not self._panel_text("ans"):
            self._status("灵梦：先解一道题，再来追问。", "warn")
            return
        try:
            ctx = self._ctx()
        except Exception as e:
            self._status(str(e), "err")
            return
        self.follow_var.set("")
        if not self.messages:
            self.messages = [{"role": "user", "content": self._panel_text("src")}]
        self.messages.append({"role": "user", "content": text})
        self._append("ans", f"\n\n【追问】{text}\n\n", "head")
        self._status("慧音：正在补充说明…", "info")
        self.busy = True
        threading.Thread(target=self._followup_worker, args=(ctx, list(self.messages)),
                         daemon=True).start()

    def _followup_worker(self, ctx: dict, messages: list[dict]) -> None:
        try:
            res = llm.chat_stream(
                ctx["base"], ctx["key"], ctx["model"], messages,
                reasoning_effort=ctx["effort"], temperature=ctx["temperature"],
                extra_body=ctx["extra"] or None,
                on_delta=self._stream_cb("ans", "body"), cancel=self.cancel,
            )
            self.messages.append({"role": "assistant", "content": res.text})
            prefix = "【追问】"
            if res.reasoning:
                self.q.put(("meta", self._cost_text(ctx["model"], res.usage)))
            self.q.put(("status", f"{prefix}已补充", "ok"))
        except Exception as e:
            self.q.put(("append", "ans", f"\n[追问失败] {e}\n", "err"))
            self.q.put(("status", f"追问失败：{e}", "err"))
        finally:
            self._flush_stream("ans", "body")
            self.q.put(("busy", False))

    def _check_balance_async(self, key: str, base: str, done) -> None:
        from modules import balance as _balance
        from modules import toast as _toast

        def notify(text: str) -> None:
            head = (text or "")[:16]
            speaker = "reimu"
            if "八云紫" in head:
                speaker = "yukari"
            elif "魔理沙" in head:
                speaker = "marisa"
            self._notify("balance", "博麗神社 · 香火钱", text, avatar=speaker)

        if not key:
            text = "灵梦：连通行密钥都没填，你是来参拜的还是来许愿的？"
            done(text, False)
            threading.Thread(target=notify, args=(text,), daemon=True).start()
            return

        self._balance_done = done

        def work() -> None:
            try:
                res = _balance.check(base, key)
                text, ok = res["text"], bool(res["ok"])
            except Exception as e:
                msg = str(e)
                if msg.startswith(("灵梦：", "八云紫：", "魔理沙：")):
                    text = msg
                else:
                    text = f"灵梦：翻钱包失败——{msg}"
                ok = False
            self.q.put(("balance_result", text, ok))
            notify(text)

        threading.Thread(target=work, daemon=True).start()

    def _on_clip_image(self, img) -> None:
        if self.busy or self.web_on:
            return
        try:
            self._start_job("recognize", image=img, source="剪贴板截图")
        except Exception as e:
            self._status(str(e), "err")

    # ------------------------------------------------------------------ 消息泵
    def _pump(self) -> None:
        try:
            for _ in range(500):
                self._handle(self.q.get_nowait())
        except queue.Empty:
            pass
        try:
            self._maybe_apply_pending_theme()
        except Exception:
            pass
        self.root.after(45, self._pump)

    def _handle(self, ev: tuple) -> None:
        kind = ev[0]
        if kind == "append":
            self._append(ev[1], ev[2], ev[3] if len(ev) > 3 else "body")
        elif kind == "clear":
            self._clear_panel(ev[1])
        elif kind == "status":
            self._status(ev[1], ev[2] if len(ev) > 2 else "info")
        elif kind == "meta":
            self.meta_var.set(ev[1])
        elif kind == "balance_result":
            cb = getattr(self, "_balance_done", None)
            self._balance_done = None
            if cb is not None:
                try:
                    cb(ev[1], bool(ev[2]))
                except Exception:
                    pass
        elif kind == "busy":
            self._set_busy(bool(ev[1]))
        elif kind == "windows":
            self._apply_windows(ev[1])
            self._status(f"紫：境界里找到 {len(ev[1])} 个窗口，选题目所在的那个。", "info")
        elif kind == "models":
            self._apply_models(ev[1])
        elif kind == "models_error":
            self._status(f"魔理沙：模型列表拿不到——{ev[1]}", "err")
        elif kind == "web_off":
            if len(ev) > 1 and ev[1] != getattr(self, "_web_gen", 0):
                return
            self.web_on = False
            self.web_var.set(False)
            try:
                self.btn_web.configure(text="⛩  开始退治")
            except Exception:
                pass
            self._refresh_action_status()
        elif kind == "notify":
            self._do_notify(*ev[1:8])
        elif kind == "update_result":
            self._on_update_result(ev[1], ev[2], ev[3])
        elif kind == "clip_image":
            self._on_clip_image(ev[1])
        elif kind == "hotkey":
            if ev[1] == "capture":
                self.action_capture()
            elif ev[1] == "answer":
                self.action_answer_only()

    def _append(self, panel: str, text: str, tag: str = "body") -> None:
        txt = self.panels.get(panel)
        if txt is None or not text:
            return
        if panel != "src":
            txt.configure(state="normal")
        if self._placeholder_only(panel):
            txt.delete("1.0", "end")
        txt.insert("end", text, tag)
        txt.see("end")
        if panel != "src":
            txt.configure(state="disabled")
        self._refresh_scrollbar(panel)

    def _clear_panel(self, panel: str) -> None:
        txt = self.panels.get(panel)
        if txt is None:
            return
        if panel != "src":
            txt.configure(state="normal")
        txt.delete("1.0", "end")
        if panel != "src":
            txt.configure(state="disabled")
        self._show_placeholder(panel)
        self._refresh_scrollbar(panel)

    def _placeholder_only(self, panel: str) -> bool:
        txt = self.panels.get(panel)
        ph = PLACEHOLDERS.get(panel, "")
        if txt is None or not ph:
            return False
        return txt.get("1.0", "end-1c").strip() == ph.strip()

    def _show_placeholder(self, panel: str) -> None:
        txt = self.panels.get(panel)
        ph = PLACEHOLDERS.get(panel, "")
        if txt is None or not ph:
            return
        if txt.get("1.0", "end-1c").strip():
            return
        editable = panel == "src"
        if not editable:
            txt.configure(state="normal")
        txt.insert("1.0", ph, "placeholder")
        if not editable:
            txt.configure(state="disabled")
        self._refresh_scrollbar(panel)

    def _refresh_scrollbar(self, panel: str) -> None:
        sb = self._scrollbars.get(panel)
        txt = self.panels.get(panel)
        if sb is None or txt is None:
            return
        if txt.get("1.0", "end-1c").strip() and not self._placeholder_only(panel):
            sb.grid()
        else:
            sb.grid_remove()

    def _panel_text(self, panel: str) -> str:
        txt = self.panels.get(panel)
        if txt is None or self._placeholder_only(panel):
            return ""
        return txt.get("1.0", "end").strip()

    def _copy_panel(self, panel: str) -> None:
        text = self._panel_text(panel)
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._status(TIPS["copied"], "ok")

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        if not busy:
            self.cancel.clear()
        try:
            self.btn_capture.configure(state="disabled" if busy else "normal")
        except tk.TclError:
            pass

    def _status(self, text: str, level: str = "info") -> None:
        color = {"info": C["muted"], "ok": C["ok"], "warn": C["warn"], "err": C["err"]}.get(level, C["muted"])
        self.status_var.set(text)
        self.status_label.configure(fg=color)
        head = text[:10]
        for name, key in SPEAKERS.items():
            if head.startswith(name):
                icon = getattr(self, "_status_icons", {}).get(key)
                if icon is not None:
                    self.status_avatar.configure(image=icon)
                break

    def _rotate_quote(self) -> None:
        """闲着的时候，让灵梦和魔理沙轮流说两句。"""
        try:
            if not self.busy and not self.auto_var.get() and not getattr(self, "web_on", False):
                cur = self.status_var.get().strip()
                if cur in QUOTES or cur in ("", TIPS["ready"]):
                    self._quote_idx = (getattr(self, "_quote_idx", -1) + 1) % len(QUOTES)
                    self._status(QUOTES[self._quote_idx], "info")
        finally:
            self.root.after(14000, self._rotate_quote)

    def _apply_models(self, models: list[str]) -> None:
        self._models = list(models)
        box = getattr(self, "_dlg_model_box", None)
        vbox = getattr(self, "_dlg_vision_box", None)
        var = getattr(self, "_dlg_model_var", None)
        for w, vals in ((box, models), (vbox, ["（使用答题模型）"] + models)):
            try:
                if w is not None:
                    w.configure(values=vals)
            except Exception:
                pass
        if var is not None and not var.get() and models:
            var.set(models[0])
        if models and not self.model_var.get():
            self.model_var.set(models[0])
        self._status(f"魔理沙：拿到 {len(models)} 个模型了！", "ok")

    # ------------------------------------------------------------------ 退出
    def _on_close(self) -> None:
        try:
            self.cancel.set()
            self.web_stop.set()
            if self.clip_watcher is not None:
                self.clip_watcher.stop()
            self._save_config()
        except Exception:
            pass
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        self.root.destroy()


def _ensure_assets() -> None:
    """素材缺失时自动生成（角色立绘需联网下载，详见 tools/fetch_characters.py）。"""
    need = ("banner.png", "splash.png", "icon.ico")
    if all(os.path.exists(os.path.join(ASSETS, f)) for f in need):
        return
    try:
        sys.path.insert(0, os.path.join(HERE, "tools"))
        import make_assets  # noqa: F401

        make_assets.main()
    except Exception:
        pass


def make_splash(root: tk.Tk) -> tuple[tk.Toplevel, object] | None:
    """先开启动画面：新主题按时段选图，经典主题保持原图。"""
    cfg = settings.load()
    active = (cfg.get("theme") == theme.THEME_NEW and cfg.get("theme_unlocked"))
    if active:
        phase = banner_time.phase_for_now()
        try:
            img = theme.compose_splash(ASSETS, phase)
        except Exception:
            active = False
        if active:
            top = tk.Toplevel(root)
            top.overrideredirect(True)
            top.attributes("-topmost", True)
            w, h = img.width, img.height
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            top.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 2)}")
            photo = ImageTk.PhotoImage(img)
            canvas = tk.Canvas(top, width=w, height=h, bd=0, highlightthickness=0,
                               bg="#05030a")
            canvas.pack()
            canvas.create_image(0, 0, anchor="nw", image=photo)

            def _splash_text(x, y, text, fill, font, anchor="center"):
                for dx, dy in ((2, 2), (1, 1)):
                    canvas.create_text(x + dx, y + dy, text=text, fill="#170f20",
                                       font=font, anchor=anchor)
                canvas.create_text(x, y, text=text, fill=fill, font=font, anchor=anchor)

            _splash_text(640, 62, "符卡作业簿", "#fffaf6", ("KaiTi", 38, "bold"))
            _splash_text(640, 108, "～ 幻想郷・宿題退治 ～", theme.NEW_COLORS["gold"],
                         ("Yu Gothic UI", 14))
            _splash_text(640, 690, f"v{settings.APP_VERSION}  ·  Shinichi · Fastrof · 会哈气の祥  ·  MIT License",
                         "#e3d8ea", ("Microsoft YaHei UI", 10))
            try:
                top.focus_force()
            except tk.TclError:
                pass
            return top, photo

    path = os.path.join(ASSETS, "splash.png")
    if not os.path.exists(path):
        return None
    try:
        img = Image.open(path)
        photo = ImageTk.PhotoImage(img)
    except Exception:
        return None
    top = tk.Toplevel(root)
    top.overrideredirect(True)
    top.attributes("-topmost", True)
    w, h = img.width, img.height
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    top.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 2)}")
    tk.Label(top, image=photo, bd=0, bg=C["bg"]).pack()
    try:
        top.focus_force()
    except tk.TclError:
        pass
    return top, photo


def show_activation(root: tk.Tk, reason: str = "", allow_trial: bool = False) -> bool:
    """博麗神社的结界许可窗口（一机一码激活）。返回 True 表示已获得许可。"""
    from modules import clipboard
    from modules import license as lic

    F = "Microsoft YaHei UI"
    win = tk.Toplevel(root)
    win.title("博麗神社 · 结界许可")
    win.configure(bg=C["bg"])
    win.resizable(False, False)
    w, h = 800, 640
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    win.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")
    win.attributes("-topmost", True)
    win.after(400, lambda: win.attributes("-topmost", False))
    result = {"ok": False}
    machine = lic.machine_code()

    tk.Label(win, text="博麗神社 · 结界许可", bg=C["bg"], fg=C["gold"],
             font=(F, 24, "bold")).pack(pady=(16, 0))
    tk.Label(win, text="～ 无许可者，不得入内 ～", bg=C["bg"], fg=C["muted"],
             font=(F, 11)).pack(pady=(2, 4))
    tk.Label(win, text="灵梦：想借结界把作业退治掉？先拿一张许可来。",
             bg=C["bg"], fg=C["text"], font=(F, 10)).pack(pady=(0, 10))

    box = tk.Frame(win, bg=C["panel"], highlightbackground=C["border"],
                   highlightthickness=1, padx=18, pady=12)
    box.pack(fill="x", padx=30)
    tk.Label(box, text="本机灵符（机器码）", bg=C["panel"], fg=C["muted"],
             font=(F, 9)).pack(anchor="w")
    code_row = tk.Frame(box, bg=C["panel"])
    code_row.pack(fill="x", pady=(2, 4))
    tk.Label(code_row, text=machine, bg=C["panel"], fg=C["gold"],
             font=("Consolas", 17, "bold")).pack(side="left")

    tip = tk.Label(win, text=reason or "把收到的咒文贴在这里，念一遍就能进结界。",
                   bg=C["bg"], fg=C["muted"], font=(F, 9))

    def copy_machine() -> None:
        try:
            clipboard.copy_text(machine)
            tip.configure(text="灵符已收好。寄给神社的任意一位，就能换回许可咒文。", fg=C["ok"])
        except Exception:
            pass

    tk.Button(code_row, text="收下灵符", command=copy_machine, bg=C["panel2"], fg=C["text"],
              relief="flat", bd=0, padx=14, pady=2, cursor="hand2",
              font=(F, 9)).pack(side="left", padx=(14, 0))

    tk.Label(box, text="把灵符寄给神社的任何一位（点一下邮箱即可复制）——",
             bg=C["panel"], fg=C["muted"], font=(F, 9)).pack(anchor="w", pady=(8, 2))
    people = [("博麗灵梦 · Shinichi", lic.EMAILS[0][1]),
              ("八云紫 · Fastrof", lic.EMAILS[1][1])]
    mail_tip = tk.Label(box, text="", bg=C["panel"], fg=C["ok"], font=(F, 9), anchor="w")
    for name, mail in people:
        lb = tk.Label(box, text=f"{name}　{mail}", bg=C["panel"], fg=C["gold"],
                      cursor="hand2", font=(F, 10, "underline"), anchor="w")
        lb.pack(anchor="w", pady=1)

        def _copy(_e=None, m=mail) -> None:
            try:
                clipboard.copy_text(m)
                mail_tip.configure(text=f"已复制 {m}，直接粘贴到收件人即可。", fg=C["ok"])
            except Exception:
                mail_tip.configure(text="复制失败，请手动抄一下。", fg=C["err"])

        lb.bind("<Button-1>", _copy)
        Tooltip(lb, "点击复制这个邮箱")
    mail_tip.pack(anchor="w", pady=(2, 0))

    tk.Label(win, text="许可咒文（激活码）", bg=C["bg"], fg=C["text"],
             font=(F, 10, "bold")).pack(anchor="w", padx=34, pady=(14, 2))
    code_var = tk.StringVar()
    entry = tk.Entry(win, textvariable=code_var, bg=C["input"], fg=C["text"],
                     insertbackground=C["text"], relief="flat", font=("Consolas", 11))
    entry.pack(fill="x", padx=34, ipady=7)
    tip.pack(anchor="w", padx=34, pady=(6, 0))
    tk.Label(win, text="紫：五天的试用要是用完了，就得来神社登记咯。",
             bg=C["bg"], fg=C["muted"], font=(F, 9)).pack(anchor="w", padx=34, pady=(4, 0))

    def activate() -> None:
        code = code_var.get().strip()
        ok, msg, _ = lic.verify_code(code)
        if ok:
            try:
                lic.save_license(code)
            except Exception as e:
                tip.configure(text=f"许可没写进神社的登记簿：{e}", fg=C["err"])
                return
            result["ok"] = True
            tip.configure(text="结界开了，进去吧。" + msg, fg=C["ok"])
            win.after(600, win.destroy)
        else:
            tip.configure(text=f"灵梦：{msg}", fg=C["err"])

    btns = tk.Frame(win, bg=C["bg"])
    btns.pack(side="bottom", fill="x", padx=34, pady=14)

    def start_trial() -> None:
        from modules import license as lic

        lic.start_trial()
        result["ok"] = True
        try:
            win.destroy()
        except Exception:
            pass

    tk.Button(btns, text="解开结界", command=activate, bg=C["accent"], fg="#ffffff",
              activebackground=C["accent_dark"], activeforeground="#ffffff",
              relief="flat", bd=0, padx=26, pady=7, cursor="hand2",
              font=(F, 11, "bold")).pack(side="right")
    if allow_trial:
        tk.Button(btns, text="先试用 5 天", command=start_trial, bg=C["panel2"],
                  fg=C["gold"], activebackground=C["accent_dark"], activeforeground="#ffffff",
                  relief="flat", bd=0, padx=18, pady=7, cursor="hand2",
                  font=(F, 10, "bold")).pack(side="right", padx=(0, 10))
    tk.Button(btns, text="先回人间", command=win.destroy, bg=C["panel2"], fg=C["text"],
              relief="flat", bd=0, padx=18, pady=7, cursor="hand2",
              font=(F, 10)).pack(side="right", padx=(0, 10))
    tk.Label(btns, text=f"符卡作业簿 v{settings.APP_VERSION} · MIT License",
             bg=C["bg"], fg=C["muted"], font=(F, 9)).pack(side="left")

    entry.bind("<Return>", lambda _e: activate())
    entry.focus_set()
    win.protocol("WM_DELETE_WINDOW", win.destroy)
    root.wait_window(win)
    return result["ok"]


def _boot_log(msg: str) -> None:
    """记录启动时的授权判断，方便排查"为什么直接进主界面"。"""
    try:
        from modules import settings as _s

        with open(os.path.join(_s.config_dir(), "boot.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + f" v{_s.APP_VERSION} " + msg + "\n")
    except Exception:
        pass


def main() -> None:
    _ensure_assets()
    capture.make_dpi_aware()
    capture.set_app_user_model_id("Shinichi.SpellCardHomework")

    root = tk.Tk()
    root.withdraw()
    try:
        root.tk.call("tk", "scaling", capture.dpi_scale() * 96 / 72)
    except Exception:
        pass
    icon = os.path.join(ASSETS, "icon.ico")
    if os.path.exists(icon):
        try:
            root.iconbitmap(icon)
        except Exception:
            pass
    icon_png = os.path.join(ASSETS, "icon.png")
    if os.path.exists(icon_png):
        try:
            _ip = ImageTk.PhotoImage(Image.open(icon_png).resize((64, 64), Image.LANCZOS))
            root.iconphoto(True, _ip)
            root._icon_ref = _ip
        except Exception:
            pass

    splash = make_splash(root)
    state: dict = {"app": None, "booted": False}

    def boot() -> None:
        if state["booted"]:
            return
        state["booted"] = True
        trial_notice = ""
        # 关键：必须在任何 settings.save / 激活前记下“首次安装”的两个事实，
        # 不能只看版本号（老用户根本没有 onboarding 字段）。
        config_existed = first_run.config_exists(settings.CONFIG_PATH)
        try:
            from modules import license as _lic

            access, lic_msg, _days = _lic.check_access()
        except Exception as _e:
            access, lic_msg, _days = "tampered", f"授权检查失败：{_e}", 0
        pre_access = access
        _boot_log(f"access={access} config_existed={config_existed} "
                  f"exe={sys.executable} argv={sys.argv[0]}")
        if access == "licensed":
            pass
        elif access == "trial":
            trial_notice = f"紫：{lic_msg}，结界随时会关哦。"
        elif access == "fresh":
            if splash is not None:
                try:
                    if splash[0].winfo_exists():
                        splash[0].destroy()
                except Exception:
                    pass
            _boot_log("show activation (fresh)")
            if not show_activation(
                root, "灵梦：第一次来？可以先用五天，或者拿一张许可咒文来。",
                allow_trial=True,
            ):
                try:
                    root.destroy()
                except Exception:
                    pass
                return
            access2, lic_msg2, _days2 = _lic.check_access()
            if access2 == "licensed":
                pass
            elif access2 == "trial":
                trial_notice = f"紫：{lic_msg2}，结界随时会关哦。"
            else:
                try:
                    root.destroy()
                except Exception:
                    pass
                return
        else:
            if splash is not None:
                try:
                    if splash[0].winfo_exists():
                        splash[0].destroy()
                except Exception:
                    pass
            _boot_log(f"show activation ({access})")
            if not show_activation(root, f"灵梦：{lic_msg}。先拿一张许可来吧。"):
                try:
                    root.destroy()
                except Exception:
                    pass
                return
            # 激活后必须真的拿到许可，否则直接退出
            if not _lic.status()[0]:
                try:
                    root.destroy()
                except Exception:
                    pass
                return
        try:
            app = App(root)
        except Exception:
            import traceback

            messagebox.showerror(APP_TITLE, f"启动失败：\n{traceback.format_exc()[-1500:]}")
            root.destroy()
            return
        state["app"] = app

        # 双保险：没有许可/试用就绝不显示主界面
        try:
            _final = _lic.check_access(update=False)[0]
        except Exception:
            _final = "tampered"
        _boot_log(f"final={_final}")
        if _final not in ("licensed", "trial"):
            _boot_log("blocked: no license/trial")
            try:
                root.destroy()
            except Exception:
                pass
            return

        root.protocol("WM_DELETE_WINDOW", app._on_close)
        root.deiconify()
        root.lift()
        if trial_notice:
            try:
                app._status(trial_notice, "warn")
            except Exception:
                pass
        if icon and os.path.exists(icon):
            try:
                capture.set_window_icon(int(root.wm_frame(), 16), icon)
            except Exception:
                pass
        if splash is not None:
            try:
                if splash[0].winfo_exists():
                    splash[0].destroy()
            except Exception:
                pass
        try:
            app.maybe_start_first_run(pre_access, config_existed)
        except Exception:
            pass

    if splash is not None:
        splash[0].bind("<Button-1>", lambda _e: boot())
        splash[0].bind("<Key>", lambda _e: boot())
    root.after(1000, boot)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover
        import traceback

        try:
            messagebox.showerror(APP_TITLE, f"启动失败：\n{exc}\n\n{traceback.format_exc()[-1500:]}")
        except Exception:
            raise























