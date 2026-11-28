"""博麗神社 · 境界設定（设置中心）。

只做界面与配置归位，不碰自动答题逻辑：
- 不 import web / answer_engine / prompts / llm 的求解路径；
- 只调用 App 已有的保存、通知、余额、更新、引导回调；
- 六个分区：契约、读符、退治、外观、香火钱、神社登记。
"""
from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from modules import first_run, llm, settings, theme, usage


NAV = [
    ("contract", "结界契约", "模型与 API", "✦"),
    ("capture", "读符术式", "OCR 与截图", "☯"),
    ("auto", "退治术式", "自动答题", "⛩"),
    ("look", "绘卷外观", "主题与通知", "❀"),
    ("usage", "香火钱", "用量与费用", "¥"),
    ("about", "神社登记", "授权与版本", "✧"),
]

QUOTES = {
    "contract": "慧音：契约上的字，要一笔一画写清楚。",
    "capture": "魔理沙：截图交给我，别把桌面乱七八糟的也塞进来。",
    "auto": "咲夜：时间要卡准；这一页只改入口和偏好。",
    "look": "紫：境界的景色，也要合你心意。",
    "usage": "灵梦：香火钱要算清楚，别到时候又装傻。",
    "about": "灵梦：神社的登记簿，可不是随便涂改的。",
}


