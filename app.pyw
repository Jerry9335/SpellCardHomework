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

# 结界的门牌：专门记「这个调试端口是本程序亲手张开的」。
# 紫：境界有很多扇门，不是每扇都归我管——不是自己开的就不去关，
# 免得把别人正在用的窗户一起收进缝隙里。
BARRIER_MARK = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
    "SpellCardHomework", "barrier.port")

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
    # 文文是号外/更新提示的固定说话人；漏了 mapping 时状态栏会沿用上一位
    # 的头像（实测曾顶着八云紫的头像播报号外）。
    "文文": "aya", "射命丸文": "aya", "天狗": "aya",
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


def _cfg_float(value, default: float) -> float:
    """从配置里取一个浮点数。

    灵梦：配置是别人塞进赛钱箱的纸条，写错字很正常。看不懂就用默认值，
    决不能让一张糊掉的纸条把整本作业簿炸掉。
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _cfg_int(value, default: int) -> int:
    """从配置里取一个整数，写错就退回默认值（同 `_cfg_float`）。"""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _var_float(var, default: float) -> float:
    """从 Tk 数值变量取数：空框/乱填一律退回默认值。

    咲夜：Tk 的 DoubleVar 在空框时会直接抛 TclError，一点时间都不给。
    这里替它兜住，别让一次手滑把整轮设置保存都吞掉。
    """
    try:
        text = str(var.get()).strip()
    except Exception:
        return float(default)
    if not text:
        return float(default)
    try:
        return float(text)
    except (TypeError, ValueError):
        return float(default)


def _var_int(var, default: int) -> int:
    """从 Tk 数值变量取整数（同 `_var_float`）。"""
    return int(_var_float(var, float(default)))


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.HERE = HERE
        self.ASSETS = ASSETS
        self.assets_dir = ASSETS
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
        self._whats_new_win = None
        self._manual_whats_new = False
        self._pending_whats_new = False
        self._first_run_hide_main = False
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
        # 答案正文的「誊清」缓冲：流式走纯文本，落笔后再换成带公式图的版本
        self._ans_body = ""
        self._ans_body_start = "1.0"
        self._ans_photos: list = []
        self._ans_rendered_for = ""
        self.clip_watcher: clipboard.ClipboardWatcher | None = None
        self._update_checking = False
        self._launch_time = time.time()
        self._update_offered = ""
        self._update_download_win = None
        self._update_last_source = ""
        self._update_startup_scheduled = False
        self._suppress_update_this_run = False
        self._first_launch_run = False
        self._web_user_stop = True
        self._web_round_failed = False
        self._web_stale: dict[str, int] = {}
        self._web_last_fills: list[tuple] = []

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
        # 华文行楷缺“麗/郷/題”等字，Tk 会逐字回退成黑体，标题会一半行楷一半黑体。
        # 楷体字形完整，作为标题字体可以保证整行统一。
        self.F_TITLE = _pick_font(self.root, ["楷体", "华文行楷", "Microsoft YaHei UI"], "Microsoft YaHei UI")
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
        # 主窗口改成更宽的长方形；小屏仍按实际屏幕夹住，不许把状态栏顶出屏幕。
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        min_w, min_h = min(1180, sw - 40), min(720, sh - 80)
        min_w, min_h = max(760, min_w), max(540, min_h)
        r.minsize(min_w, min_h)

        # 上次关窗时的几何位置要接着用；但必须夹在本机屏幕里。
        # 旧 1380×880 / 1520×940 对现在的界面偏小：低于 1650×980 的保存
        # 尺寸自动迁移到新默认 1660×987；真正拉大过的尺寸继续保留。
        # （灵梦：上次你把我这扇窗户摆到哪了，我记着呢——但不会摆到屏幕外面去。）
        def_w, def_h = 1660, 987
        w = max(min_w, min(def_w, sw - 40))
        h = max(min_h, min(def_h, sh - 80))
        x, y = max(0, (sw - w) // 2), max(0, (sh - h) // 3)
        geom = str(self.cfg.get("geometry") or "").strip()
        if geom:
            m = re.match(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$", geom)
            if m:
                sw_w, sw_h = int(m.group(1)), int(m.group(2))
                # 旧默认/偏小尺寸迁移；真正的大窗口保留
                if sw_w >= 1650 and sw_h >= 980:
                    w = max(min_w, min(sw_w, sw - 40))
                    h = max(min_h, min(sw_h, sh - 80))
                x = max(0, min(int(m.group(3)), max(0, sw - w)))
                y = max(0, min(int(m.group(4)), max(0, sh - h - 40)))
        r.geometry(f"{w}x{h}+{x}+{y}")

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
        hdr.columnconfigure(1, weight=1)
        avatar_key = {"src": "marisa", "trans": "keine", "ans": "reimu"}.get(key)
        avatar = self._avatars.get(avatar_key) if avatar_key else None
        if avatar is not None:
            tk.Label(hdr, image=avatar, bg=C["panel"], bd=0).grid(
                row=0, column=0, padx=(10, 4), pady=4, sticky="w")
        # grid：标题占中间可伸缩列，右侧按钮固定成独立列。
        # 这样“慧音的翻译”的“译”不会被“誊抄”压住。
        tk.Label(hdr, text=title, bg=C["panel"], fg=C["gold"], anchor="w",
                 justify="left", font=(self.F_TITLE, 15)).grid(
            row=0, column=1, sticky="ew", padx=(6, 6), pady=(8, 6))
        tipmap = {"抹去": "清空这个面板的内容", "誊抄": "复制面板内容到剪贴板"}
        btns = tk.Frame(hdr, bg=C["panel"])
        btns.grid(row=0, column=2, sticky="e", padx=(0, 6), pady=(8, 6))
        for text, cmd in buttons:
            _b = tk.Button(btns, text=text, command=cmd, bg=C["panel"], fg=C["muted"],
                           activebackground=C["panel2"], activeforeground=C["text"],
                           relief="flat", bd=0, padx=8, pady=2, cursor="hand2",
                           font=(self.F_UI, 10))
            _b.pack(side="right", padx=(0, 6))
            if text in tipmap:
                Tooltip(_b, tipmap[text])
        if hint:
            tk.Label(hdr, text=hint, bg=C["panel"], fg=C["muted"],
                     font=(self.F_UI, 10)).grid(
                row=1, column=1, columnspan=2, sticky="w", pady=(0, 4))

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
        """博麗神社 · 香火钱账本：新窗口只读 usage，不碰自动答题。"""
        win = getattr(self, "_usage_win", None)
        try:
            if win is not None and win.winfo_exists():
                win.lift()
                win.focus_force()
                return
        except Exception:
            self._usage_win = None
        from modules import usage_window

        usage_window.UsageWindow(self, C)

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
        _boot_log("first-run setup window created")
        # 某些 VM/远程桌面里 Toplevel 创建后会被主窗口或激活窗口压到后面。
        # 创建完成后强制显示一次，确保用户一定看得到契约页。
        self.root.after(80, self._ensure_setup_visible)

    def _ensure_setup_visible(self) -> None:
        win = self._setup_win
        if win is None or not getattr(win, "winfo_exists", lambda: False)():
            return
        try:
            win.deiconify()
            win.lift()
            win.attributes("-topmost", True)
            win.focus_force()
        except Exception:
            pass
        try:
            _boot_log(
                f"first-run setup shown mapped={win.winfo_ismapped()} "
                f"state={win.state()} geom={win.geometry()}")
        except Exception:
            pass
        try:
            win.after(1200, lambda: win.attributes("-topmost", False))
        except Exception:
            pass

    def _on_setup_done(self, result: dict) -> None:
        self._setup_win = None
        if result.get("cancelled"):
            # 契约可以稍后再续，不能把整个主程序一起关掉。
            _boot_log("first-run setup cancelled: return to main")
            self._reveal_main_for_onboarding()
            try:
                # 首次安装才标记“稍后续”；从设置里取消重看契约不应把老用户打回首启。
                if getattr(self, "_first_run_hide_main", False) or first_run.is_resume(self.cfg):
                    self.cfg["onboarding_state"] = first_run.STATE_PENDING
                settings.save(self.cfg)
            except Exception:
                pass
            try:
                self._status("契约先留着，之后在「设置 → 结界契约」补；引路可在「神社登记」重看。", "warn")
                self.root.deiconify()
                self.root.lift()
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
        # 从“主界面隐藏”的首次安装路径回来：引导需要主界面作背景。
        self._reveal_main_for_onboarding()

        def _open_safe() -> None:
            try:
                self.open_onboarding(manual=False, start_step=1)
            except Exception as exc:
                import traceback
                _boot_log(f"onboarding UI failed: {exc!r}\n{traceback.format_exc()[-1200:]}")
                # 引导打不开也不能让主程序看起来“退出了”
                try:
                    self.root.deiconify()
                    self.root.lift()
                    self._status("新手引导启动失败，先进主界面；可在设置里重看。", "warn")
                except Exception:
                    pass

        # 契约全屏关闭后立刻接全屏引导；不要在中间把主界面亮出来。
        self.root.after(0, _open_safe)

    def _on_onboarding_done(self, skipped: bool = False) -> None:
        self._onboarding_win = None
        self._reveal_main_for_onboarding()
        if not self._manual_onboarding:
            try:
                first_run.mark_done(
                    self.cfg, settings.APP_VERSION,
                    bool(self.cfg.get("onboarding_api_skipped")),
                    tour_skipped=bool(skipped))
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
        # 首次安装/重装：引导结束后才展示本版更新说明。
        # 这里不直接在 on_done 回调里弹全屏，先让主界面稳定一拍。
        if getattr(self, "_pending_whats_new", False):
            self._pending_whats_new = False
            try:
                self.root.after(250, lambda: self.maybe_show_whats_new(True))
            except Exception:
                pass

    def maybe_show_whats_new(self, config_existed: bool) -> None:
        if self._setup_win is not None or self._onboarding_win is not None:
            return
        from modules import whats_new

        if not whats_new.should_show(self.cfg, config_existed):
            return
        self.open_whats_new(manual=False)

    def open_whats_new(self, manual: bool = False, start_step: int = 1) -> None:
        if self._whats_new_win is not None and getattr(
                self._whats_new_win, "winfo_exists", lambda: False)():
            try:
                self._whats_new_win.lift()
            except Exception:
                pass
            return
        from modules import whats_new

        self._manual_whats_new = bool(manual)
        self._whats_new_win = whats_new.WhatsNewWizard(
            self, self._on_whats_new_done, start_step=start_step, manual=manual)

    def _on_whats_new_done(self, skipped: bool = False, manual: bool = False) -> None:
        self._whats_new_win = None
        # 手动看过也算已读，避免用户刚从设置里看完、下次启动又自动弹一遍。
        try:
            from modules import whats_new

            whats_new.mark_seen(self.cfg)
            settings.save(self.cfg)
        except Exception:
            pass
        try:
            self._status(
                "更新说明看完了。设置 → 神社登记 → 更新说明，随时可以重看。"
                if not skipped else
                "更新说明先跳过；设置 → 神社登记 → 更新说明，随时可以重看。",
                "info")
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

    def _apply_install_anchor(self) -> None:
        """识别卸载后重装：保留 API/模型，但把首启/引导状态重置。"""
        try:
            if first_run.reinstall_detected(
                    self.cfg, settings.CONFIG_PATH, HERE):
                first_run.reset_for_reinstall(self.cfg)
                _boot_log(
                    f"reinstall detected install_anchor={first_run.install_anchor(HERE)!r} "
                    f"old={self.cfg.get('install_anchor')!r}")
            first_run.mark_install_anchor(self.cfg, HERE)
            settings.save(self.cfg)
        except Exception as exc:
            _boot_log(f"install anchor failed: {exc!r}")

    def _reveal_main_for_onboarding(self) -> None:
        if not self._first_run_hide_main:
            return
        self._first_run_hide_main = False
        try:
            self.root.deiconify()
            self.root.lift()
            _boot_log("first-run: main window revealed for onboarding")
        except Exception:
            pass

    def maybe_start_first_run(self, pre_access: str, config_existed: bool) -> None:
        self._onboarding_pre_access = pre_access
        self._onboarding_config_existed = config_existed
        if not first_run.should_show(self.cfg, pre_access, config_existed):
            _boot_log(
                f"first-run skipped state={self.cfg.get('onboarding_state')!r} "
                f"pre_access={pre_access!r} has_setup={first_run.has_setup(self.cfg)}")
            if (not str(self.cfg.get("onboarding_state") or "").strip()
                    and (config_existed or pre_access != "fresh")):
                try:
                    first_run.mark_legacy(self.cfg)
                    settings.save(self.cfg)
                except Exception:
                    pass
            return
        try:
            # 重装标记只消费一次；之后即使契约取消，也不会每次启动都重弹。
            self.cfg["onboarding_reinstall"] = False
            first_run.mark_pending(self.cfg)
            settings.save(self.cfg)
        except Exception:
            pass
        self._first_run_hide_main = True
        resume = int(self.cfg.get("onboarding_resume_step") or 1)
        self.root.after(350, lambda: self._start_first_run_resume(resume))

    def _start_first_run_resume(self, resume: int) -> None:
        try:
            if resume > first_run.SETUP_STEPS:
                self._reveal_main_for_onboarding()
                self.open_onboarding(manual=False,
                                     start_step=max(1, min(first_run.ONBOARD_STEPS,
                                                           resume - first_run.SETUP_STEPS)))
            else:
                # 契约页是首次安装最关键的窗口：主界面先藏起来，避免在 VM /
                # 远程桌面上把契约窗口压到后面，让用户以为“契约页没出来”。
                if self._first_run_hide_main:
                    try:
                        self.root.withdraw()
                        _boot_log("first-run setup: main window withdrawn")
                    except Exception:
                        pass
                self.start_setup_wizard(start_step=max(1, min(first_run.SETUP_STEPS, resume)))
        except Exception as exc:
            import traceback
            _boot_log(f"first-run UI failed: {exc!r}\n{traceback.format_exc()[-1200:]}")
            try:
                messagebox.showerror(APP_TITLE, f"首次安装引导启动失败：\n{exc}")
            except Exception:
                pass

    def _open_settings(self) -> None:
        """博麗神社 · 境界設定：只开新设置中心，不碰自动答题段。"""
        win = getattr(self, "_settings_win", None)
        try:
            if win is not None and win.winfo_exists():
                win.lift()
                win.focus_force()
                return
        except Exception:
            self._settings_win = None
        from modules import settings_center

        settings_center.SettingsCenter(self, C)

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
        self.temp_var = tk.DoubleVar(value=_cfg_float(c.get("temperature"), 0.2))
        self.extra_var = tk.StringVar(value=c.get("extra_json", ""))
        _m = c.get("capture_method") or ""
        if _m.startswith("后台") or _m == "window":
            _m = "后台抓取（可抓被遮挡窗口）"
        else:
            _m = "屏幕抓取（所见即所得）"
        self.method_var = tk.StringVar(value=_m)
        self.minimize_var = tk.BooleanVar(value=bool(c.get("minimize_on_capture", False)))
        self.interval_var = tk.DoubleVar(value=_cfg_float(c.get("auto_interval"), 1.5))
        self.settle_var = tk.DoubleVar(value=_cfg_float(c.get("auto_settle"), 0.8))
        self.threshold_var = tk.DoubleVar(value=_cfg_float(c.get("auto_threshold"), 1.5))
        self.vision_base_var = tk.StringVar(value=c.get("vision_base_url", "") or "")
        self.vision_key_var = tk.StringVar(value=c.get("vision_api_key", "") or "")
        self.web_port_var = tk.IntVar(value=_cfg_int(c.get("web_port"), 9222))
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
        self.toast_quiet_start_var = tk.IntVar(value=_cfg_int(c.get("toast_quiet_start"), 23))
        self.toast_quiet_end_var = tk.IntVar(value=_cfg_int(c.get("toast_quiet_end"), 8))

        reg = c.get("region")
        self.region = None
        if isinstance(reg, (list, tuple)) and len(reg) == 4:
            try:
                _r = tuple(int(float(v)) for v in reg)
                if _r[2] > 0 and _r[3] > 0:
                    self.region = _r  # type: ignore[assignment]
            except (TypeError, ValueError):
                # 配置里的框选区域坏了就当没框过（P2-19：不让坏配置拖垮启动）
                self.region = None
        self.target_title = str(c.get("window_title") or "")

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
            temperature=_var_float(self.temp_var, 0.2),
            extra_json=self.extra_var.get().strip(),
            capture_method=self.method_var.get(),
            region=list(self.region) if self.region else None,
            window_title=self.target_title,
            auto_enabled=bool(self.auto_var.get()),
            auto_interval=_var_float(self.interval_var, 1.5),
            auto_settle=_var_float(self.settle_var, 0.8),
            auto_threshold=_var_float(self.threshold_var, 1.5),
            minimize_on_capture=bool(self.minimize_var.get()),
            web_port=_var_int(self.web_port_var, 9222),
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
            toast_quiet_start=_var_int(self.toast_quiet_start_var, 23),
            toast_quiet_end=_var_int(self.toast_quiet_end_var, 8),
            toast_seen=dict(getattr(self, "_toast_seen", {}) or {}),
            theme=str(self.cfg.get("theme", theme.THEME_CLASSIC)),
            theme_unlocked=bool(self.cfg.get("theme_unlocked", False)),
            geometry=self.root.geometry(),
        )
        return cfg

    def _save_config(self) -> bool:
        try:
            self.cfg = self._snapshot_cfg()
            return bool(settings.save(self.cfg))
        except Exception:
            return False

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

    def _schedule_update_check(self, first_launch: bool = False) -> None:
        """每次启动只检查一次；首次安装/首启流程中完全不检查。"""
        self._first_launch_run = bool(first_launch)
        self._suppress_update_this_run = bool(first_launch)
        if first_launch:
            _boot_log("update: skipped on first launch")
            return
        if self._update_startup_scheduled:
            return
        self._update_startup_scheduled = True
        # 等主界面稳定、首启窗口判定完成后再打听一次。
        self.root.after(2500, self._update_check_startup)

    def _update_check_startup(self) -> None:
        if self._suppress_update_this_run or self._update_checking:
            return
        self._check_updates(manual=False)

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
                else:
                    self._status(f"文文：{tag} 的号外已经给你看过了，去下载吧。", "info")

                # 自动检查也要 Toast；手动检查保留强制提醒。
                if first_offer:
                    toast_body = f"文文：新号外印好了——{tag} 上架。要现在去下载吗？"
                else:
                    toast_body = f"文文：{tag} 的号外还压在文文那儿，去下载页看看吧。"
                self._notify("update", "博麗神社 · 号外", toast_body,
                             avatar="aya", force=bool(manual))
            else:
                self._status(f"文文：没有新号外，v{settings.APP_VERSION} 还是最新的。", "info")
                self._notify(
                    "update", "博麗神社 · 号外",
                    f"文文：今天的号外翻遍了，v{settings.APP_VERSION} 还是最新的一期。",
                    avatar="aya", force=bool(manual),
                )
        else:
            self._update_last_source = "没打听到"
            msg = err or "连接没有回应"
            self._status(f"文文：路被结界挡住了……（{msg[:80]}）", "warn")
            self._notify(
                "update", "博麗神社 · 号外",
                f"文文：路被结界挡住了……（{msg[:60]}）",
                avatar="aya", force=bool(manual),
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

        def open_release() -> None:
            url = info.get("url") or info.get("download") or ""
            if not url:
                self._status("文文：这期号外没留下载地址，去仓库的 Releases 页看看吧。", "warn")
                return
            win.destroy()
            self._open_url(url)

        def copy_link() -> None:
            url = info.get("url") or info.get("download") or ""
            if not url:
                self._status("文文：这期号外没留下载地址。", "warn")
                return
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(url)
                self.root.update_idletasks()
                self._status("文文：下载链接已经抄到剪贴板了。", "ok")
            except Exception:
                self._status("文文：剪贴板被结界卡住了，直接去号外页吧。", "warn")

        download_url = str(info.get("download") or "")
        asset_name = str(info.get("asset_name") or "")
        has_installer = bool(
            download_url
            and (asset_name.lower().endswith((".exe", ".msi"))
                 or download_url.lower().split("?", 1)[0].endswith((".exe", ".msi")))
        )
        def open_download() -> None:
            win.destroy()
            self._open_update_download(info)

        if has_installer:
            tk.Button(row, text="下载安装包", command=open_download,
                      bg=C["accent"], fg="white",
                      relief="flat", bd=0, padx=16, pady=5, cursor="hand2",
                      font=(self.F_UI, 10, "bold")).pack(side="left")
            tk.Button(row, text="前往发布页", command=open_release, bg=C["panel2"],
                      fg=C["text"], relief="flat", bd=0, padx=12, pady=5,
                      cursor="hand2", font=(self.F_UI, 10)).pack(side="left", padx=(8, 0))
        else:
            tk.Button(row, text="前往发布页", command=open_release, bg=C["accent"], fg="white",
                      relief="flat", bd=0, padx=16, pady=5, cursor="hand2",
                      font=(self.F_UI, 10, "bold")).pack(side="left")
        tk.Button(row, text="复制链接", command=copy_link, bg=C["panel2"],
                  fg=C["text"], relief="flat", bd=0, padx=12, pady=5,
                  cursor="hand2", font=(self.F_UI, 10)).pack(side="left", padx=(8, 0))
        tk.Button(row, text="稍后再说", command=win.destroy, bg=C["panel2"], fg=C["muted"],
                  relief="flat", bd=0, padx=14, pady=5, cursor="hand2",
                  font=(self.F_UI, 10)).pack(side="left", padx=(10, 0))

        self._update_hint_var = tk.StringVar(
            value=("下载后会自动校验 SHA256，再由更新助手安装；也可以直接去发布页。"
                   if has_installer else
                   "本期没有直接安装包地址，请前往发布页下载。"))
        tk.Label(win, textvariable=self._update_hint_var,
                 bg=C["bg"], fg=C["muted"], font=(self.F_UI, 9)).pack(pady=(0, 10))
        win.protocol("WM_DELETE_WINDOW", win.destroy)

    def _open_update_download(self, info: dict) -> None:
        """号外下载窗口：多线程、断点续传、SHA256，完成后交给更新助手。"""
        win = getattr(self, "_update_download_win", None)
        try:
            if win is not None and win.win.winfo_exists():
                win.win.lift()
                return
        except Exception:
            self._update_download_win = None
        from modules import update_ui

        avatar = os.path.join(ASSETS, "char", "toast", "avatar_aya.png")
        try:
            self._update_download_win = update_ui.start_download(
                self.root, info, C, self.F_UI, self.F_TITLE, avatar,
                self._install_downloaded_update)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"号外取件失败：\n{exc}")
            self._update_download_win = None

    def _install_downloaded_update(self, path: str) -> None:
        """下载并校验完成后，启动更新助手；安装器会等待本进程退出。"""
        try:
            if not os.path.isfile(path):
                raise FileNotFoundError(path)
            if not getattr(sys, "frozen", False):
                # 源码运行时没有安装目录，直接打开安装包，避免误装 Python 目录。
                os.startfile(path)
                self._status("文文：安装包已经打开，按向导完成安装即可。", "ok")
                return
            from modules import update_install

            app_dir = os.path.dirname(sys.executable)
            update_install.start_install(path, app_dir, sys.executable)
            self._status("文文：号外取到，准备张贴……", "ok")
            self.root.after(300, self._on_close)
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"更新助手启动失败：\n{exc}")

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
            # 首次契约/引导还在全屏时不要弹试用提醒，避免和仪式抢焦点。
            if (getattr(self, "_first_run_hide_main", False)
                    or getattr(self, "_setup_win", None) is not None
                    or getattr(self, "_onboarding_win", None) is not None):
                return
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
        # 框选模式下不拿窗口列表去覆盖选择，否则用户刚框好的区域会被显示成
        # 「整个屏幕」，看起来像框选丢了（P2-20）。
        if self.region:
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
        # P2-20：以前框选过一次之后，region 会永远压过窗口选择——
        # 你在这儿选「整个屏幕」，我却还盯着上次那块小方框，嘴上还说「整块屏幕归我管」。
        # 现在只要你主动改选窗口/整屏，就把那块框选收回去。
        # （紫：框住的缝隙，你说一声我就松开。）
        had_region = bool(self.region)
        self.region = None
        if label == "整个屏幕":
            self.target_title = ""
            self.target_hwnd = 0
            if had_region:
                self._status("灵梦：框选那块收回来了，现在整块屏幕都归我管。", "info")
            else:
                self._status("灵梦：好，整块屏幕都归我管。", "info")
            return
        for w in self.windows:
            if w.label() == label:
                self.target_title = w.title
                self.target_hwnd = w.hwnd
                if had_region:
                    self._status(f"灵梦：框选收回来，改盯这扇窗户——{w.title[:50]}", "ok")
                else:
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
            self._web_hint_qno = 0
            self._web_hint_part = ()
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
            # P2-1：这几个状态是「上一轮」的，必须跟着新一轮一起归零。
            # 以前 _web_ledger_failed 一旦为 True 就再也没人清过——上一轮某次
            # 磁盘写失败，会让之后每一轮都直接「停在原题等人工」，日志还骗人。
            # （魔理沙：一页没写成账，不等于这辈子都记不了账啊。）
            self._web_ledger_failed = False
            self._web_model_fails = 0
            self._web_empty_since = 0.0
            self._web_stale = {}
            self._web_last_fills = []
            self.web_done = ""
            if self.auto_var.get():
                self.auto_var.set(False)
                self._status("灵梦：全自动接管了，自动监听先关掉。", "info")
            self.web_on = True
            btn_txt = "⛩  退治中…"
            self.btn_web.configure(text=btn_txt)
            port = int(self.web_port_var.get() or 9222)
            if not self._web_port_open(port):
                self._status("紫：结界还没开——先点左边的「张开结界」（或者自己打开答题浏览器）。", "warn")
            else:
                self._status("紫：正在从境界的缝隙里连你的浏览器…", "info")
            # P2-3：每一轮要有自己的世代号，并且确认上一轮真的退出了。
            # 以前这里 web_stop.set() 之后马上 clear() 就起新线程，旧线程的
            # 撤销被一并取消 —— 两条循环会同时读/点同一个页面，还会互相关 UI。
            _gen = getattr(self, "_web_gen", 0) + 1
            self._web_gen = _gen
            _old = getattr(self, "web_thread", None)
            if _old is not None and _old.is_alive():
                self._web_status("紫：上一轮还在境界里收尾，先送它出来…", "info")
                self.web_stop.set()
                _old.join(timeout=6.0)
                if _old.is_alive():
                    self._web_status(
                        "紫：旧的那轮赖着不肯走，这轮先不开——免得两条线同时动一扇窗。",
                        "err")
                    self.web_on = False
                    self._web_user_stop = True
                    self.web_var.set(False)
                    self.btn_web.configure(text="⛩  开始退治")
                    return
            self.web_stop.clear()
            self.web_thread = threading.Thread(target=self._web_loop, args=(_gen,), daemon=True)
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
            # 正在收结界的时候别插手，否则勾选框会被轮询来回拨（P2-12 配套）。
            if getattr(self, "_barrier_closing", False):
                return
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

    def _close_answer_browser(self, port: int) -> str:
        """通过 CDP Browser.close 关闭专用答题浏览器。

        返回 `"ok"`（关掉了）/ `"foreign"`（这扇门不是我开的，不动手）/
        `"timeout"`（发了关闭请求但它没退）。
        """
        if not self._barrier_is_mine(port):
            return "foreign"
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
                try:
                    if os.path.exists(BARRIER_MARK):
                        os.remove(BARRIER_MARK)
                except OSError:
                    pass
                return "ok"
            time.sleep(0.2)
        return "timeout"

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
            _port = port

            # P2-12：关结界要问端口、发 CDP、再等它真的退——最多五六秒。
            # 以前这一整套都在 Tk 主线程上跑，整个界面跟着僵住；现在丢给工作
            # 线程，结果走队列回主线程再动界面。
            def _close_worker():
                try:
                    res = self._close_answer_browser(_port)
                except Exception as exc:
                    self.q.put(("status", f"魔理沙：关结界时出岔子——{exc}", "err"))
                    res = "timeout"
                self.q.put(("barrier_closed", res, _port))

            threading.Thread(target=_close_worker, daemon=True).start()

    def _on_barrier_closed(self, res: str, port: int) -> None:
        """结界关闭的收尾：在主线程里改界面。"""
        self._barrier_closing = False
        if res == "ok":
            # 不在这里改 _barrier_last：让 _watch_barrier 观察到
            # True→False 的变化，统一只推一条“结界已关闭”。
            was_open = bool(getattr(self, "_barrier_last", False))
            self.browser_var.set(False)
            self.btn_browser.configure(text="☂  张开结界")
            self._status("紫：结界已关闭，专用答题浏览器已退出。", "info")
            if not was_open:
                self._barrier_toast("紫：结界已关闭。")
        elif res == "foreign":
            self.browser_var.set(True)
            self.btn_browser.configure(text="☂  关闭结界")
            self._status(
                "紫：这扇结界门牌对不上——不是我张开的，我不擅自关。"
                "你要关就自己在浏览器那边关。", "warn")
            self._barrier_toast(
                "紫：那扇门不是我开的，留着不动。", avatar="yukari")
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

    def _barrier_is_mine(self, port: int) -> bool:
        """这扇结界是不是本程序亲手张开的（P2-22）。

        紫：境界里到处是门，光看「门是开的」可认不出是不是我开的。
        门牌对不上，我就不去关它——免得把别人正在用的窗户一起收进缝隙。
        """
        try:
            with open(BARRIER_MARK, "r", encoding="utf-8") as f:
                return str(f.read()).strip() == str(int(port))
        except (OSError, ValueError):
            return False

    def _launch_answer_browser(self) -> bool:
        """张开结界：调「启动答题浏览器.bat」，并记下这扇门是谁开的。

        P1-5：URL 以前是当命令行参数传给 cmd 的。`list2cmdline` 只给带空格的
        参数加引号，URL 里的 `&` 完全不受保护——bat 只会收到 `?a`，而 `b=2`
        还会被 cmd 当成一条命令去执行。现在改走环境变量，一个字都不用过转义。
        """
        bat = os.path.join(HERE, "启动答题浏览器.bat")
        if not os.path.exists(bat):
            return False
        try:
            url = (self.start_url_var.get() or "").strip() or "https://kysu.edu"
            port = int(self.web_port_var.get() or 9222)
            env = dict(os.environ)
            env["SCH_START_URL"] = url
            env["SCH_BARRIER_PORT"] = str(port)
            try:
                os.makedirs(os.path.dirname(BARRIER_MARK), exist_ok=True)
                with open(BARRIER_MARK, "w", encoding="utf-8") as f:
                    f.write(str(port))
            except OSError:
                pass
            subprocess.Popen(
                ["cmd", "/c", bat], cwd=HERE, env=env,
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

    def _web_loop(self, gen: int = 0) -> None:
        """全自动主循环：连不上就等，断了就重连，一直做到没有下一题。

        `gen` 是本轮的世代号。收工事件必须带着**本轮**的世代号回去，
        否则旧线程退出时会把用户刚开起来的新一轮从 UI 上关掉（P2-3）。
        """
        drv = None
        errs = 0
        try:
            while not self.web_stop.is_set():
                if gen and gen != getattr(self, "_web_gen", 0):
                    # 已经有更新的一轮接手了，这一轮悄悄退场
                    break
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
                    # 这一题的 key 是“提交前”就写进 _web_seen 的；一次 CDP/
                    # 网络抖动如果直接重试，会被当成“这题处理过了”而跳过。
                    # 异常路径主动丢掉当前 key，让下一轮重新读题、重新作答。
                    try:
                        self._web_seen.discard(str(getattr(self, "_web_current_key", "")))
                    except Exception:
                        pass
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
                _stopped = self.web_stop.is_set() and not getattr(self, "_web_all_done", False)
                if _stopped:
                    _body = "魔理沙：全自动被停止，当前这一轮没有正常收工。"
                elif _blocked:
                    _body = (f"魔理沙：这一轮跑完了。对 {_ok} 错 {_fail}；"
                             f"第 {','.join('Q'+str(n) for n in _blocked)} 题留给人工。")
                elif _fail or (getattr(self, "_web_round_failed", False)
                               and not getattr(self, "_web_all_done", False)):
                    _body = (f"魔理沙：啧，这一轮没退治干净……对 {_ok} 错 {_fail}，"
                             "你自己看着办。")
                else:
                    _body = f"魔理沙：这一轮退治完了。对 {_ok} 错 {_fail}，还行嘛。"
                if not _stopped:
                    self._notify("auto", "博麗神社 · 退治", _body,
                                 key=f"auto:{int(time.time())}", force=True, avatar="marisa")
            if not getattr(self, "_web_user_stop", True):
                if _stopped:
                    self._web_status(
                        "魔理沙：全自动被停止——不是正常收工，当前题还没有完成。",
                        "warn")
                elif _blocked:
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
            self.q.put(("web_off", gen if gen else getattr(self, "_web_gen", 0)))

    def _web_recover_blocked(self, drv) -> bool:
        """单题失败不要退出全自动：标记待人工，跳到下一道未完成题。"""
        if getattr(self, "_web_ledger_failed", False):
            self._web_status("魔理沙：跳过账本没写成，停在原题等人工，不再跳过。", "err")
            return False
        # 如果上一轮是被“停止”打断的，不要在这里把停止伪装成正常收工。
        if self.web_stop.is_set():
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
        # 单小问/最后一小问失败时：停在当前题，**不再自动跳到下一道 Question**。
        # 旧行为会把“求解失败/卡顿”直接记成待人工并跳题；用户重开全自动后
        # 又因为状态是 Incorrect/Partially correct 继续跳，整题就永远丢了。
        if not self._web_has_more_parts(st):
            if qno:
                try:
                    skip_ledger.record_once(
                        qno, st.get("part") or [], reason="自动流程未能完成，停在本题",
                        source="pearson")
                except Exception:
                    self._web_ledger_failed = True
            self._web_round_failed = True
            self._web_status(
                f"魔理沙：第 {qno} 题没完成，先停在本题等重试，不自动跳下一题。",
                "warn")
            return False
        # 当前题还有小问：只允许翻到下一小问，绝不把整个 Question 跳掉。
        # 本小问失败仍然入账，但后面的小问要继续做。
        if self._web_has_more_parts(st):
            _pv = st.get("part") or []
            _pn, _pm = int(_pv[0]), int(_pv[1])
            if qno:
                try:
                    skip_ledger.record_once(
                        qno, _pv, reason="当前小问未能完成，继续下一小问",
                        source="pearson")
                except Exception as exc:
                    self._web_ledger_failed = True
                    self._web_round_failed = True
                    self._web_status(
                        f"魔理沙：小问账本写入失败（{exc}），停在这里。", "err")
                    return False
            self._web_status(
                f"魔理沙：第 {qno} 题第 {_pn} 小问没完成，先翻到第 {_pn + 1} 小问，不跳题。",
                "warn")
            key = self._web_key(st)
            try:
                if self._web_next(drv, key):
                    return True
            except Exception:
                pass
            try:
                st2 = drv.state() or {}
                pv2 = st2.get("part") or []
                if len(pv2) == 2 and tuple(pv2) != tuple(_pv):
                    return True
            except Exception:
                pass
            self._web_status(
                "魔理沙：翻不到下一小问，先停在本题，不跳 Question。", "warn")
            return False
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
            # 入账成功就把「账本坏了」的旗子放下来（P2-1）：一次写盘失败不该
            # 让之后每一轮都被这条陈旧标志拦住。
            self._web_ledger_failed = False
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
        # 走到这里，当前题已经写进 skip ledger 了，所以「离开未完成题」点 Yes 是允许的。
        # 关键：**先把这个警告框关掉，再去点题号**。
        # 模态框挡在页面上时，点题号根本无效，goto_question 只会返回失败，
        # 整轮就冤死在这儿（灵梦：门被堵住了，你得先把门推开再走）。
        for _attempt in range(3):
            try:
                if drv.leave_prompt():
                    drv.click_leave("yes")
                    time.sleep(0.8)
            except Exception:
                pass
            try:
                ok = drv.goto_question(tn) == "ok"
            except Exception:
                ok = False
            if not ok:
                time.sleep(0.5)
                continue
            # 有的版本是「点题号 → 才弹框」；跳完再收一次尾。
            try:
                if drv.leave_prompt():
                    drv.click_leave("yes")
                    time.sleep(0.8)
            except Exception:
                pass
            time.sleep(0.9)
            try:
                if int((drv.state() or {}).get("qno") or 0) == tn:
                    return True
            except Exception:
                pass
        # 最后一道保险：题号跳不过去，就退用页面自己的「下一题」。
        # （魔理沙：正门进不去，翻墙也得把你送过去。）
        for _attempt in range(2):
            try:
                if drv.leave_prompt():
                    drv.click_leave("yes")
                    time.sleep(0.8)
                drv.click_text(r"^(next|next question|continue)$")
                time.sleep(1.2)
                if int((drv.state() or {}).get("qno") or 0) != qno:
                    return True
            except Exception:
                pass
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
        if self._web_has_more_parts(st):
            return False
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
        # 多小问未做完时，任何“跳下一道题”的入口都必须拒绝。
        if self._web_has_more_parts(st):
            self._web_status(
                "灵梦：当前题还有小问没做完，先把小问翻完，不跳到下一题。", "info")
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
            # partial 也是「已经判过分」的一种，不能再点 Check（P1-2）
            if kind in ("correct", "incorrect", "partial", "finished"):
                return False
            if kind == "leave":
                # 「确定离开本题吗」：点 No 留下，再重试 Check，绝不盲目提交/跳题。
                # 用 click_leave（按 leave_state 解析出的唯一按钮 id 点），
                # 别按文字乱点 —— dijit 的确认框里，文字和按钮根本不在同一个节点。
                try:
                    drv.click_leave("no")
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

    def _web_feedback(self, drv, timeout: float = 15.0, base_posted=None) -> str:
        """读判分结果，返回 correct / incorrect / partial / 空串。

        帕秋莉：`resultPosted` 是个累计的 revision，上一题的残留很容易冒充本题。
        以前只要它非 0 就直接采信——可能在真正的反馈弹出来之前，就把上一题的
        正误当成这一题：答对记成错、答错记成对，两种都是灾难。
        现在要么「反馈弹窗确实开着」，要么「resultPosted 相对点 Check 之前变了」。
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            fb = ""
            # **判分框优先**（《作业侠客》就是这样判的：只看可见的判分框）。
            # Dojo 内部的 resultPosted/kind 是**整题聚合值**——多小问里
            # 前一问 partial 会让后一问答对了也被判成 partial
            # （2026-11-28 Q14 实测：弹窗写「Fantastic!」，内部状态还是 partial）。
            try:
                fb = (drv.feedback() or "").strip()
            except Exception:
                fb = ""
            if fb:
                return fb
            try:
                # Dojo player 的内部判分优先；它比 DOM 弹窗更稳定
                ps = drv.player_state() if hasattr(drv, "player_state") else {}
                pk = self._web_player_kind(ps)
                if pk:
                    fresh = bool(ps.get("feedbackOpen"))
                    if not fresh and base_posted is not None:
                        posted = ps.get("resultPosted")
                        if posted is not None:
                            try:
                                fresh = int(posted or 0) != int(base_posted or 0)
                            except (TypeError, ValueError):
                                fresh = False
                    if fresh:
                        return pk
                cs = drv.completion_state() if hasattr(drv, "completion_state") else {}
                kind = str((cs or {}).get("kind") or "")
                if kind in ("correct", "partial", "incorrect"):
                    return kind
                if kind == "finished":
                    return "correct"
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
        n, m = 0, 0
        try:
            st = drv.state() or {}
            pv = st.get("part") or []
            n, m = (int(pv[0]), int(pv[1])) if len(pv) == 2 else (0, 0)
        except Exception:
            n, m = 0, 0
        # 还有小问没做完时，**只允许点「Continue / Continue to next part」** ——
        # 那是同一道题里往后翻一节，不会跳过小问。
        # 普通的「Next question」会直接跳题，必须拦住。
        # （灵梦：一节做完了该翻到下一节，但要翻到别的题，我得先问一声。）
        if 0 < n < m:
            try:
                r = drv.click_text(r"^continue( to next part)?$")
            except Exception:
                r = "error"
            if r != "ok":
                self._web_status(
                    f"灵梦：还有第 {n + 1} 小问（共 {m} 问），没找到「继续」就先不翻页。", "info")
                return False
            time.sleep(0.6)
            if self._web_wait_change(drv, old_key, timeout=10):
                return True
            self._web_status(f"灵梦：点了「继续」但页面没动，停在原题。", "warn")
            return False
        try:
            cs = drv.completion_state() if hasattr(drv, "completion_state") else {}
            if cs and cs.get("kind") not in ("", "none"):
                if not cs.get("hasNext"):
                    return False
                res = drv.click_completion("next") if hasattr(drv, "click_completion") else "no"
            else:
                # 「下一题」不一定叫 Next：答对之后 Pearson 常常只给一个
                # `Continue`（多小问里是「Continue to next part」）。
                res = drv.click_text(
                    r"^(next( question)?|continue( to next part)?|next part)$")
            if res != "ok":
                return False
            time.sleep(0.6)
            if drv.leave_prompt():
                try:
                    drv.click_leave("no")
                except Exception:
                    pass
                return False
        except Exception:
            return False
        return self._web_wait_change(drv, old_key)

    # ==================================================================
    # 以下整段学自《作业侠客》hwai.py 的 App：
    # `_fill_fields` / `_pending_fields` / `_report_fields` / `_ask_text`
    # / `_verify_fix` / `_advance` / 交卷前复核。
    # 我们原来的实现是「边踩坑边补特判」，不成体系；他这套是跑顺过的，照搬。
    # （帕秋莉：别人的笔记已经校对过了，就别再自己推一遍。）
    # ==================================================================
    def _fill_math_value(self, drv, fid: str, val: str) -> None:
        """填一个非矩阵值；无穷符号必须走调色板，不能键入 \\inf。

        Pearson 把键盘输入的 ``\\inf`` 渲染成字面文本 “infinity”，Check 不认；
        调色板的 ∞ 按钮才插入真正的符号（Q17 实测）。其他值仍走结构感知键入。
        """
        raw = str(val or "").strip()
        ed = latex.to_editor_input(raw)
        paste = latex.to_paste_input(raw)
        _inf_tokens = {"∞", "infinity", r"\infty", r"\inf"}
        if raw.lower() in _inf_tokens or ed.strip().lower() in _inf_tokens \
                or paste.strip().lower() in _inf_tokens:
            if drv.palette_infinity(fid) == "ok":
                return
        drv.insert_math(ed)

    def _fill_fields(self, drv, fields, vals) -> str:
        """把 vals 逐个填进 fields。成功返回 ""，失败返回一句人话。

        与旧 `_web_fill` 的区别（都是他的做法）：
        - 先 `focus_field` 再 `wait_js(/focusNode/)` 确认焦点真进去；
        - `clear_field()` 返回 False 就停，绝不硬打字（免得 Ctrl+A 选中整页）；
        - 只用 `insert_math(normalize_math(v))`，不粘贴、不比对值；
        - 填完等 aria-label 不再是占位符，而不是硬等固定秒数。
        """
        if len(vals) != len(fields):
            return f"页面有 {len(fields)} 个空，模型给了 {len(vals)} 个值，对不上"
        if any(not v for v in vals):
            missing = [str(i + 1) for i, v in enumerate(vals) if not v]
            return "第 " + "、".join(missing) + " 个空模型没给值"
        total = len(vals)
        for i, (fld, val) in enumerate(zip(fields, vals), 1):
            fid = fld["id"]
            self._web_status(f"灵梦：落笔第 {i}/{total} 格…", "info")
            drv.focus_field(fid)
            drv.wait_js("document.activeElement"
                        " && /focusNode/.test(String(document.activeElement.className || ''))", 2.0)
            if not drv.clear_field():
                return f"第 {i} 个空的输入框聚焦不上（不硬打字，免得把整页选起来）"
            if isinstance(val, tuple):
                rows, cols, mv = val
                if len(mv) < rows * cols:
                    return f"第 {i} 个空要 {rows * cols} 个矩阵元素，只有 {len(mv)} 个"
                err = drv.fill_matrix(fid, rows, cols, mv)
                if err:
                    return f"填第 {i} 个空失败：{err}"
            else:
                self._fill_math_value(drv, fid, str(val))
                drv.wait_js("((document.getElementById(%s) || {}).getAttribute && "
                            "(document.getElementById(%s).getAttribute('aria-label') || '')"
                            ".indexOf('enter your response') < 0) === true"
                            % (json.dumps(fid), json.dumps(fid)), 3.0)
        return ""

    @staticmethod
    def _pending_fields(st: dict) -> list:
        """这页还需要填的空：跳过已填的，以及「没选中的那个选项」里的空。

        **不按名字里的 Decoy 过滤**：Pearson 把「选中的那个选项里的空」也起名
        `Decoy1`，按名字过滤会把本该填的空跳过，Check answer 一直是灰的。
        """
        any_checked = any(r.get("checked") for r in (st.get("radios") or []))
        out = []
        for f in st.get("fields") or []:
            if f.get("filled"):
                continue
            if any_checked and f.get("in_opt") == "unchecked":
                continue
            out.append(f)
        return out

    @staticmethod
    def _report_fields(st: dict) -> list:
        """复核时要看的空：只算「选中的那个选项里」的和题干里的。"""
        any_checked = any(r.get("checked") for r in (st.get("radios") or []))
        return [f for f in st.get("fields") or []
                if not (any_checked and f.get("in_opt") == "unchecked")]

    @staticmethod
    def _ask_text(st: dict) -> str:
        """给式神的题目文本：**当前这一节放最前面**。

        整页文本只留 4000 字，长题（Part 8/9）会把当前这节的指令截掉，
        模型看到的全是前面几个小问，于是直接把前面的答案抄过来。
        """
        text = st.get("text") or ""
        cur = (st.get("cur") or "").strip()
        if cur and cur not in text:
            return ("【当前这一节】\n" + cur +
                    "\n\n【整页其余内容（可能含前面已做过的小问，别照抄它们的答案）】\n" + text)
        return text

    def _verify_fix(self, drv, why: str) -> bool:
        """复核说「应该是 X」时，如果 X 正好是某个选项，就直接改过来。

        只处理「选项选错」这一种，文本框暂不动（改字容易越改越乱）。
        """
        tail = why.split("应该是", 1)[-1] if "应该是" in why else why
        tail = tail.lower()
        try:
            radios = drv.state()["radios"]
        except Exception:
            return False
        for r in radios:
            lab = (r.get("label") or "").strip()
            if not lab or r.get("checked") or r.get("disabled"):
                continue
            if lab.lower() in tail:
                if drv.pick_choice("X", [dict(r, letter="X")]) == "ok":
                    self._web_status(f"魔理沙：复核说选错了，已改成「{lab}」，再交一次", "warn")
                    return True
        return False

    def _verify_before_submit(self, drv, st: dict, ctx: dict) -> str:
        """交卷前让式神复核已填的答案（他的 `verify_filled`）。

        返回 "ok" / "fixed" / "stop:<说明>" / "skip"（没东西可复核）。
        """
        try:
            from modules import prompts as _p
        except Exception:
            return "skip"
        checked = [r for r in (st.get("radios") or []) if r.get("checked")]
        fields = self._report_fields(st)
        fills = [f for f in (st.get("fills") or st.get("dropdowns") or [])
                 if (f.get("value") or "").strip()]
        if not fields and not fills and not checked:
            return "skip"
        lines = []
        for i, f in enumerate(fields, 1):
            lab = (f.get("label") or "").strip()
            if not lab:
                continue
            hint = (f.get("hint") or "").replace("\n", " ").strip()[:120]
            lines.append("第%d空：%s%s" % (i, lab[:120],
                                          ("　（所在句子：%s）" % hint) if hint else ""))
        for i, f in enumerate(fills, 1):
            lines.append("下拉%d：%s" % (i, (f.get("value") or "").strip()[:60]))
        if checked:
            lines.append("已选选项：%s" % ((checked[0].get("label") or "").strip()[:300]))
        if not lines:
            return "skip"
        body = (_p.VERIFY_PROMPT + "\n\n题目：\n" + self._ask_text(st)[:4000]
                + "\n\n当前已填：\n" + "\n".join(lines))
        ctx = ctx or getattr(self, "_web_ctx", None) or {}
        base = str((ctx or {}).get("base") or "")
        key = str((ctx or {}).get("key") or "")
        model = str((ctx or {}).get("model") or "")
        if not (key and model):
            return "skip"
        try:
            raw = self._ask_cancellable(base, key, model,
                                        [{"role": "user", "content": body}],
                                        ctx, timeout=90.0)
        except Exception:
            return "skip"
        verdict, why = _p.parse_verify(raw)
        if verdict == "ok":
            self._web_status("玉：复核通过，交卷。", "ok")
            return "ok"
        if verdict == "wrong":
            if self._verify_fix(drv, why):
                return "fixed"
            # 复核只改了选项；文字填空改不了。把复核结论当成下一轮的提示，
            # 让模型重算并重填，而不是整题停在原地等人工。
            try:
                _st = drv.state() or {}
                _qno = int(_st.get("qno") or 0)
                _part = tuple(_st.get("part") or [])
            except Exception:
                _qno, _part = 0, ()
            _vkey = ("verify", _qno, _part)
            _vtry = self._web_try.get(_vkey, 0) + 1
            self._web_try[_vkey] = _vtry
            if _vtry > 2:
                self._web_status(
                    f"玉：复核连续 {_vtry} 次认为不对，先停，交给你看。", "warn")
                return "stop:" + why
            self._web_hint = ("交卷前复核认为当前填写不对：" + str(why)[:200]
                              + "。请按这个结论重新计算，并只输出 CHOICE/MATRIX/"
                                "DROPDOWN/VALUE 四行。")
            self._web_hint_qno = _qno
            self._web_hint_part = _part
            self._web_status("玉：复核发现填得不对，带着复核结论重算一次…", "warn")
            return "fixed"
        self._web_status("玉：复核没拿到结论（式神没按格式回），先停，你自己看一眼再交", "warn")
        return "stop:复核没有结论"

    def _advance(self, drv, qn, before: str) -> bool:
        """把页面推到下一题。只用页面自己的「下一题」按钮，**绝不点 Save / 左边题号 / 改 URL**。

        四条路线（他的顺序）：判分框的 Next question → 播放器 btnNext
        → 不会跳走的 inline next → 交还给人、只等页面变化。
        """
        # 路线一：判分框里的「Next question」——真 Pearson 新界面只有这条能走
        if drv.click_feedback_next():
            self._web_status("灵梦：点判分框里的「Next question」…", "info")
            if drv.wait_advanced(qn, before, 25.0):
                return True
            self._web_status("魔理沙：点过了但页面没动；先停，不重复点（怕重复提交）", "warn")
            return False
        # 路线二：播放器标题栏自己的 btnNext
        for _ in range(2):
            got = drv.click_next_btn()
            if got == "disabled":
                break
            if got == "ok":
                self._web_status("灵梦：点播放器的「下一题」…", "info")
                if drv.wait_advanced(qn, before, 15.0):
                    return True
            time.sleep(1.0)
        # 路线三：播放器里不会跳走的 ›
        if drv.click_inline_next():
            self._web_status("灵梦：点「下一题」…", "info")
            if drv.wait_advanced(qn, before, 12.0):
                return True
        # 路线四：交回给用户，只等页面变化（最坏也是停在原题，不会把作业页弄丢）
        self._web_status(f"灵梦：第 {qn} 题做完了。你自己点一下「Next question」，我接着做", "info")
        return drv.wait_advanced(qn, before, 30.0)

    @staticmethod
    def _web_has_more_parts(st: dict) -> bool:
        """当前 Question 是否还有后面的小问（part 1/N, 2/N ...）。"""
        try:
            pv = (st or {}).get("part") or []
            if len(pv) == 2:
                n, m = int(pv[0]), int(pv[1])
                return 0 < n < m
        except Exception:
            pass
        return False

    @staticmethod
    def _web_active_checks(st: dict) -> list[dict]:
        """当前小问真正可勾的复选框；上一小问留下的 disabled 框不算。

        Pearson 多小问会把 Part 1 的选项保留在 DOM 里并 disabled。旧逻辑
        直接 `bool(st.get("checks"))`，于是 Part 2 明明只剩填空，却被判成
        “还要选选项”，模型不给 CHOICE 就被跳过（Q10 Part 2 实测）。
        """
        return [c for c in (st.get("checks") or [])
                if isinstance(c, dict) and not c.get("disabled")]

    def _web_targets(self, st: dict, part_n: int) -> list[dict]:
        """当前小问可填的框：未作答（placeholder）优先，其次按小问号。

        多小问题里每个 part 会动态增加输入框，所以不能假设“第 N 问=第 N 个框”。
        """
        boxes = list(st.get("fields") or []) + list(st.get("inputs") or [])
        usable = [b for b in boxes
                  if not b.get("readonly") and not b.get("disabled")]
        # 只跳过「已经判过分、锁住了」的空：判过分的 Part 会留在页面上，再往里头
        # 写会把已经对的答案搅乱。
        # **但「填着内容、却还能编辑」的框必须留下** —— 那多半是上一轮填错的答案，
        # 我们要先清掉再写新的。（灵梦：写错的字得擦掉重写，不能当没看见。）
        # 2026-11-28 Q12 实锤：错答案留在框里，旧逻辑把它当「已填」跳过，
        # 结果既不改也不清，直接跳到下一题。
        usable = [b for b in usable
                  if not (b.get("filled") and b.get("disabled"))]
        # 没选中的那个选项里的空：填了不计分，还会把做过的题再填一遍。
        # 判断依据是 in_opt（往上数六层、正好只有一个 radio 的容器），
        # **不是** id 里有没有 Decoy —— Pearson 把「选中的那个选项」里的空
        # 也起名叫 Decoy1，按名字过滤会把该填的空跳过。
        if any(r.get("checked") for r in (st.get("radios") or [])):
            usable = [b for b in usable if b.get("in_opt") != "unchecked"]
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
        self._web_hint = ""
        self._web_hint_qno = 0
        self._web_hint_part = ()
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
                f"魔理沙：第 {qno} 题先记入待人工账本；未完成前不跳下一个 Question。{_extra}",
                "warn")
        else:
            self._web_status(
                f"魔理沙：这道题先记入待人工账本，停在本题等重试。{_extra}", "warn")
        return False

    def _web_stale_retry(self, drv, key: str) -> bool:
        """「丢掉这轮答案重新读题」的限流器（P0-3）。

        返回 True = 回主循环再读一遍本页；返回 False = 该交还主循环了。

        以前这条路没有上限：一旦 `field_present` 因为拿不到主世界而恒为 False，
        每一轮都会「读题 → 算三遍 → 丢掉 → 再读题」，静默烧 token 到天荒地老。
        （魔理沙：三次都瞄不准，就先记下来，别在这儿把魔力耗干。）
        """
        _stale = getattr(self, "_web_stale", None)
        if not isinstance(_stale, dict):
            _stale = {}
        try:
            _stale[key] = int(_stale.get(key, 0)) + 1
        except Exception:
            _stale[key] = 1
        self._web_stale = _stale
        n = _stale[key]
        if n >= 3:
            _stale.pop(key, None)
            self._web_status(
                "魔理沙：这题的控件老是变，重算三次都没能落下笔，"
                "记成待人工、跳到下一题。", "warn")
            self._web_skip(drv, key)
            return False
        self._web_status(
            f"灵梦：控件在填写前又变了，丢掉这轮答案重新读题…（第 {n} 次）", "warn")
        self._web_seen.discard(key)
        return True

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

    @staticmethod
    def _deparen(text: str) -> str:
        """把只包着一个简单项的括号拆掉：`(1)/(2)` → `1/2`。

        帕秋莉：括号只是排版。`(1)/(2)` 和 `1/2` 指的是同一个数，
        编辑器回读时喜欢加括号，不能因此判人家填错。
        """
        prev = None
        out = text or ""
        while prev != out:
            prev = out
            out = re.sub(r"\(([0-9A-Za-z.]+)\)", r"\1", out)
        return out

    @staticmethod
    def _fill_matches(expected: str, got: str) -> bool:
        """回读值是否就是期望答案。

        帕秋莉：同一个答案有好几种写法——`\\frac{1}{2}`、`1/2`、`(1)/(2)`；
        而 `2` 出现在 `-2`、`2.5`、`3/2`、`√3`、`x+1` 里面，都不算填对了。
        判定顺序：先比等价写法 → 再比数值 → 最后才做「独立 token」匹配。

        （旧版只做 `exp in got`，把填错的 12 当成 2；上一版补了边界，但边界里
        不含 `- . / ^ √ +`，于是 `-2`、`2.5`、`√3` 又被当成了 `2`。）
        """
        if not expected or not got:
            return False
        # 回读常常是 Pearson 的「朗读式」文本（`6500 equals 5000 left parenthesis …`），
        # 先翻回数学写法再比，否则填对了也会被判「没填进去」。
        try:
            expected = latex.aria_to_plain(expected)
            got = latex.aria_to_plain(got)
        except Exception:
            pass
        a = latex.normalize_answer(expected)
        b = latex.normalize_answer(got)
        if not a or not b:
            return False

        # 1) 期望答案的几种等价写法（原样 / 粘贴形态 / 按键形态 / 去括号）
        forms = [a]
        for conv in (latex.to_paste_input, latex.to_editor_input):
            try:
                form = latex.normalize_answer(conv(expected))
            except Exception:
                form = ""
            if form and form not in forms:
                forms.append(form)
        for form in list(forms):
            plain = App._deparen(form)
            if plain and plain not in forms:
                forms.append(plain)
        b_plain = App._deparen(b)
        if b in forms or b_plain in forms:
            return True

        # 2) 数值等价：3 与 3.0、1/2 与 0.5
        try:
            na = verify_math.parse_number_exact(a)
            nb = verify_math.parse_number_exact(b_plain)
            # 带逗号的可能是有序对 (5,25)，也可能是千分位，宁可不当数字比
            if (na is not None and nb is not None
                    and "," not in a and "," not in b_plain and na == nb):
                return True
        except Exception:
            pass

        # 3) 独立 token：前后不能紧贴数字/字母/小数点/斜杠/幂/根号/正负号
        edge = r"[0-9A-Za-z._/^√+π∞\-]"
        try:
            return bool(re.search(
                r"(?<!" + edge + r")" + re.escape(a) + r"(?!" + edge + r")", b))
        except re.error:
            return False

    def _web_field_empty(self, drv, fid: str) -> bool:
        """这个框是不是还空着（占位符还在）。

        帕秋莉：判断「有没有落笔」只需要看那行占位提示还在不在，
        不需要读出内容 —— 朗读式文本各版本写法不一，靠不住。
        """
        try:
            return bool(re.search(r"enter your response|nothing|^\s*$",
                                  str(drv.field_text(fid) or ""), re.I))
        except Exception:
            return True

    def _web_fill(self, drv, fid: str, text: str) -> bool:
        """填一个框，并确认真的填进去了。

        2026-11-28 重写。老版本有两条硬伤：
        1. 回读用 `field_text`，而它把「两份渲染 + aria-label」拼在一起，
           `2` 读成 `"222"` —— 任何填空都会被判「没填进去」，
           然后 3 次粘贴 + 4 次 insert 来回刷，一题耗 20 多秒再跳过。
        2. 重试轮次太多、每次轮询 2.5 秒，遇上不匹配就是干等。

        现在的策略：粘贴为主（粘贴会触发编辑器的输入事件，Pearson 才认账），
        每轮最多等 ~1.6 秒；两轮粘贴 + 一轮按键兜底。
        最后如果「框里确实有东西」但值对不上，也放行交给 Check 判 ——
        总比把整题扔掉强（灵梦：写歪了可以改，交白卷没得救）。
        """
        want = latex.to_paste_input(text)
        typed = latex.to_editor_input(text)
        # 含分式 / 指数 / 根号的答案一律「按键逐字打」。
        # 整段粘贴（等价于整段 insertText）会被编辑器把 `/` 的分母一路吃到后面，
        # 实测 `5(x+3/2)^2` 会变成「分母里塞了 )²」的坏结构，判分直接不认。
        _structural = bool(re.search(r"[/^_\\]", typed))

        def _readback() -> str:
            """等回读**稳定**再取值。

            2026-11-28 实测：打完字立刻读，会读到「只渲染了一半」的标签
            （`right parenthesis Superscript …` 这种），于是被当成填错。
            所以要求连续两次读到同一个非空值才算数。
            """
            last = None
            same = 0
            for _ in range(16):
                time.sleep(0.2)
                try:
                    txt = drv.field_text(fid)
                except Exception:
                    txt = ""
                if txt and txt == last:
                    same += 1
                    if same >= 1 and not self._web_field_empty(drv, fid):
                        return txt
                else:
                    same = 0
                last = txt
            return last or ""

        def _type_in() -> None:
            # 清空后必须等够，否则 `clear_field` 的收尾会把刚打的字一起带走
            # （实测 0.25s 会丢内容，0.4/0.7s 才稳）。
            drv.focus_field(fid)
            time.sleep(0.45)
            drv.clear_field()
            time.sleep(0.7)
            drv.insert_math(typed)
            time.sleep(0.45)

        def _paste_in() -> None:
            drv.focus_field(fid)
            time.sleep(0.45)
            drv.clear_field()
            time.sleep(0.7)
            drv.paste_math(want)
            time.sleep(0.45)

        def _balanced(s: str) -> bool:
            """括号是否配平（用来识别「只打了一半」的输入）。"""
            try:
                p = latex.aria_to_plain(s)
            except Exception:
                p = s or ""
            d_ = 0
            for ch in p:
                if ch == "(":
                    d_ += 1
                elif ch == ")":
                    d_ -= 1
                    if d_ < 0:
                        return False
            return d_ == 0

        # 结构型（含分式/指数/根号）只走按键，**绝不退回粘贴** ——
        # 粘贴会把 `5(x+3/2)^2` 解析成「分母里塞了 )²」的坏结构，
        # 而且回读是英文朗读文本，越比对越乱。所以：按键一次，
        # 只要框里真的落了字就交给 Check 判。
        if _structural:
            # 打两轮：第一轮若只落了一半（括号不配平），再清一次重打。
            for _try in range(2):
                try:
                    _type_in()
                except Exception:
                    pass
                txt = _readback()
                if not self._web_field_empty(drv, fid) and _balanced(txt):
                    return True
                self._web_status(
                    f"魔理沙：公式只落了一半（第 {_try + 1} 次），清掉重打。", "warn")
            # 还不行才退粘贴兜底（至少让框里有内容，交给 Check 判）
            try:
                _paste_in()
            except Exception:
                pass
            if not self._web_field_empty(drv, fid):
                self._web_status(
                    "魔理沙：按键两轮都没打完整，改用粘贴兜底；请留意判分反馈。", "warn")
                return True
            return False

        # 普通数值 / 简单表达式：先粘贴（快且稳），不成再按键
        for _fn in (_paste_in, _type_in):
            try:
                _fn()
            except Exception:
                continue
            txt = _readback()
            if self._fill_matches(text, txt):
                return True

        # 兜底：Input.insertText（只写内容、不一定触发事件，慎用）
        try:
            drv.focus_field(fid)
            time.sleep(0.2)
            drv.clear_field()
            time.sleep(0.2)
            drv.insert(want)
            time.sleep(0.6)
        except Exception:
            pass
        txt = _readback()
        if self._fill_matches(text, txt):
            return True

        # 内容在、但对不上：放行。让 Check answer 来判，
        # 判错还能带提示重算一次；总比整题跳过（等于 0 分）好。
        if not self._web_field_empty(drv, fid):
            self._web_status(
                f"魔理沙：这格填的是「{str(txt)[:20]}」，和期望的「{str(text)[:20]}」不完全一样，"
                "先交给 Check 判。", "warn")
            return True
        return False


    def _ask_cancellable(self, base: str, api_key: str, model: str, msgs: list,
                         ctx: dict, timeout: float = 120.0,
                         temperature: float = 0.2) -> str:
        """可被「收工」立即打断的模型调用：流式收集，cancel 用 web_stop。"""
        buf: list[str] = []

        def on_delta(chunk: str) -> None:
            buf.append(chunk)

        # 全自动协议只要 CHOICE/MATRIX/DROPDOWN/VALUE/FIELD 几行；有的模型
        # 会突然输出上万 token（实测单次 64 秒），把整轮拖死。
        # 给网页求解设一个上限；用户在“附加咒文”里写了 max_tokens 就以用户为准。
        extra = dict(ctx.get("extra") or {})
        extra.setdefault("max_tokens", 2200)

        res = llm.chat_stream(
            base, api_key, model, msgs,
            reasoning_effort=ctx.get("effort"),
            temperature=temperature,
            extra_body=extra or None,
            timeout=timeout,
            on_delta=on_delta,
            cancel=self.web_stop,
        )
        return (res.text or "".join(buf) or "").strip()

    @staticmethod
    def _web_part_text(text: str, n: int) -> str:
        """取出第 n 小问那一段正文。

        慧音：Pearson 的小问标题长这样——「Part 2 of 3: 求导」。
        光切到 Part 2 会剩下一个「of 3:」的尾巴，模型读起来像半句话，
        所以这里把它一并抹掉。
        """
        if n <= 0:
            return text or ""
        raw = text or ""
        try:
            m = re.search(rf"Part\s+{n}\b(.*?)(?=Part\s+{n + 1}\b|\Z)", raw, re.S | re.I)
            seg = m.group(1) if m else raw
        except Exception:
            seg = raw
        return re.sub(r"^\s*of\s+\d+\s*[:：]\s*", "", seg, count=1)

    @staticmethod
    def _web_focus_text(text: str, n: int) -> str:
        """多小问同页时，只把「共享题干 + 当前小问」交给模型。

        P0-5：以前这里的判据是 `len(_pieces) >= 3`，可是
        `re.split(..., maxsplit=2)` 在只有一处「Part 1」的文本上只切出 2 段——
        条件永远不成立，stem 永远是空串。于是从第 2 小问起，模型只看到孤零零
        一句小问，看不到共享的题干，等于闭着眼睛答题。
        （紫：境界被切成两半的时候，你别拿量三半的尺子去量。）
        """
        if n <= 0:
            return text or ""
        raw = text or ""
        seg = App._web_part_text(raw, n).strip()
        stem = ""
        try:
            # 「Part 1」之前的部分才是真正的小问共享题干
            pieces = re.split(r"Part\s+\d+\b", raw, maxsplit=1, flags=re.I)
            if pieces:
                stem = pieces[0].strip()
        except Exception:
            stem = ""
        if not seg or seg == raw.strip():
            return raw
        seg = App._web_clip(seg, 2000)
        stem = App._web_clip(stem, 1200)
        return ("当前是第 " + str(n) + " 小问，只回答这一小问。\n"
                + ("【共享题干】\n" + stem + "\n\n" if stem else "")
                + "【本小问】\n" + seg)

    @staticmethod
    def _web_clip(s: str, limit: int) -> str:
        """截断长文本：保住开头和结尾，中间省略。

        帕秋莉：一本书太长的时候，前后封面都得留着——只读前半本，
        你永远不知道结论在第几页。
        """
        s = s or ""
        if len(s) <= limit:
            return s
        head = max(200, limit - 500)
        return s[:head] + "\n……\n" + s[-500:]

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
        # 重试提示只属于“同一道题”。一旦页面已经换题，旧提示必须丢掉，
        # 否则下一题会被当成重试、题号不自增，还会把上一题的答案提示带过去。
        try:
            _st_qno = int(st.get("qno") or 0)
            _st_part = tuple(st.get("part") or [])
        except Exception:
            _st_qno, _st_part = 0, ()
        if self._web_hint and (
                getattr(self, "_web_hint_qno", 0) != _st_qno
                or tuple(getattr(self, "_web_hint_part", ())) != _st_part):
            self._web_hint = ""
            self._web_hint_qno = 0
            self._web_hint_part = ()
        # 整份作业每一题都已判过分（含 part 0.4 的 Partially correct）：不再动页面，
        # 避免重启后把已经提交的答案又重填一遍，甚至把部分题改坏。
        try:
            _qs0 = [q for q in (st.get("questions") or []) if int(q.get("n") or 0) > 0]
            _kinds0 = [self._web_status_kind(q.get("status")) for q in _qs0]
            # 多小问的题，左侧状态可能已经是 Correct/Partially correct，
            # 但当前只做到 Part 2/7；这时不能把整份作业判成“做完了”。
            if (_qs0 and not self._web_has_more_parts(st)
                    and all(k in ("correct", "incorrect", "partial") for k in _kinds0)):
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
        # 交作业 / 结束页：这一页摆着「Submit / Done」这种封印。
        # 灵梦：那不是我能碰的按钮 —— 交不交卷是人的事。看见就停，让它自己决定。
        try:
            if st.get("hasDanger") and not st.get("hasCheck"):
                self._web_status(
                    "灵梦：这页有「Submit / Done」按钮，看着像交作业的页面，"
                    "我不点，你自己确认后再继续。", "warn")
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
        # 一算出 key 就记下来：后面任何一步抛异常，_web_loop 才能把
        # 这个 key 从 _web_seen 里丢掉，避免一次抖动被当成“处理过了”跳过。
        self._web_current_key = key
        # 当前页还有没有「待填 / 待选」的控件。
        # 灵梦：题号旁边打个勾，只说明**已经交过的那几小问**判完了，
        # 不代表这一问也做完了 —— 多小问常把状态挂在整题上。
        try:
            _pending_now = bool(
                [f for f in (st.get("fields") or [])
                 if not f.get("filled") and not f.get("disabled")]
                or [r for r in (st.get("radios") or [])
                    if not r.get("checked") and not r.get("disabled")]
                or [c for c in (st.get("checks") or [])
                    if not c.get("checked") and not c.get("disabled")]
                or [d for d in (st.get("dropdowns") or []) if not d.get("locked")])
        except Exception:
            _pending_now = False
        # 多小问硬约束：当前 Part 做完后，只能翻到下一小问，绝不跳 Question。
        # 旧逻辑会在 Part 1 判对后调用 _web_jump_next_unanswered，直接跳到
        # 下一道题；Q10 Part 1/2、Q23 Part 1/7 都踩过这个坑。
        try:
            # 只有“当前 Part 已经判过分”才允许翻下一小问；
            # 填了值但还没 Check（例如交卷前复核失败、正在带提示重算）时，
            # 绝不能翻页/跳题，否则会把这小问的答案丢掉（Q8 Part 1 实测）。
            _q_pre = next((x for x in (st.get("questions") or [])
                           if int(x.get("n") or 0) == int(st.get("qno") or 0)), None)
            _part_judged = bool(
                _q_pre and self._web_done_status(_q_pre.get("status")))
            if (self._web_has_more_parts(st) and not _pending_now
                    and not getattr(self, "_web_hint", "")
                    and _part_judged):
                _fb_now = ""
                try:
                    _fb_now = (drv.feedback() or "").strip()
                except Exception:
                    _fb_now = ""
                if not _fb_now:
                    _pv = st.get("part") or []
                    _pn, _pm = int(_pv[0]), int(_pv[1])
                    self._web_status(
                        f"灵梦：还有第 {_pn + 1} 小问（共 {_pm} 问），先翻到下一小问，不跳题。",
                        "info")
                    if self._web_next(drv, key):
                        return True
                    _st_after = drv.state() or {}
                    _pv_after = _st_after.get("part") or []
                    if len(_pv_after) == 2 and tuple(_pv_after) != tuple(_pv):
                        return True
                    self._web_status(
                        "灵梦：当前题还有小问没翻过去，停在这里等你处理，不跳到下一题。",
                        "warn")
                    self._web_round_failed = True
                    return False
        except Exception:
            pass
        # 当前题已经答对：不要死等 Next，直接找下一道没答完的题。
        # **但前提是本页真的没有待做的控件** —— 否则就会出现「最后小问被跳过」：
        # 整题状态显示已判分，而 Part 3 的空还空着，我们就跳走了。
        try:
            _qno = int(st.get("qno") or 0)
            _q = next((x for x in (st.get("questions") or [])
                       if int(x.get("n") or 0) == _qno), None)
            _fb_open = ""
            try:
                _fb_open = (drv.feedback() or "").strip()
            except Exception:
                _fb_open = ""
            # _web_hint 非空 = 当前题刚被判错、正在带提示重算；
            # 这时绝不能因为左侧题号暂时显示“已完成”就跳到下一题。
            if (_q and not _fb_open and not _pending_now
                    and not getattr(self, "_web_hint", "")
                    and self._web_status_kind(_q.get("status")) == "correct"):
                if self._web_jump_next_unanswered(drv, st):
                    return True
                self._web_status(
                    f"灵梦：第 {_qno} 题已答过，后面也没有未完成的题了。", "ok")
                return False
            if (_q and not _fb_open and not _pending_now
                    and not getattr(self, "_web_hint", "")
                    and not self._web_done_status(_q.get("status"))):
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
        has_choices = bool(st.get("radios")) or bool(self._web_active_checks(st))
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

        # 刚翻页时正文还是「Please wait...」，这时读到的题干是残的，模型会答不出来。
        # 等它加载完再读一次（学自《作业侠客》2026-11-25 的实测）。
        try:
            for _ in range(10):
                if "please wait" not in str(st.get("text") or "").lower():
                    break
                time.sleep(0.6)
                _st2 = drv.state()
                if _st2:
                    st = _st2
        except Exception:
            pass

        _is_retry = bool(self._web_hint)
        self._web_seen.add(key)
        if not _is_retry:
            self._web_question += 1
            # 换到新的一题就把答案面板清掉。不清的话面板里会一直挂着上一题的
            # 内容（用户会以为这题已经答过了），而且誊清公式时会越积越长。
            # （灵梦：换一张符卡，纸当然要换一张。）
            self.q.put(("clear", "ans"))
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

        # P2-9：交给式神的题干必须是「公式 + 咒文提示 + 下拉框选项」都在的那一份。
        # 以前 focus_text 是从 st["text"] 取的，而下拉框选项只拼进了上面这个
        # 局部 text —— 式神只知道「按顺序写编号」，却不知道编号是什么，纯靠猜。
        # 把「当前这一节」顶到最前面。整页正文只留 4000 字，长题里当前小节的
        # 指令常被截掉，式神于是把前面小问的答案照抄过来。
        # （慧音：问第 (d) 问，就先把第 (d) 问的题面递过去。）
        _cur = str(st.get("cur") or "").strip()
        rich_text = text
        focus_text = self._web_focus_text(rich_text, part_n)
        # 「当前这一节」单独贴在最前面，别混进共享题干里（否则会被切成两半）
        if _cur and _cur not in focus_text:
            focus_text = "【当前这一节】\n" + _cur + "\n\n" + focus_text
        # 图题的多小问共享同一张图/图注；只给“当前小问”会丢掉图形描述，
        # 模型就只能回 CHOICE: -> / VALUE: ->（Q4 Part 2 实测）。
        if part_n > 1:
            focus_text = (
                "【整题上下文（含前面小问的已知条件；前面小问的答案只作参考、"
                "绝对不要照抄；只回答【当前小问】）】\n"
                + rich_text + "\n\n【当前小问】\n" + focus_text)
        # 小问提示只加在面板显示上；focus_text 自己会带一份，别重复。
        if part_n:
            seg = self._web_part_text(rich_text, part_n).strip()[:300]
            text = (f"当前是第 {part_n} 小问（共 {part_m} 问），只回答这一小问。\n"
                    + (seg + "\n\n" if seg else "") + rich_text)
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
        # P2-10：题面顺序和回填顺序必须是同一个顺序。
        # 以前 packet 用的是页面顺序，真正回填时 `_web_targets` 又把占位框
        # 提前、把第 N 个框提到最前 —— 多空题的「值1; 值2」就可能填到相反的框里。
        # 现在先用同一个排序生成 packet，回填时不再二次重排。
        _ordered = self._web_targets(st, part_n)
        _st_packet = st
        if _ordered:
            _st_packet = dict(st)
            _st_packet["fields"] = list(_ordered)
            _st_packet["inputs"] = []
            _st_packet["labels"] = [str(b.get("label") or "") for b in _ordered]
        packet = question_reader.build_packet(_st_packet, focus_text)
        self._web_model_fails = getattr(self, "_web_model_fails", 0)
        spec = {}
        try:
            def _ask_engine(msgs, temperature=0.7, tag="sample"):
                if tag == "fallback":
                    # 并发流式采样偶尔会被网关截断（同一题连续 3+1 路都断）。
                    # 最后兜底改走**单次非流式**请求，避开 SSE 截断问题。
                    time.sleep(0.8)
                    res = llm.chat_once(
                        ctx["base"], ctx["key"], ctx["model"], msgs,
                        reasoning_effort=None, temperature=0.2,
                        extra_body={"max_tokens": 2200}, timeout=90.0)
                    return (res.text or "").strip()
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
                has_choices = bool(st.get("radios")) or bool(self._web_active_checks(st))
                drops = st.get("dropdowns") or []
                try:
                    _lp = st.get("part") or [0, 0]
                    _lpn = int(_lp[0]) if len(_lp) == 2 and _lp[1] else 0
                except Exception:
                    _lpn = 0
                _ordered2 = self._web_targets(st, _lpn)
                _st2 = st
                if _ordered2:
                    _st2 = dict(st)
                    _st2["fields"] = list(_ordered2)
                    _st2["inputs"] = []
                    _st2["labels"] = [str(b.get("label") or "") for b in _ordered2]
                packet2 = question_reader.build_packet(
                    _st2, self._web_focus_text(_live.get("text") or text, _lpn))
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
                time.sleep(0.5)
                return self._web_stale_retry(drv, key)
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
        if st.get("radios") or self._web_active_checks(st):
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
                    has_choices = bool(st.get("radios")) or bool(self._web_active_checks(st))
                    drops = st.get("dropdowns") or []
            except Exception:
                pass

        # P0：填任何控件前再核对一次快照。Pearson 在选项加载/小问切换时
        # 经常替换 DOM；如果控件 UID/签名已经变了，旧答案必须丢弃重读。
        if not self._web_snapshot_intact(drv, st):
            time.sleep(0.4)
            return self._web_stale_retry(drv, key)

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
            # P1-1：以前用一个 picked 计数器，重试时把「已经选好的框」又数了
            # 一遍 —— picked 虚高，`picked < need` 就被骗过去，结果带着空下拉框
            # 去交卷。现在按框号记集合，已经选好的不重复计入。
            # （咲夜：同一个盘子擦两遍，不会变成擦过两个盘子。）
            ok_idx: set[int] = set()
            need = min(len(active), len(spec["drops"]))

            def _drop_index(_i: int):
                try:
                    return int(spec["drops"][_i]) - 1
                except Exception:
                    return None

            def _pick_drop(_i: int, _dd: dict, idx: int) -> None:
                for _try in range(3):
                    try:
                        drv.dropdown_open(_dd["id"])
                        time.sleep(0.4)
                        r = drv.dropdown_pick(idx)
                        time.sleep(0.4)
                        drv.dropdown_close()
                        if r == "ok":
                            ok_idx.add(_i)
                            return
                    except Exception:
                        try:
                            drv.dropdown_close()
                        except Exception:
                            pass
                    time.sleep(0.4)

            for _i, _dd in enumerate(active):
                if _i >= len(spec["drops"]):
                    continue
                idx = _drop_index(_i)
                if idx is None:
                    continue
                _pick_drop(_i, _dd, idx)

            if need and len(ok_idx) < need:
                self._web_status(
                    f"魔理沙：下拉框只选上 {len(ok_idx)}/{need}，再等一会儿重试…", "warn")
                time.sleep(1.5)
                # 只补没选上的框
                for _i, _dd in enumerate(active):
                    if _i in ok_idx or _i >= len(spec["drops"]):
                        continue
                    idx = _drop_index(_i)
                    if idx is None:
                        continue
                    _pick_drop(_i, _dd, idx)
                if len(ok_idx) < need:
                    self._web_status(
                        f"魔理沙：下拉框 {len(ok_idx)}/{need} 还是没选上，停在原题重试。",
                        "warn")
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
            # 顺序必须和上面生成 packet 时一致，这里不再二次重排（P2-10）。
            # （慧音：题目问第几空，就答第几空——顺序一乱，全篇都错。）
            targets = self._web_targets(st, part_n)
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
                if len(targets) < len(vals):
                    self._web_status("魔理沙：空框不够，跳过这题", "warn")
                    return self._web_skip(drv, key)
                # 用他的 `_fill_fields`：焦点确认 → clear_field 布尔 → insert_math
                # → 等 aria-label 不再是占位符。不再粘贴、不再做值比对。
                _err = self._fill_fields(drv, targets[:len(vals)], vals)
                if _err:
                    self._web_status("魔理沙：" + _err + "，先跳过", "warn")
                    return self._web_skip(drv, key)
                self._web_last_fills = [(key, b["id"], v)
                                        for b, v in zip(targets[:len(vals)], vals)]
                self.q.put(("append", "ans", "已填入： " + " ; ".join(vals) + "\n", "dim"))

            else:
                if not targets:
                    self._web_status("魔理沙：找不到输入框，跳过", "warn")
                    return self._web_skip(drv, key)
                fid = targets[0]["id"]
                _err = self._fill_fields(drv, [targets[0]], [spec["value"]])
                if _err:
                    self._web_status("魔理沙：" + _err + "，先跳过这题", "warn")
                    return self._web_skip(drv, key)
                self._web_last_fills = [(key, fid, spec["value"])]
                self.q.put(("append", "ans", "已填入：" + str(drv.field_label(fid))[:60] + "\n", "dim"))

        # ---- 图形题：用 Pearson 的 GraphControl API 画函数
        if has_graph:
            try:
                _pn, _pm = (st.get("part") or [0, 0])[:2]
                _seg = self._web_part_text(st.get("text") or "", int(_pn or 0)).lower()
            except Exception:
                _seg = (st.get("text") or "").lower()
            _draw_text = any(k in _seg for k in (
                "graph the parabola", "graph both", "graph the functions",
                "graph the equation", "use the graphing tool", "graph f",
                "graph y"))
            # 「要你自己画」必须是**真的有作图控件**，而且要**没有待选选项**。
            # 灵梦：题目说「先在纸上画，再选正确的那张图」——那就只是选择题。
            # 页面上那四张坐标图是选项缩略图，把它们当作图区去画，
            # 只会把一道好端端的选择题判成「公式没解析出来」然后整轮收工。
            # 判据用 state 里的 draw_graph（大方块/带工具条/有放大入口），
            # 不用题干关键词 —— 关键词分不清「画图区」和「选项里的图」。
            _need_graph = (bool(st.get("draw_graph"))
                           and not (st.get("radios") or [])
                           and _draw_text)
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
                        if str(_res) == "no-dijit":
                            # P2-4：图形控件要靠 Dojo 的 registry 才够得着。
                            # 有些 Pearson 页面根本不挂全局 dijit，式神够不到。
                            self._web_status(
                                "帕秋莉：这页的图形结界没有挂出 Dojo 的登记册"
                                "（no-dijit），式神够不到，先停在原题。", "warn")
                        else:
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

        # P2-6：Pearson 的 Check 常常是异步冒出来的。刚填完那一瞬间按钮还没渲染，
        # 以前就直接判「没有下一题」整轮收工——到嘴的符卡就这么飞了。
        # （灵梦：手都伸到赛钱箱边上了，你让我再等一下下会怎样？）
        _filled = bool(spec.get("values") or spec.get("value") or spec.get("matrix")
                       or spec.get("choices") or spec.get("drops"))
        if _filled and not st_now.get("hasCheck") and not st_now.get("hasNext"):
            for _w in range(12):
                time.sleep(0.5)
                try:
                    _stc = drv.state() or {}
                except Exception:
                    _stc = {}
                if _stc.get("hasCheck") or _stc.get("hasNext"):
                    st_now = _stc
                    break

        # Check 灰着就说明还有空没填 / 选项没选；这时点它毫无反应，
        # 只会白等一轮判分超时。（帕秋莉：门锁着就别敲了，先看看缺哪把钥匙。）
        try:
            if st_now.get("hasCheck") and st_now.get("hasCheckOn") is False:
                # 框里内容明明是对的、Check 却还灰着 —— 说明编辑器把这次输入
                # 显示出来了，但没记进 Pearson 的状态里（`insertText` 不触发
                # 它的事件就是这样）。实测：清空 + 重新「粘贴」一次就解禁了。
                # （帕秋莉：字写在纸上了，可登记簿没记；得再登记一遍。）
                _refilled = False
                for _k, _fid, _val in (getattr(self, "_web_last_fills", []) or []):
                    if _k != key:
                        continue        # 别的题填的格，别往这题上粘
                    try:
                        drv.focus_field(_fid)
                        time.sleep(0.2)
                        drv.clear_field()
                        time.sleep(0.2)
                        drv.paste_math(latex.to_paste_input(_val))
                        time.sleep(0.4)
                        _refilled = True
                    except Exception:
                        pass
                if _refilled:
                    self._web_status(
                        "灵梦：Check 还是灰的，把刚填的格重新粘一遍，让它真的记上…", "info")
                    time.sleep(0.6)
                    try:
                        st_now = drv.state() or st_now
                    except Exception:
                        pass
                if st_now.get("hasCheckOn") is False:
                    self._web_status(
                        "灵梦：Check 按钮还是灰的（这页还有空没填、或选项没选），"
                        "停在原题等一下。", "warn")
                    self._web_round_failed = True
                    self._web_seen.discard(key)
                    return False
        except Exception:
            pass

        if st_now.get("hasCheck"):
            if st_now.get("canCheck") is False:
                self._web_status(
                    "灵梦：Check 还是灰的，说明还有空没填全；停在原题重来。", "warn")
                self._web_round_failed = True
                self._web_seen.discard(key)
                return False
            # 交卷前让式神复核一遍（学自《作业侠客》的 verify_filled）：
            # 填完就交最容易交错；先自己重算一遍、再和已填的比对，通过了才点。
            # （玉：交卷之前，先自己阅一遍卷。）
            _vf = "skip"
            try:
                _vf = self._verify_before_submit(drv, st_now, getattr(self, "_web_ctx", {}))
            except Exception:
                _vf = "skip"
            if _vf == "fixed":
                # 复核指出选项选错了、已经改正 —— 回上一轮重新提交
                self._web_seen.discard(key)
                return True
            if str(_vf).startswith("stop:"):
                self._web_round_failed = True
                self._web_seen.discard(key)
                return False
            self._web_status("灵梦：点 Check answer…", "info")
            # P2-5：记下点 Check 之前的 resultPosted，用来分辨「本题的判分」
            # 和「上一题残留的 revision」——以前就是被陈旧值骗了一次。
            _base_posted = None
            try:
                _ps0 = drv.player_state() if hasattr(drv, "player_state") else {}
                _base_posted = _ps0.get("resultPosted")
            except Exception:
                _base_posted = None
            if not self._web_click_check(drv):
                # 再给 Pearson 一次渲染时间，避免刚换题时误判
                time.sleep(1.2)
                if not self._web_click_check(drv):
                    self._web_status("灵梦：Check 按钮一直没出现，停在原题等一下。", "warn")
                    self._web_round_failed = True
                    return False
            fb = self._web_feedback(drv, base_posted=_base_posted)
            if not fb:
                # 有时第一次点击被页面吞掉；按钮还在就再点一次
                try:
                    if (drv.state() or {}).get("hasCheck"):
                        self._web_status("灵梦：没等到判分，再点一次 Check answer…", "warn")
                        try:
                            drv.click_text_native(r"^(check answer|final check)$")
                        except Exception:
                            self._web_click_check(drv)
                        fb = self._web_feedback(drv, timeout=10.0,
                                                base_posted=_base_posted)
                except Exception:
                    pass
            if fb == "correct":
                self._web_ok += 1
                self._web_round_failed = False
                self._web_hint = ""
                self._web_hint_qno = 0
                self._web_hint_part = ()
                self._web_status(
                    f"灵梦：第 {self._web_question} 题答对了。（对 {self._web_ok} / 错 {self._web_fail}）", "ok")
                if st_now.get("inDialog"):
                    self._web_status("魔理沙：练习题答对了（弹窗里不点 Next，避免翻掉真题）", "ok")
                    return False
                if drv.dialog_next():
                    if self._web_next(drv, key):
                        return True
                # 多小问：答对之后 Pearson 常常直接换出一个 `Continue`
                # （下一问的题面已经在下面了）。先点它，别干等 15 秒。
                if self._web_next(drv, key):
                    return True
                # 弹窗还挂着就点掉；下一小问出现就继续，否则翻下一题
                self._web_dismiss(drv)
                time.sleep(0.6)
                if self._web_wait_change(drv, key, timeout=12):
                    return True
                if self._web_jump_next_unanswered(drv):
                    return True
                self._web_status(
                    f"灵梦：没有下一题了，全自动收工（对 {self._web_ok} / 错 {self._web_fail}）。", "ok")
                return False

            # P1-2：partial（部分正确）以前会被 `good` 里的 correct 命中、
            # 当成全对记上去。现在和「判错」走同一条重算路径，文案分开说。
            if fb in ("incorrect", "partial"):
                _is_partial = fb == "partial"
                self._web_fail += 1
                self._web_round_failed = True
                fb_text = drv.feedback_text()
                wrong = ("多选 " + ",".join(spec["choices"])) if spec.get("choices") else \
                    str(spec.get("values") or spec.get("value") or "")
                self._web_prev.setdefault(key, set()).add(_sig)
                # 重试次数按“题号 + 小问”记，不能按 _web_key：
                # 填过答案后 field label 会变，key 必变，tries 会永远从 1 开始。
                _try_key = (int(st_now.get("qno") or 0),
                            tuple(st_now.get("part") or []))
                tries = self._web_try.get(_try_key, 0) + 1
                self._web_try[_try_key] = tries
                _mark = "△ 部分正确" if _is_partial else "× 判错"
                self.q.put(("append", "ans", f"{_mark}（第 {tries} 次）：{fb_text[:60]}\n", "err"))
                drv.click_text(r"^\s*ok\s*$")
                time.sleep(0.8)
                if tries <= 2 and not st_now.get("inDialog"):
                    self._web_hint = (f"上一次填的答案是 【{wrong}】，被判错了。"
                                      f"题目给的提示是：【{fb_text[:120]}】。"
                                      "请换个思路重新计算，务必给出正确结果。")
                    self._web_hint_qno = int(st_now.get("qno") or 0)
                    self._web_hint_part = tuple(st_now.get("part") or [])
                    self._web_seen.discard(key)
                    if _is_partial:
                        self._web_status(
                            f"魔理沙：只拿了个部分正确，带着提示再算一次（第 {tries} 次重试）…",
                            "warn")
                    else:
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
    def _pump_error(self, ev: tuple, exc: Exception) -> None:
        """单个事件处理失败：记一笔账，别让它带走整台消息泵。

        灵梦：一张符卡糊了，就换下一张——总不能让整台泵跟着停摆吧。
        """
        try:
            kind = ev[0] if ev else "?"
        except Exception:
            kind = "?"
        _boot_log(f"pump event={kind!r} failed: {exc!r}")

    def _pump(self) -> None:
        """消息泵：把工作线程丢进队列的事件一张张收下来。

        P1-9：以前 `self.root.after(45, ...)` 写在函数末尾、不在 finally 里，
        任何一个事件抛异常（比如某个窗口已经销毁）都会让重排被跳过——
        从此状态栏、busy、通知、剪贴板全部不再处理，界面看着还活着其实已经死了。
        现在：单个事件失败只记账，重排放进 finally，泵不会停。
        """
        try:
            for _ in range(500):
                try:
                    ev = self.q.get_nowait()
                except queue.Empty:
                    break
                try:
                    self._handle(ev)
                except Exception as exc:
                    self._pump_error(ev, exc)
            try:
                self._maybe_apply_pending_theme()
            except Exception:
                pass
        finally:
            try:
                self.root.after(45, self._pump)
            except tk.TclError:
                pass

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
        elif kind == "barrier_closed":
            self._on_barrier_closed(ev[1], ev[2] if len(ev) > 2 else 0)
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
        # 答案正文单独攒一份：等这一轮说完，再整段换成「带公式图」的版本。
        # （紫：边写边排版容易把半句公式切坏，等落笔了再誊清。）
        if panel == "ans" and tag == "body":
            if not self._ans_body:
                self._ans_body_start = txt.index("end-1c")
            self._ans_body += text
        txt.insert("end", text, tag)
        txt.see("end")
        if panel != "src":
            txt.configure(state="disabled")
        self._refresh_scrollbar(panel)

    @staticmethod
    def _needs_math_img(text: str) -> bool:
        """只有含分式 / 根号 / 矩阵的答案才值得重排成图。

        帕秋莉：`\\frac{1}{2}` 写成 `1/2` 也读得懂；但 `(1 2)(3 4)` 这种
        矩阵字面写法，得排成真正的矩阵才对得上题面。
        """
        return bool(re.search(r"\\frac|\\dfrac|\\tfrac|\\sqrt|\\begin\{", text or ""))

    def _beautify_ans(self) -> None:
        """把答案里已经写完的分式/根号/矩阵换成真正的排版图。

        流式阶段仍然吐纯文本（半句公式排不了）；等这一轮落笔，再整段誊清。
        任何一步失败都只是「保持纯文本」，绝不能让答案消失。

        注意要拿**模型原文**（`self.last_answer`），不是面板里已经转换过的文本：
        面板里的 `\\frac{1}{2}` 早就被转成 `1/2` 了，再排也排不出分式。
        """
        raw = (self.last_answer or "").strip()
        if not raw or raw == self._ans_rendered_for:
            # 追问会再走一次 busy=False，同一条答案不要重复誊清（会把追问内容冲掉）
            return
        if not self._needs_math_img(raw):
            return
        txt = self.panels.get("ans")
        if txt is None or not self._ans_body_start:
            return
        try:
            from modules import mathimg as _mi

            shown, images = _mi.render(raw, font_px=15, ink=C["text"],
                                       bg=txt.cget("bg"), font_path=None)
        except Exception as exc:
            _boot_log(f"mathimg render failed: {exc!r}")
            return
        if not images:
            return
        self._ans_rendered_for = raw
        try:
            txt.configure(state="normal")
            txt.delete(self._ans_body_start, "end")
            photos = []
            for chunk, idx in _mi.split_placeholders(shown):
                if idx is None:
                    if not chunk:
                        continue
                    # 文本段还要过一遍显示转换：`(x-2)^{2}` → `(x-2)²`、`\le` → `≤`。
                    # （只把分式/根号/矩阵抠成图，剩下的字照旧要读得懂。）
                    try:
                        chunk = latex.latex_to_text(chunk)
                    except Exception:
                        pass
                    txt.insert("end", chunk, "body")
                    continue
                try:
                    photo = ImageTk.PhotoImage(images[idx])
                except Exception:
                    continue
                photos.append(photo)
                txt.image_create("end", image=photo, padx=2, pady=2)
            txt.see("end")
            txt.configure(state="disabled")
            # 必须留着引用，否则 Tk 会把图片回收成一片空白
            self._ans_photos = photos
            self._refresh_scrollbar("ans")
        except Exception as exc:
            _boot_log(f"mathimg insert failed: {exc!r}")

    def _clear_panel(self, panel: str) -> None:
        txt = self.panels.get(panel)
        if txt is None:
            return
        if panel == "ans":
            self._ans_body = ""
            self._ans_body_start = "1.0"
            self._ans_photos = []
            self._ans_rendered_for = ""
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
        if not busy:
            # 这一轮落笔了：把答案里的分式/根号/矩阵换成排版图
            try:
                self._beautify_ans()
            except Exception as exc:
                _boot_log(f"beautify failed: {exc!r}")

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


def _license_badge(name: str, size: int):
    """加载授权状态徽章；name 为 license_ok / license_no。"""
    path = os.path.join(ASSETS, "license", f"{name}.png")
    im = Image.open(path).convert("RGBA")
    return ImageTk.PhotoImage(im.resize((size, size), Image.LANCZOS))


def show_activation(root: tk.Tk, reason: str = "", allow_trial: bool = False) -> bool:
    """博麗神社的结界许可窗口（一机一码激活）。返回 True 表示已获得许可。"""
    from modules import clipboard
    from modules import license as lic

    F = "Microsoft YaHei UI"
    win = tk.Toplevel(root)
    win.title("博麗神社 · 结界许可")
    win.configure(bg=C["bg"])
    win.resizable(False, False)
    w, h = 860, 760
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    win.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")
    win.attributes("-topmost", True)
    win.after(400, lambda: win.attributes("-topmost", False))
    result = {"ok": False}
    machine = lic.machine_code()

    try:
        _lic_ok = bool(lic.status()[0])
        logo = _license_badge("license_ok" if _lic_ok else "license_no", 150)
        win._license_logo_ref = logo
    except Exception:
        logo = None
    head = tk.Frame(win, bg=C["bg"])
    head.pack(fill="x", padx=30, pady=(14, 0))
    if logo is not None:
        tk.Label(head, image=logo, bg=C["bg"], bd=0).pack(side="left", padx=(0, 14))
    head_txt = tk.Frame(head, bg=C["bg"])
    head_txt.pack(side="left", fill="x", expand=True)
    tk.Label(head_txt, text="博麗神社 · 结界许可", bg=C["bg"], fg=C["gold"],
             font=(F, 24, "bold"), anchor="w").pack(fill="x")
    tk.Label(head_txt, text="～ 无许可者，不得入内 ～", bg=C["bg"], fg=C["muted"],
             font=(F, 11), anchor="w").pack(fill="x", pady=(2, 0))
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
    tk.Label(win, text="紫：三天的试用要是用完了，就得来神社登记咯。",
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

        try:
            lic.start_trial()
            state, msg, _days = lic.check_access(update=False)
            if state not in ("trial", "licensed"):
                raise RuntimeError(msg or "试用记录没有生效")
        except Exception as e:
            _boot_log(f"trial start failed: {e!r}")
            try:
                tip.configure(text=f"灵梦：试用结界没张开——{e}", fg=C["err"])
            except Exception:
                pass
            return
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
        tk.Button(btns, text="先试用 3 天进入", command=start_trial, bg=C["panel2"],
                  fg=C["gold"], activebackground=C["accent_dark"], activeforeground="#ffffff",
                  relief="flat", bd=0, padx=18, pady=7, cursor="hand2",
                  font=(F, 10, "bold")).pack(side="right", padx=(0, 10))
    else:
        def stay_without_trial() -> None:
            # 没有可用试用时，不能把“先回人间”做成静默退出：
            # 用户会以为它能进主界面。这里只解释原因，窗口继续留着。
            try:
                messagebox.showinfo(
                    "结界许可",
                    "这台机器目前没有可用试用，需要许可咒文才能进入主界面。\n"
                    "可以粘贴激活码后再点「解开结界」。",
                    parent=win,
                )
            except Exception:
                pass

        tk.Button(btns, text="先回人间", command=stay_without_trial,
                  bg=C["panel2"], fg=C["text"],
                  relief="flat", bd=0, padx=18, pady=7, cursor="hand2",
                  font=(F, 10)).pack(side="right", padx=(0, 10))
    tk.Label(btns, text=f"符卡作业簿 v{settings.APP_VERSION} · MIT License",
             bg=C["bg"], fg=C["muted"], font=(F, 9)).pack(side="left")

    def leave_or_trial() -> None:
        if allow_trial:
            start_trial()
        else:
            win.destroy()

    entry.bind("<Return>", lambda _e: activate())
    entry.focus_set()
    win.protocol("WM_DELETE_WINDOW", leave_or_trial)
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


def _code_stamp() -> str:
    """在 boot.log 里记一笔「这次跑的是哪一版代码」。

    灵梦：改完代码忘了重启，是这行字最想解决的问题——
    以前只能靠猜，现在一眼就能看出跑的是不是刚改的那一份。
    """
    try:
        _f = os.path.join(HERE, "app.pyw")
        _m = time.strftime("%m-%d %H:%M:%S", time.localtime(os.path.getmtime(_f)))
        _mods = []
        for _n in ("web", "latex", "mathimg"):
            _p = os.path.join(HERE, "modules", _n + ".py")
            if os.path.exists(_p):
                _mods.append(_n + "@" + time.strftime(
                    "%H:%M:%S", time.localtime(os.path.getmtime(_p))))
        return f"code app.pyw@{_m} " + " ".join(_mods)
    except Exception:
        return "code ?"


def main() -> None:
    _ensure_assets()
    from modules import single_instance

    if not single_instance.begin():
        if not single_instance.focus_existing():
            try:
                messagebox.showinfo(APP_TITLE, "符卡作业簿已经在运行，但暂时没找到它的窗口。\n"
                                               "灵梦：门已经开着，别从窗户爬进来。")
            except Exception:
                pass
        return
    capture.make_dpi_aware()
    capture.set_app_user_model_id("Shinichi.SpellCardHomework")
    _boot_log(f"boot {_code_stamp()}")

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
                root, "灵梦：第一次来？可以先用三天，或者拿一张许可咒文来。",
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
        try:
            single_instance.record_window(root)
        except Exception:
            pass

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

        # 关键：卸载重装时 %APPDATA%\SpellCardHomework\config.json 可能还在。
        # 用安装目录创建时间识别“目录被重建”，重置首启状态，但保留 API/模型。
        app._apply_install_anchor()

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
        _show_first = False
        try:
            _show_first = first_run.should_show(app.cfg, pre_access, config_existed)
            _boot_log(
                f"first_run show={_show_first} pre_access={pre_access} "
                f"config_existed={config_existed} "
                f"has_setup={first_run.has_setup(app.cfg)} "
                f"state={app.cfg.get('onboarding_state')!r} "
                f"resume={app.cfg.get('onboarding_resume_step')!r}")
            app.maybe_start_first_run(pre_access, config_existed)
        except Exception as _fr_e:
            _show_first = True
            import traceback
            _boot_log(f"first_run failed: {_fr_e!r}\n{traceback.format_exc()[-1200:]}")
            try:
                app._status(f"首次安装引导启动失败：{_fr_e}", "warn")
            except Exception:
                pass
        # 更新说明：已有用户在新版本首次启动时播放一次；
        # 新用户/重装用户先完成契约与引路，再由 _on_onboarding_done 接手，
        # 不能在启动这里提前 mark_seen，否则他们永远看不到本版说明。
        try:
            if _show_first:
                app._pending_whats_new = True
            else:
                app.root.after(
                    900, lambda: app.maybe_show_whats_new(config_existed))
        except Exception as _wn_e:
            _boot_log(f"whats new schedule failed: {_wn_e!r}")
        # 更新检查：首次安装/首启流程中完全跳过；之后每次启动只查一次。
        try:
            app._schedule_update_check(first_launch=bool(_show_first))
        except Exception as _upd_e:
            _boot_log(f"update schedule failed: {_upd_e!r}")

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