class SettingsCenter(tk.Toplevel):
    """设置中心；所有配置键与现有 `self.*_var` 保持一一对应。"""

    def __init__(self, app, palette: dict):
        super().__init__(app.root)
        self.app = app
        self.C = palette
        self.F_UI = app.F_UI
        self.F_TITLE = app.F_TITLE
        self.F_JP = app.F_JP
        self.F_MONO = app.F_MONO
        self.cfg = app.cfg
        self._closed = False
        self._dirty = False
        self._loading = True
        self._pages: dict[str, tk.Frame] = {}
        self._canvases: dict[str, tk.Canvas] = {}
        self._nav_items: dict[str, tuple] = {}
        self._models = list(getattr(app, "_models", []) or [])
        self._mq: queue.Queue = queue.Queue()
        self._models_busy = False
        self._license_logo_ref = None
        self._current_page = "contract"
        self._snapshot = ()

        self._build_vars()
        self._build_window()
        self._build_pages()
        self._wire_dirty()
        self._snapshot = self._values()
        self._loading = False
        self._set_status("卷宗已合上。", self.C["muted"])
        self.show_page("contract")
        self.after(300, self._auto_fetch_models)
        self.app._settings_win = self

    # ------------------------------------------------------------------ vars
    def _build_vars(self) -> None:
        a = self.app
        self.v_provider = tk.StringVar()
        self.v_base = tk.StringVar(value=a.base_var.get())
        self.v_key = tk.StringVar(value=a.key_var.get())
        self.v_model = tk.StringVar(value=a.model_var.get())
        self.v_vision = tk.StringVar(value=a.vision_var.get())
        self.v_vision_base = tk.StringVar(value=a.vision_base_var.get())
        self.v_vision_key = tk.StringVar(value=a.vision_key_var.get())
        self.v_effort = tk.StringVar(value=a.effort_var.get())
        self.v_ocr = tk.StringVar(value=a.ocr_var.get())
        self.v_translate = tk.BooleanVar(value=bool(a.trans_var.get()))
        self.v_temp = tk.DoubleVar(value=float(a.temp_var.get() or 0.2))
        self.v_extra = tk.StringVar(value=a.extra_var.get())
        self.v_method = tk.StringVar(value=a.method_var.get())
        self.v_minimize = tk.BooleanVar(value=bool(a.minimize_var.get()))
        self.v_interval = tk.DoubleVar(value=float(a.interval_var.get() or 1.5))
        self.v_settle = tk.DoubleVar(value=float(a.settle_var.get() or 0.8))
        self.v_threshold = tk.DoubleVar(value=float(a.threshold_var.get() or 1.5))
        self.v_clip = tk.BooleanVar(value=bool(a.clip_var.get()))
        self.v_browser = tk.BooleanVar(value=bool(a.browser_only_var.get()))
        self.v_port = tk.IntVar(value=int(a.web_port_var.get() or 9222))
        self.v_continue = tk.BooleanVar(value=bool(a.continue_wrong_var.get()))
        self.v_start_url = tk.StringVar(value=a.start_url_var.get())
        self.v_theme = tk.StringVar(
            value=str(self.cfg.get("theme", theme.THEME_CLASSIC)))
        self.v_toast = tk.BooleanVar(value=bool(a.toast_enabled_var.get()))
        self.v_toast_update = tk.BooleanVar(value=bool(a.toast_update_var.get()))
        self.v_toast_trial = tk.BooleanVar(value=bool(a.toast_trial_var.get()))
        self.v_toast_balance = tk.BooleanVar(value=bool(a.toast_balance_var.get()))
        self.v_toast_auto = tk.BooleanVar(value=bool(a.toast_auto_var.get()))
        self.v_quiet_start = tk.IntVar(value=int(a.toast_quiet_start_var.get()))
        self.v_quiet_end = tk.IntVar(value=int(a.toast_quiet_end_var.get()))
        self.v_channel = tk.StringVar(value=a.update_channel_var.get())
        self.v_update_enabled = tk.BooleanVar(value=bool(a.update_enabled_var.get()))
        self.v_update_interval = tk.StringVar(value=a.update_interval_var.get())
        self.v_update_custom = tk.IntVar(value=int(a.update_custom_var.get() or 5))
        self.v_update_threads = tk.IntVar(value=int(a.update_max_threads_var.get() or 8))
        self.v_update_snooze = tk.StringVar(value="未封笔")
        a._snooze_var = self.v_update_snooze
        self.v_balance = tk.StringVar(value="灵梦：想查香火钱，就点下面的按钮。")
        self.v_conn = tk.StringVar(value="慧音：契约填好后，可以试探一下式神。")

        self._all_vars = [
            self.v_provider, self.v_base, self.v_key, self.v_model, self.v_vision,
            self.v_vision_base, self.v_vision_key, self.v_effort, self.v_ocr,
            self.v_translate, self.v_temp, self.v_extra, self.v_method,
            self.v_minimize, self.v_interval, self.v_settle, self.v_threshold,
            self.v_clip, self.v_browser, self.v_port, self.v_continue,
            self.v_start_url, self.v_theme, self.v_toast, self.v_toast_update,
            self.v_toast_trial, self.v_toast_balance, self.v_toast_auto,
            self.v_quiet_start, self.v_quiet_end, self.v_channel,
            self.v_update_enabled, self.v_update_interval,
            self.v_update_custom, self.v_update_threads,
        ]

    # --------------------------------------------------------------- window
    def _build_window(self) -> None:
        C = self.C
        self.title("博麗神社 · 境界設定")
        self.configure(bg=C["bg"])
        self.transient(self.app.root)
        self.resizable(True, True)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        # 设置中心做成宽长方形；小屏仍留出标题栏/任务栏空间。
        min_w = max(720, min(1020, sw - 80))
        min_h = max(520, min(660, sh - 90))
        self.minsize(min_w, min_h)
        w = max(min_w, min(1200, sw - 80))
        h = max(min_h, min(780, sh - 90))
        x = min(max(20, self.app.root.winfo_rootx() + 40), max(20, sw - w - 20))
        y = min(max(20, self.app.root.winfo_rooty() + 20), max(20, sh - h - 20))
        self.geometry(f"{w}x{h}+{x}+{y}")

        self._nav = tk.Frame(self, bg=C["panel"], width=190)
        self._nav.pack(side="left", fill="y")
        self._nav.pack_propagate(False)

        tk.Label(self._nav, text="博麗神社", bg=C["panel"], fg=C["gold"],
                 font=(self.F_TITLE, 20)).pack(pady=(18, 0))
        tk.Label(self._nav, text="境 界 設 定", bg=C["panel"], fg=C["muted"],
                 font=(self.F_JP, 9)).pack(pady=(0, 2))
        tk.Label(self._nav, text="～ 一处一处，慢慢理～", bg=C["panel"], fg=C["muted"],
                 font=(self.F_UI, 8)).pack(pady=(0, 12))

        for key, title, sub, glyph in NAV:
            item = tk.Frame(self._nav, bg=C["panel"], cursor="hand2")
            item.pack(fill="x", padx=10, pady=2)
            bar = tk.Frame(item, bg=C["panel"], width=3)
            bar.pack(side="left", fill="y")
            txt = tk.Frame(item, bg=C["panel"])
            txt.pack(side="left", fill="x", expand=True, padx=(8, 0), pady=5)
            t1 = tk.Label(txt, text=f"{glyph}  {title}", bg=C["panel"], fg=C["text"],
                          anchor="w", font=(self.F_UI, 11, "bold"))
            t1.pack(fill="x")
            t2 = tk.Label(txt, text=f"    {sub}", bg=C["panel"], fg=C["muted"],
                          anchor="w", font=(self.F_UI, 8))
            t2.pack(fill="x")
            self._nav_items[key] = (item, bar, txt, t1, t2)
            for wdg in (item, bar, txt, t1, t2):
                wdg.bind("<Button-1>", lambda _e, k=key: self.show_page(k))

        tk.Label(self._nav, text="东方 Project 二次创作", bg=C["panel"], fg=C["muted"],
                 font=(self.F_UI, 8)).pack(side="bottom", pady=12)

        self._main = tk.Frame(self, bg=C["bg"])
        self._main.pack(side="left", fill="both", expand=True)
        self._content = tk.Frame(self._main, bg=C["bg"])

        head = tk.Frame(self._main, bg=C["bg"])
        head.pack(fill="x", padx=24, pady=(16, 4))
        self.page_title_var = tk.StringVar()
        self.page_sub_var = tk.StringVar()
        self.page_quote_var = tk.StringVar()
        tk.Label(head, textvariable=self.page_title_var, bg=C["bg"], fg=C["gold"],
                 anchor="w", font=(self.F_TITLE, 22)).pack(fill="x")
        tk.Label(head, textvariable=self.page_sub_var, bg=C["bg"], fg=C["text"],
                 anchor="w", font=(self.F_UI, 10)).pack(fill="x", pady=(1, 0))
        tk.Label(head, textvariable=self.page_quote_var, bg=C["bg"], fg=C["muted"],
                 anchor="w", font=(self.F_UI, 9)).pack(fill="x", pady=(2, 0))
        tk.Frame(self._main, bg=C["border"], height=1).pack(fill="x", padx=24, pady=(8, 0))

        foot = tk.Frame(self._main, bg=C["bg"])
        foot.pack(side="bottom", fill="x", padx=24, pady=12)
        self.foot_status = tk.Label(foot, text="卷宗已合上。", bg=C["bg"],
                                    fg=C["muted"], anchor="w", font=(self.F_UI, 9))
        self.foot_status.pack(side="left", fill="x", expand=True)
        self.save_btn = self._button(foot, "记入卷宗", self._save, primary=True)
        self.save_btn.pack(side="right", padx=(10, 0))
        self.cancel_btn = self._button(foot, "收回符纸", self._on_close)
        self.cancel_btn.pack(side="right")

        self._content.pack(fill="both", expand=True, padx=14, pady=(8, 0))
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Escape>", lambda _e: self._on_close())
        self.bind("<Control-s>", lambda _e: self._save())

    # --------------------------------------------------------------- widgets
    def _button(self, parent, text, command, primary=False, small=False):
        C = self.C
        return tk.Button(
            parent, text=text, command=command,
            bg=C["accent"] if primary else C["panel2"],
            fg="#ffffff" if primary else C["text"],
            activebackground=C["accent_dark"] if primary else C["border"],
            activeforeground="#ffffff" if primary else C["gold"],
            relief="flat", bd=0, cursor="hand2",
            padx=12 if small else 18, pady=4 if small else 6,
            font=(self.F_UI, 9 if small else 10, "bold" if primary else "normal"))

    def _entry(self, parent, var, show=None):
        return ttk.Entry(parent, textvariable=var, show=show or "")

    def _combo(self, parent, var, values, readonly=True, width=26):
        return ttk.Combobox(parent, textvariable=var, values=values,
                            state="readonly" if readonly else "normal", width=width)

    def _spin(self, parent, var, lo, hi, inc=1, width=6):
        return ttk.Spinbox(parent, from_=lo, to=hi, increment=inc,
                           textvariable=var, width=width)

    def _card(self, parent, title: str, desc: str = "") -> tk.Frame:
        C = self.C
        card = tk.Frame(parent, bg=C["panel"], highlightbackground=C["border"],
                        highlightthickness=1)
        card.pack(fill="x", pady=(0, 12))
        inner = tk.Frame(card, bg=C["panel"], padx=16, pady=12)
        inner.pack(fill="x")
        tk.Label(inner, text=f"✦  {title}", bg=C["panel"], fg=C["gold"],
                 anchor="w", font=(self.F_TITLE, 13)).pack(fill="x")
        if desc:
            tk.Label(inner, text=desc, bg=C["panel"], fg=C["muted"],
                     anchor="w", font=(self.F_UI, 9)).pack(fill="x", pady=(1, 6))
        grid = tk.Frame(inner, bg=C["panel"])
        grid.pack(fill="x", pady=(3, 0))
        grid.columnconfigure(1, weight=1)
        return grid

    def _add_row(self, grid, row: int, primary: str, secondary: str,
                 widget, hint: str = "", sticky: str = "ew"):
        C = self.C
        lab = tk.Frame(grid, bg=C["panel"])
        lab.grid(row=row, column=0, sticky="ne", padx=(0, 12), pady=5)
        tk.Label(lab, text=primary, bg=C["panel"], fg=C["text"], anchor="e",
                 font=(self.F_UI, 10, "bold")).pack(fill="x")
        if secondary:
            tk.Label(lab, text=secondary, bg=C["panel"], fg=C["muted"], anchor="e",
                     font=(self.F_UI, 8)).pack(fill="x")
        widget.grid(row=row, column=1, sticky=sticky, pady=4)
        if hint:
            tk.Label(grid, text=hint, bg=C["panel"], fg=C["muted"], anchor="w",
                     justify="left", wraplength=190,
                     font=(self.F_UI, 8)).grid(row=row, column=2, sticky="w",
                                               padx=(10, 0), pady=4)

    def _note(self, parent, text: str, color: str | None = None):
        C = self.C
        return tk.Label(parent, text=text, bg=C["bg"], fg=color or C["muted"],
                        anchor="w", justify="left", wraplength=720,
                        font=(self.F_UI, 9))

    def _bind_wheel(self, canvas: tk.Canvas) -> None:
        def _wheel(e):
            canvas.yview_scroll(int(-e.delta / 120), "units")

        def _walk(w):
            w.bind("<MouseWheel>", _wheel)
            for ch in w.winfo_children():
                _walk(ch)

        _walk(canvas)

    # ----------------------------------------------------------------- pages
    def _make_page(self, key: str, builder) -> None:
        C = self.C
        outer = tk.Frame(self._content, bg=C["bg"])
        canvas = tk.Canvas(outer, bg=C["bg"], highlightthickness=0, bd=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        body = tk.Frame(canvas, bg=C["bg"], padx=18, pady=4)
        win = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))
        self._pages[key] = outer
        self._canvases[key] = canvas
        builder(body)
        self._bind_wheel(canvas)

    def _build_pages(self) -> None:
        self._make_page("contract", self._page_contract)
        self._make_page("capture", self._page_capture)
        self._make_page("auto", self._page_auto)
        self._make_page("look", self._page_look)
        self._make_page("usage", self._page_usage)
        self._make_page("about", self._page_about)

    def show_page(self, key: str) -> None:
        if key not in self._pages:
            return
        for k, w in self._pages.items():
            if k == key:
                w.pack(fill="both", expand=True)
            else:
                w.pack_forget()
        title = next((n[1] for n in NAV if n[0] == key), key)
        sub = next((n[2] for n in NAV if n[0] == key), "")
        self.page_title_var.set(title)
        self.page_sub_var.set(sub)
        self.page_quote_var.set(QUOTES.get(key, ""))
        self._current_page = key
        for k, (item, bar, txt, t1, t2) in self._nav_items.items():
            active = k == key
            bg = self.C["panel2"] if active else self.C["panel"]
            item.configure(bg=bg)
            bar.configure(bg=self.C["accent"] if active else self.C["panel"])
            for wdg in (item, txt, t1, t2):
                wdg.configure(bg=bg)
            t1.configure(fg=self.C["gold"] if active else self.C["text"])

    # ------------------------------------------------------------------ page 1
    def _page_contract(self, body: tk.Frame) -> None:
        C = self.C
        g = self._card(body, "契约与坐标", "模型平台、接口地址与通行密钥")
        prov = self._combo(g, self.v_provider, [n for n, _ in llm.PROVIDER_PRESETS])
        prov.bind("<<ComboboxSelected>>", self._on_provider)
        self._add_row(g, 0, "结界来源", "模型平台", prov, "DeepSeek / OpenAI / 智谱 / 通义")
        self._add_row(g, 1, "术式坐标", "Base URL", self._entry(g, self.v_base),
                      "接口地址，末尾一般不带 /")
        key_row = tk.Frame(g, bg=C["panel"])
        key_entry = self._entry(key_row, self.v_key, show="•")
        key_entry.pack(side="left", fill="x", expand=True)
        show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(key_row, text="显示", variable=show_var,
                        command=lambda: key_entry.configure(show="" if show_var.get() else "•")
                        ).pack(side="left", padx=(8, 0))
        self._add_row(g, 2, "通行密钥", "API Key", key_row, "DPAPI 加密保存在本机")

        g2 = self._card(body, "式神选择", "主模型、视觉模型与推理强度")
        model_row = tk.Frame(g2, bg=C["panel"])
        model_row.columnconfigure(0, weight=1)
        self.model_box = self._combo(model_row, self.v_model, list(self._models),
                                     readonly=False, width=30)
        self.model_box.grid(row=0, column=0, sticky="ew")
        self._button(model_row, "去名录翻一翻", self.refresh_models,
                     small=True).grid(row=0, column=1, padx=(8, 0))
        self._add_row(g2, 0, "退治式神", "答题模型", model_row, "主要写答案的模型")
        self.vision_box = self._combo(
            g2, self.v_vision, ["（使用答题模型）"] + list(self._models), width=30)
        self._add_row(g2, 1, "读图式神", "视觉模型", self.vision_box,
                      "识图用；也可沿用主模型")
        self._add_row(g2, 2, "读图坐标", "视觉 Base URL",
                      self._entry(g2, self.v_vision_base), "留空 = 用主接口")
        vk_row = tk.Frame(g2, bg=C["panel"])
        vk_entry = self._entry(vk_row, self.v_vision_key, show="•")
        vk_entry.pack(side="left", fill="x", expand=True)
        vk_show = tk.BooleanVar(value=False)
        ttk.Checkbutton(vk_row, text="显示", variable=vk_show,
                        command=lambda: vk_entry.configure(show="" if vk_show.get() else "•")
                        ).pack(side="left", padx=(8, 0))
        self._add_row(g2, 3, "读图密钥", "视觉 Key", vk_row, "留空 = 用主 Key")
        self._add_row(g2, 4, "灵力强度", "推理强度",
                      self._combo(g2, self.v_effort,
                                  [label for label, _ in llm.EFFORT_OPTIONS], width=24),
                      "越高越慢，通常越稳")

        g3 = self._card(body, "附加咒文", "透传给接口的额外 JSON")
        self._add_row(g3, 0, "附加咒文", "extra JSON", self._entry(g3, self.v_extra),
                      "可留空；必须是 JSON 对象")

        g4 = self._card(body, "连接检查", "确认坐标与式神都能应答")
        row = tk.Frame(g4, bg=C["panel"])
        self.test_btn = self._button(row, "试探式神", self.test_connection, primary=True)
        self.test_btn.pack(side="left")
        self._button(row, "去名录翻一翻", self.refresh_models, small=True).pack(
            side="left", padx=(8, 0))
        self._add_row(g4, 0, "试探", "测试连接", row, "只拉模型列表，不写题")
        tk.Label(g4, textvariable=self.v_conn, bg=C["panel"], fg=C["muted"],
                 anchor="w", justify="left", wraplength=650,
                 font=(self.F_UI, 9)).grid(row=1, column=0, columnspan=3,
                                           sticky="w", pady=(4, 0))

        self._sync_provider_from_base()
        self.app._dlg_model_box = self.model_box
        self.app._dlg_model_var = self.v_model
        self.app._dlg_vision_box = self.vision_box
        self.app._dlg_key_var = self.v_key
        self.app._dlg_base_var = self.v_base

    # ------------------------------------------------------------------ page 2
    def _page_capture(self, body: tk.Frame) -> None:
        C = self.C
        g = self._card(body, "读符方式", "题目怎么被看懂")
        self._add_row(g, 0, "读符方式", "OCR / 视觉",
                      self._combo(g, self.v_ocr, ["自动", "视觉模型", "本地 OCR"]),
                      "自动 = 视觉优先，失败转本地")
        row = tk.Frame(g, bg=C["panel"])
        ttk.Checkbutton(row, text="英文题自动翻译", variable=self.v_translate).pack(side="left")
        tk.Label(row, text="温度", bg=C["panel"], fg=C["muted"],
                 font=(self.F_UI, 9)).pack(side="left", padx=(18, 4))
        self._spin(row, self.v_temp, 0.0, 2.0, 0.1, 5).pack(side="left")
        self._add_row(g, 1, "译符", "翻译与温度", row, "英文题可自动转成中文")

        g2 = self._card(body, "抽符与结界", "截屏方式、自动监视与剪贴板")
        self._add_row(g2, 0, "抽符方式", "截图方式",
                      self._combo(g2, self.v_method,
                                  ["屏幕抓取（所见即所得）",
                                   "后台抓取（可抓被遮挡窗口）"], width=30),
                      "后台抓取可抓被遮挡窗口")
        rowm = tk.Frame(g2, bg=C["panel"])
        ttk.Checkbutton(rowm, text="截图时本窗口自动让位",
                        variable=self.v_minimize).pack(side="left")
        self._add_row(g2, 1, "结界遮蔽", "截图时让位", rowm, "避免把自己的窗口截进去")

        rowauto = tk.Frame(g2, bg=C["panel"])
        for text, var, lo, hi, inc, w in (
            ("间隔", self.v_interval, 0.5, 600.0, 0.5, 6),
            ("静置", self.v_settle, 0.0, 600.0, 0.2, 6),
            ("阈值", self.v_threshold, 0.0, 100.0, 0.2, 6),
        ):
            tk.Label(rowauto, text=text, bg=C["panel"], fg=C["muted"],
                     font=(self.F_UI, 9)).pack(side="left", padx=(0, 4))
            self._spin(rowauto, var, lo, hi, inc, w).pack(side="left", padx=(0, 12))
        self._add_row(g2, 2, "自动监视", "间隔 / 静置 / 阈值", rowauto,
                      "间隔、静置单位秒；阈值是画面变化分数")

        rowclip = tk.Frame(g2, bg=C["panel"])
        ttk.Checkbutton(rowclip, text="剪贴板自动识别（Win+Shift+S）",
                        variable=self.v_clip).pack(side="left")
        self._add_row(g2, 3, "剪贴符纸", "剪贴板识别", rowclip, "截图后自动读剪贴板")
        rowb = tk.Frame(g2, bg=C["panel"])
        ttk.Checkbutton(rowb, text="自动监听只扫浏览器前台",
                        variable=self.v_browser).pack(side="left")
        self._add_row(g2, 4, "结界范围", "只扫浏览器", rowb, "避免误识别其他窗口")

        self._note(body, "这一页只改识别与截屏偏好，不改动自动答题的求解代码。",
                   C["muted"]).pack(anchor="w", pady=(0, 8))

    # ------------------------------------------------------------------ page 3
    def _page_auto(self, body: tk.Frame) -> None:
        C = self.C
        g = self._card(body, "结界入口", "答题浏览器与起始页面")
        roww = tk.Frame(g, bg=C["panel"])
        tk.Label(roww, text="调试端口", bg=C["panel"], fg=C["muted"],
                 font=(self.F_UI, 9)).pack(side="left")
        self._spin(roww, self.v_port, 1024, 65535, 1, 8).pack(side="left", padx=(6, 0))
        self._add_row(g, 0, "结界入口", "调试端口", roww, "对应『启动答题浏览器.bat』")
        self._add_row(g, 1, "入口坐标", "起始网址",
                      self._entry(g, self.v_start_url), "点『张开结界』时打开这个页面")

        g2 = self._card(body, "退治偏好", "只影响入口与做题偏好")
        row = tk.Frame(g2, bg=C["panel"])
        ttk.Checkbutton(row, text="答错也继续下一题",
                        variable=self.v_continue).pack(side="left")
        self._add_row(g2, 0, "退治", "答错继续", row, "全自动仍需手动点『开始退治』")

        self._note(body, "咲夜：这里的改动只影响入口和偏好，不会替你多点一次 Check；"
                         "自动答题逻辑本轮没有改动。", C["muted"]).pack(anchor="w", pady=(0, 8))

    # ------------------------------------------------------------------ page 4
    def _page_look(self, body: tk.Frame) -> None:
        C = self.C
        g = self._card(body, "绘卷主题", "主界面与启动画面的外观")
        unlocked = bool(self.cfg.get("theme_unlocked"))
        row = tk.Frame(g, bg=C["panel"])
        rb1 = tk.Radiobutton(
            row, text="经典", variable=self.v_theme, value=theme.THEME_CLASSIC,
            bg=C["panel"], fg=C["text"], selectcolor=C["panel2"],
            activebackground=C["panel"], activeforeground=C["gold"],
            font=(self.F_UI, 10), cursor="hand2")
        rb1.pack(side="left", padx=(0, 18))
        rb2 = tk.Radiobutton(
            row, text="晨午宵绘卷" + ("" if unlocked else "  🔒"),
            variable=self.v_theme, value=theme.THEME_NEW,
            bg=C["panel"], fg=C["text"], selectcolor=C["panel2"],
            activebackground=C["panel"], activeforeground=C["gold"],
            font=(self.F_UI, 10), cursor="hand2")
        rb2.pack(side="left")
        if not unlocked:
            rb2.configure(state="disabled")
            self.v_theme.set(theme.THEME_CLASSIC)
        self._add_row(g, 0, "绘卷", "主题", row, "新主题随时段切换主界面与启动画面")
        self._note(g, "晨午宵绘卷需要解锁；切换后需要重启主界面才能完全换装。",
                   C["muted"]).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 0))

        g2 = self._card(body, "式神传讯", "Windows 通知与安静时段")
        ttk.Checkbutton(g2, text="启用式神传讯", variable=self.v_toast).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        flags = tk.Frame(g2, bg=C["panel"])
        for text, var in (("号外", self.v_toast_update), ("结界", self.v_toast_trial),
                          ("香火钱", self.v_toast_balance), ("退治", self.v_toast_auto)):
            ttk.Checkbutton(flags, text=text, variable=var).pack(side="left", padx=(0, 12))
        self._add_row(g2, 1, "栏目", "通知类型", flags, "号外 / 试用 / 余额 / 退治")
        quiet = tk.Frame(g2, bg=C["panel"])
        tk.Label(quiet, text="从", bg=C["panel"], fg=C["muted"],
                 font=(self.F_UI, 9)).pack(side="left")
        self._spin(quiet, self.v_quiet_start, 0, 23, 1, 4).pack(side="left", padx=3)
        tk.Label(quiet, text="点到", bg=C["panel"], fg=C["muted"],
                 font=(self.F_UI, 9)).pack(side="left")
        self._spin(quiet, self.v_quiet_end, 0, 23, 1, 4).pack(side="left", padx=3)
        tk.Label(quiet, text="点", bg=C["panel"], fg=C["muted"],
                 font=(self.F_UI, 9)).pack(side="left")
        self._add_row(g2, 2, "打盹", "安静时段", quiet, "安静时段不打扰；结界到期除外")
        self._add_row(g2, 3, "试听", "测试通知",
                      self._button(g2, "让式神传一声", self.app._test_toast, small=True),
                      "弹一条测试通知", sticky="w")

    # ------------------------------------------------------------------ page 5
    def _page_usage(self, body: tk.Frame) -> None:
        C = self.C
        g = self._card(body, "香火钱", "最近的调用与花费")
        try:
            data = usage.summary(30)
            today = data["today"]
            total = data["total"]
            text = (f"今日：{today['calls']} 次 · {today['tokens']} tokens · "
                    f"¥{today['cost']:.4f}    累计：{total['calls']} 次 · "
                    f"{total['tokens']} tokens · ¥{total['cost']:.4f}")
        except Exception as e:
            text = f"账本读取失败：{e}"
        tk.Label(g, text=text, bg=C["panel"], fg=C["text"], anchor="w",
                 justify="left", wraplength=680,
                 font=(self.F_UI, 10)).grid(row=0, column=0, columnspan=3,
                                            sticky="w", pady=(0, 8))
        row = tk.Frame(g, bg=C["panel"])
        self._button(row, "打开账本", self.app._open_usage, primary=True).pack(side="left")
        self.balance_btn = self._button(row, "查余额", self._do_balance, small=True)
        self.balance_btn.pack(side="left", padx=(8, 0))
        self._add_row(g, 1, "账本", "明细与导出", row, "打开完整账本，可导出 CSV")
        tk.Label(g, textvariable=self.v_balance, bg=C["panel"], fg=C["muted"],
                 anchor="w", justify="left", wraplength=680,
                 font=(self.F_UI, 9)).grid(row=2, column=0, columnspan=3,
                                           sticky="w", pady=(6, 0))
        self._note(body, "灵梦：账本只记在本机；清空或导出都在『打开账本』里。",
                   C["muted"]).pack(anchor="w", pady=(0, 8))

    # ------------------------------------------------------------------ page 6
    def _page_about(self, body: tk.Frame) -> None:
        C = self.C
        g = self._card(body, "神社登记", "授权、机器码与激活")
        auth_text, auth_color, machine, auth_state = self._auth_info()
        row = tk.Frame(g, bg=C["panel"])
        try:
            logo_name = "license_ok" if auth_state == "licensed" else "license_no"
            logo_path = os.path.join(
                getattr(self.app, "ASSETS", os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "assets")), "license", f"{logo_name}.png")
            _im = Image.open(logo_path).convert("RGBA").resize((96, 96), Image.LANCZOS)
            self._license_logo_ref = ImageTk.PhotoImage(_im)
            tk.Label(row, image=self._license_logo_ref, bg=C["panel"], bd=0).pack(
                side="left", padx=(0, 10))
        except Exception:
            pass
        tk.Label(row, text=auth_text, bg=C["panel"], fg=auth_color,
                 font=(self.F_UI, 9)).pack(side="left")
        self._button(row, "查看许可", self.app._open_activation, small=True).pack(
            side="left", padx=(10, 0))
        self._button(row, "复制灵符", lambda: self._copy_machine(machine), small=True).pack(
            side="left", padx=(6, 0))
        self._add_row(g, 0, "登记", "授权状态", row, "永久许可 / 试用 / 未登记")
        self._add_row(g, 1, "本机灵符", "机器码",
                      tk.Label(g, text=machine, bg=C["panel"], fg=C["gold"],
                               anchor="w", font=(self.F_MONO[0], 9)),
                      "激活时把这段完整交给神社")

        g2 = self._card(body, "引路与契约", "契约配置与新手引导")
        state = str(self.cfg.get("onboarding_state") or "").strip()
        contract_ok = first_run.has_setup(self.cfg)
        if state in (first_run.STATE_PENDING, first_run.STATE_IN_PROGRESS):
            tour = "引路：未完成"
        elif state == first_run.STATE_DONE and self.cfg.get("onboarding_tour_skipped"):
            tour = "引路：已跳过"
        elif state == first_run.STATE_DONE:
            tour = "引路：已完成"
        elif state == first_run.STATE_LEGACY:
            tour = "引路：老用户升级，不自动弹出"
        else:
            tour = "引路：未开始"
        contract = "契约：已配置" if contract_ok else "契约：未完成"
        label = f"{contract}  ｜  {tour}"
        row = tk.Frame(g2, bg=C["panel"])
        if not contract_ok:
            self._button(row, "去结界契约", lambda: self.show_page("contract"),
                         small=True).pack(side="left")
        self._button(row, "重看引路", self._open_onboarding, small=True).pack(
            side="left", padx=(8, 0) if not contract_ok else (0, 0))
        tk.Label(row, text=label, bg=C["panel"], fg=C["muted"],
                 font=(self.F_UI, 8)).pack(side="left", padx=(10, 0))
        self._add_row(g2, 0, "引路", "新手引导", row,
                      "契约没配好可在左侧补；引路随时可重看，不会清空配置")

        g3 = self._card(body, "文文的号外", "自动打听、封笔与下载分片")
        auto_row = tk.Frame(g3, bg=C["panel"])
        ttk.Checkbutton(auto_row, text="让文文定期去打听新版本",
                        variable=self.v_update_enabled).pack(side="left")
        self._add_row(g3, 0, "自动打听", "定时检查", auto_row, "关掉就完全手动")

        self._add_row(g3, 1, "报信路线", "更新渠道",
                      self._combo(g3, self.v_channel,
                                  list(self.app.CHANNEL_LABELS.values()), width=22),
                      "Gitee 国内快，GitHub 是主仓库")

        int_row = tk.Frame(g3, bg=C["panel"])
        self._combo(int_row, self.v_update_interval,
                    list(self.app.INTERVAL_LABELS.values()) + ["自定义"],
                    width=12).pack(side="left")
        self._spin(int_row, self.v_update_custom, 1, 720, 1, 6).pack(
            side="left", padx=(8, 0))
        tk.Label(int_row, text="小时", bg=C["panel"], fg=C["muted"],
                 font=(self.F_UI, 9)).pack(side="left", padx=(5, 0))
        self._add_row(g3, 2, "报信间隔", "检查间隔", int_row,
                      "选“自定义”时用右边的数字")

        snooze_row = tk.Frame(g3, bg=C["panel"])
        tk.Label(snooze_row, textvariable=self.v_update_snooze, bg=C["panel"],
                 fg=C["muted"], font=(self.F_UI, 9)).pack(side="left")
        self._button(snooze_row, "选日子", self.app._pick_snooze,
                     small=True).pack(side="left", padx=(10, 0))
        self._button(snooze_row, "歇 3 天", lambda: self.app._snooze_days(3),
                     small=True).pack(side="left", padx=(6, 0))
        self._button(snooze_row, "歇 7 天", lambda: self.app._snooze_days(7),
                     small=True).pack(side="left", padx=(6, 0))
        self.app._refresh_update_labels()
        self._add_row(g3, 3, "封笔到", "暂停自动打听", snooze_row,
                      "只停自动检查；手动“立即打听”不受影响")

        self.update_last_var = tk.StringVar()
        self.app._update_last_var = self.update_last_var
        try:
            self.app._refresh_update_labels()
        except Exception:
            self.update_last_var.set("上次打听：未知")
        row = tk.Frame(g3, bg=C["panel"])
        tk.Label(row, textvariable=self.update_last_var, bg=C["panel"],
                 fg=C["muted"], font=(self.F_UI, 8)).pack(side="left")
        self._button(row, "立即打听", lambda: self.app._check_updates(manual=True),
                     small=True).pack(side="left", padx=(10, 0))
        self._add_row(g3, 4, "上次打听", "最近检查", row,
                      "每次启动检查；运行期间按上面的间隔再查")

        thread_row = tk.Frame(g3, bg=C["panel"])
        self._spin(thread_row, self.v_update_threads, 1, 32, 1, 6).pack(side="left")
        tk.Label(thread_row, text="个线程", bg=C["panel"], fg=C["muted"],
                 font=(self.F_UI, 9)).pack(side="left", padx=(5, 0))
        self._add_row(g3, 5, "最多分片", "下载线程", thread_row,
                      "1–32；服务器不支持 Range 时自动降为 1")

        g4 = self._card(body, "关于", "版本、许可与项目链接")
        self._add_row(g4, 0, "版本", "当前版本",
                      tk.Label(g4, text=f"v{settings.APP_VERSION} · MIT License",
                               bg=C["panel"], fg=C["gold"],
                               font=(self.F_MONO[0], 10)), "")
        row = tk.Frame(g4, bg=C["panel"])
        self._button(row, "更新说明", lambda: self.app.open_whats_new(manual=True),
                     small=True).pack(side="left")
        self._button(row, "关于程序", self.app._about_app, small=True).pack(
            side="left", padx=(8, 0))
        for label, url in (("GitHub", "https://github.com/Jerry9335/SpellCardHomework"),
                           ("官网", "https://jerry9335.github.io/SpellCardHomework/")):
            self._button(row, label, lambda u=url: self.app._open_url(u),
                         small=True).pack(side="left", padx=(8, 0))
        self._add_row(g4, 1, "项目", "源码与官网", row, "MIT License；仅供个人学习使用")

    # ------------------------------------------------------------- callbacks
    def _sync_provider_from_base(self) -> None:
        base = self.v_base.get().rstrip("/")
        for name, preset in llm.PROVIDER_PRESETS:
            if base == preset.rstrip("/"):
                self.v_provider.set(name)
                return

    def _on_provider(self, _ev=None) -> None:
        old_base = self.v_base.get().strip().rstrip("/")
        for name, preset in llm.PROVIDER_PRESETS:
            if name != self.v_provider.get():
                continue
            self.v_base.set(preset)
            if preset.rstrip("/") == old_base:
                return
            self.v_model.set("")
            self._models = []
            try:
                self.model_box.configure(values=[])
            except Exception:
                pass
            self._set_conn("紫：结界来源换了，先重新拉一次式神名单。", self.C["muted"])
            if self.v_key.get().strip():
                self.after(250, self.refresh_models)
            return

    def _auto_fetch_models(self) -> None:
        if self._closed:
            return
        if self.v_base.get().strip() and self.v_key.get().strip():
            self.refresh_models(silent=True)

    def refresh_models(self, silent: bool = False) -> None:
        if self._models_busy:
            return
        base = self.v_base.get().strip()
        key = self.v_key.get().strip()
        if not base or not key:
            self._set_conn("魔理沙：坐标和通行密钥都没填，名录翻不开。", self.C["warn"])
            return
        self._models_busy = True
        try:
            self.test_btn.configure(state="disabled")
        except Exception:
            pass
        if not silent:
            self._set_conn("魔理沙：去名录里翻一翻…", self.C["muted"])

        def work():
            try:
                models = llm.list_models(base, key)
                self._mq.put(("ok", models))
            except Exception as e:
                self._mq.put(("err", str(e)))

        threading.Thread(target=work, daemon=True).start()
        self.after(150, self._poll_models)

    def _poll_models(self) -> None:
        if self._closed:
            return
        try:
            kind, payload = self._mq.get_nowait()
        except queue.Empty:
            if self._models_busy:
                self.after(150, self._poll_models)
            return
        self._models_busy = False
        try:
            self.test_btn.configure(state="normal")
        except Exception:
            pass
        if kind == "err":
            self._set_conn(f"魔理沙：式神没应声——{payload}", self.C["err"])
            return
        self._models = list(payload or [])
        try:
            self.model_box.configure(values=self._models)
            self.vision_box.configure(values=["（使用答题模型）"] + self._models)
        except Exception:
            pass
        try:
            self.app._models = list(self._models)
        except Exception:
            pass
        self._set_conn(f"慧音：式神回应了，名录上有 {len(self._models)} 位。",
                       self.C["ok"])

    def test_connection(self) -> None:
        self.refresh_models()

    def _do_balance(self) -> None:
        self.balance_btn.configure(state="disabled")
        self.v_balance.set("灵梦：正在翻钱包…")

        def done(text: str, ok: bool) -> None:
            if self._closed:
                return
            self.v_balance.set(text)
            try:
                self.balance_btn.configure(state="normal")
            except Exception:
                pass

        self.app._check_balance_async(self.v_key.get().strip(),
                                      self.v_base.get().strip(), done)

    def _set_conn(self, text: str, color: str) -> None:
        try:
            self.v_conn.set(text)
        except Exception:
            pass

    def _auth_info(self) -> tuple[str, str, str, str]:
        C = self.C
        try:
            from modules import license as lic

            state, msg, days = lic.check_access(update=False)
            text = {
                "licensed": "已登记（永久许可）",
                "trial": (f"试用中（还剩 {days} 天）" if days > 0 else "试用中（最后几小时）"),
                "fresh": "未登记（可试用 3 天）",
                "expired": "试用已结束，需要许可",
                "tampered": "授权记录异常，需要重新登记",
            }.get(state, msg)
            color = C["ok"] if state == "licensed" else (
                C["warn"] if state == "trial" else C["err"])
            return text, color, lic.machine_code(), state
        except Exception as e:
            return f"授权检查失败：{e}", C["err"], "-", "tampered"

    def _copy_machine(self, machine: str) -> None:
        try:
            from modules import clipboard

            clipboard.copy_text(machine)
            self._set_status("灵梦：本机灵符已抄进剪贴板。", self.C["ok"])
        except Exception as e:
            self._set_status(f"复制失败：{e}", self.C["err"])

    def _open_onboarding(self) -> None:
        self._destroy()
        try:
            self.app.open_onboarding(manual=True)
        except Exception:
            pass

    # --------------------------------------------------------------- dirty
    def _wire_dirty(self) -> None:
        for var in self._all_vars:
            try:
                var.trace_add("write", lambda *_a: self._on_change())
            except Exception:
                pass

    def _on_change(self) -> None:
        if self._loading or self._closed:
            return
        if not self._dirty:
            self._dirty = True
            self._set_status("卷宗还有未保存的改动。", self.C["warn"])

    def _values(self) -> tuple:
        out = []
        for var in self._all_vars:
            try:
                out.append(str(var.get()))
            except Exception:
                out.append("")
        return tuple(out)

    def _set_status(self, text: str, color: str) -> None:
        try:
            self.foot_status.configure(text=text, fg=color)
        except Exception:
            pass

    # --------------------------------------------------------------- save
    def _save(self) -> bool:
        C = self.C

        def number(var, label, default, lo, hi):
            try:
                raw = str(var.get()).strip()
            except Exception:
                return None, f"{label}不是数字"
            if not raw:
                return default, None
            try:
                val = float(raw)
            except (TypeError, ValueError):
                return None, f"{label}不是数字"
            if not (lo <= val <= hi):
                return None, f"{label}要在 {lo}–{hi} 之间"
            return val, None

        nums = {}
        errors = []
        for var, label, default, lo, hi, page in (
            (self.v_temp, "灵力温度", 0.2, 0.0, 2.0, "capture"),
            (self.v_interval, "自动监视间隔", 1.5, 0.5, 600.0, "capture"),
            (self.v_settle, "静置时间", 0.8, 0.0, 600.0, "capture"),
            (self.v_threshold, "变化阈值", 1.5, 0.0, 100.0, "capture"),
            (self.v_port, "结界端口", 9222, 1024, 65535, "auto"),
        ):
            val, err = number(var, label, default, lo, hi)
            if err:
                errors.append((err, page))
            else:
                nums[label] = val

        raw_extra = self.v_extra.get().strip()
        if raw_extra:
            try:
                obj = json.loads(raw_extra)
                if not isinstance(obj, dict):
                    errors.append(("附加咒文必须是 JSON 对象", "contract"))
            except Exception:
                errors.append(("附加咒文不是合法 JSON", "contract"))

        if errors:
            msg, page = errors[0]
            self.show_page(page)
            self._set_status("灵梦：这几格看不懂——" + msg, C["err"])
            return False

        a = self.app
        a.base_var.set(self.v_base.get().strip())
        a.key_var.set(self.v_key.get().strip())
        a.model_var.set(self.v_model.get().strip())
        a.vision_var.set(self.v_vision.get().strip() or "（使用答题模型）")
        a.vision_base_var.set(self.v_vision_base.get().strip())
        a.vision_key_var.set(self.v_vision_key.get().strip())
        a.effort_var.set(self.v_effort.get())
        a.ocr_var.set(self.v_ocr.get())
        a.trans_var.set(bool(self.v_translate.get()))
        a.temp_var.set(float(nums["灵力温度"]))
        a.extra_var.set(raw_extra)
        a.method_var.set(self.v_method.get())
        a.minimize_var.set(bool(self.v_minimize.get()))
        a.interval_var.set(float(nums["自动监视间隔"]))
        a.settle_var.set(float(nums["静置时间"]))
        a.threshold_var.set(float(nums["变化阈值"]))
        a.clip_var.set(bool(self.v_clip.get()))
        a.browser_only_var.set(bool(self.v_browser.get()))
        a.web_port_var.set(int(nums["结界端口"]))
        a.continue_wrong_var.set(bool(self.v_continue.get()))
        a.start_url_var.set(self.v_start_url.get().strip() or "https://kysu.edu")
        a.update_channel_var.set(self.v_channel.get())
        a.update_enabled_var.set(bool(self.v_update_enabled.get()))
        a.update_interval_var.set(self.v_update_interval.get())
        try:
            a.update_custom_var.set(max(1, min(720, int(self.v_update_custom.get()))))
        except Exception:
            a.update_custom_var.set(5)
        try:
            a.update_max_threads_var.set(max(1, min(32, int(self.v_update_threads.get()))))
        except Exception:
            a.update_max_threads_var.set(8)
        a.toast_enabled_var.set(bool(self.v_toast.get()))
        a.toast_update_var.set(bool(self.v_toast_update.get()))
        a.toast_trial_var.set(bool(self.v_toast_trial.get()))
        a.toast_balance_var.set(bool(self.v_toast_balance.get()))
        a.toast_auto_var.set(bool(self.v_toast_auto.get()))
        a.toast_quiet_start_var.set(int(self.v_quiet_start.get()))
        a.toast_quiet_end_var.set(int(self.v_quiet_end.get()))

        chosen = self.v_theme.get()
        if chosen == theme.THEME_NEW and not self.cfg.get("theme_unlocked"):
            chosen = theme.THEME_CLASSIC
        old_theme = a.theme
        a.cfg["theme"] = chosen
        try:
            ok = a._save_config()
        except Exception:
            ok = False
        try:
            a._arm_update_timer()
        except Exception:
            pass
        if not ok:
            self._set_status("魔理沙：呜哇，卷宗没写进去——检查配置目录权限。", C["err"])
            return False
        self._dirty = False
        self._destroy()
        try:
            a._status("灵梦：记下了。", "ok")
        except Exception:
            pass
        if chosen != old_theme:
            try:
                a._request_theme_change(chosen)
            except Exception:
                pass
        return True

    # --------------------------------------------------------------- close
    def _on_close(self) -> None:
        if not self._dirty:
            self._destroy()
            return
        if self._ask_unsaved() == "save":
            self._save()

    def _ask_unsaved(self) -> str:
        C = self.C
        dlg = tk.Toplevel(self)
        dlg.title("紫：卷宗还没合上")
        dlg.configure(bg=C["bg"])
        dlg.transient(self)
        dlg.resizable(False, False)
        dlg.geometry(f"460x220+{self.winfo_rootx() + 260}+{self.winfo_rooty() + 220}")
        result = {"v": "cancel"}
        tk.Label(dlg, text="紫：卷宗还没合上", bg=C["bg"], fg=C["gold"],
                 font=(self.F_TITLE, 18)).pack(pady=(18, 4))
        tk.Label(dlg, text="要先把改动记进卷宗，还是就这么丢下它？",
                 bg=C["bg"], fg=C["text"], font=(self.F_UI, 10)).pack()
        row = tk.Frame(dlg, bg=C["bg"])
        row.pack(pady=22)

        def pick(v: str) -> None:
            result["v"] = v
            dlg.destroy()

        self._button(row, "记入卷宗", lambda: pick("save"), primary=True).pack(side="left")
        self._button(row, "收回符纸", lambda: pick("discard"), small=True).pack(
            side="left", padx=(10, 0))
        self._button(row, "继续写", lambda: pick("cancel"), small=True).pack(
            side="left", padx=(10, 0))
        dlg.protocol("WM_DELETE_WINDOW", lambda: pick("cancel"))
        dlg.bind("<Escape>", lambda _e: pick("cancel"))
        dlg.grab_set()
        self.wait_window(dlg)
        if result["v"] == "discard":
            self._destroy()
        return result["v"]

    def _destroy(self) -> None:
        if self._closed:
            return
        self._closed = True
        a = self.app
        try:
            if getattr(a, "_settings_win", None) is self:
                a._settings_win = None
            for name in ("_dlg_model_box", "_dlg_vision_box", "_dlg_model_var",
                         "_dlg_key_var", "_dlg_base_var", "_update_last_var",
                         "_snooze_var"):
                try:
                    setattr(a, name, None)
                except Exception:
                    pass
        finally:
            try:
                self.grab_release()
            except Exception:
                pass
            try:
                self.destroy()
            except Exception:
                pass
