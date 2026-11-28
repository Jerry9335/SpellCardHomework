"""首次安装的「结界契约」三页向导。

不负责启动流程，只负责收集 provider / API Key / 模型，并回调结果。
"""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from modules import llm, settings

# 名称必须与 llm.PROVIDER_PRESETS 完全一致
_FIRST_SIX = [
    ("DeepSeek", "灵脉最稳", "推荐 · 解题和视觉都稳", "价格低，学生党首选"),
    ("OpenAI", "通用", "模型最全", "需要自备网络环境"),
    ("硅基流动 SiliconFlow", "国内 · 直连", "国内访问快，模型多", "国内友好"),
    ("OpenRouter", "聚合", "一个 Key 走多家", "适合喜欢折腾的人"),
    ("阿里云百炼 DashScope", "国内 · 通义系", "阿里云账号即可申请", "通义系模型"),
    ("本地 Ollama", "本地", "无需 API Key", "数据不出门，电脑要够强"),
]
_MORE = [
    ("智谱 BigModel", "国内 · GLM 系", "中文表现好", "智谱开放平台"),
    ("月之暗面 Kimi", "国内 · 长文本", "长文阅读强", "月之暗面开放平台"),
    ("火山方舟 Ark", "国内 · 豆包系", "字节系模型", "火山引擎"),
    ("腾讯混元", "国内 · 混元系", "腾讯云账号即可", "腾讯混元"),
    ("本地 LM Studio", "本地", "无需 API Key", "适合离线使用"),
]

_APPLY_URLS = {
    "DeepSeek": "https://platform.deepseek.com/api_keys",
    "OpenAI": "https://platform.openai.com/api-keys",
    "硅基流动 SiliconFlow": "https://cloud.siliconflow.cn/account/ak",
    "OpenRouter": "https://openrouter.ai/keys",
    "阿里云百炼 DashScope": "https://bailian.console.aliyun.com/",
    "智谱 BigModel": "https://open.bigmodel.cn/usercenter/apikeys",
    "月之暗面 Kimi": "https://platform.moonshot.cn/console/api-keys",
    "火山方舟 Ark": "https://console.volcengine.com/ark",
    "腾讯混元": "https://console.cloud.tencent.com/hunyuan/api-key",
    "本地 Ollama": "https://ollama.com/download",
    "本地 LM Studio": "https://lmstudio.ai/",
}

_DEFAULT_MODELS = {
    "DeepSeek": ["deepseek-chat", "deepseek-reasoner"],
    "OpenAI": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"],
    "硅基流动 SiliconFlow": ["deepseek-ai/DeepSeek-V3", "Qwen/Qwen2.5-72B-Instruct"],
    "OpenRouter": ["deepseek/deepseek-chat", "openai/gpt-4o-mini"],
    "阿里云百炼 DashScope": ["qwen-plus", "qwen-turbo", "qwen-vl-plus"],
    "智谱 BigModel": ["glm-4-flash", "glm-4-plus", "glm-4v-plus"],
    "月之暗面 Kimi": ["moonshot-v1-8k", "moonshot-v1-32k"],
    "火山方舟 Ark": ["doubao-1-5-pro-32k", "doubao-1-5-vision-pro"],
    "腾讯混元": ["hunyuan-turbos-latest", "hunyuan-vision"],
    "本地 Ollama": ["llama3.2", "qwen2.5", "llava"],
    "本地 LM Studio": ["local-model"],
}

# 灵梦：旧契约上写过的名字。名录里查无此人的话，就别再拿它当第一行。
_LEGACY_DEFAULT_MODEL = "deepseek-flash"

_ASSETS_FALLBACK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

_AVATARS = {
    "yukari": "yukari",
    "eirin": "eirin",
    "keine": "keine",
}


def _avatar(assets: str, key: str, size: int):
    for name in (key, {"yukari": "yukari"}.get(key, key)):
        for folder in ("fan", ""):
            path = os.path.join(assets, "char", folder, f"avatar_{name}.png") if folder else \
                os.path.join(assets, "char", f"avatar_{name}.png")
            if os.path.exists(path):
                try:
                    return ImageTk.PhotoImage(
                        Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS))
                except Exception:
                    continue
    return None


class SetupWizard(tk.Toplevel):
    def __init__(self, app, on_done, start_step: int = 1, on_progress=None):
        super().__init__(app.root)
        self.app = app
        self.on_progress = on_progress
        self.assets = getattr(app, "ASSETS", getattr(app, "assets_dir", _ASSETS_FALLBACK))
        self.on_done = on_done
        self.cfg = app.cfg
        self.bg = "#141221"
        self.panel = "#1c1830"
        self.panel2 = "#231d3a"
        self.input = "#2a2342"
        self.text = "#f2eef8"
        self.muted = "#a89fc7"
        self.gold = "#e8c46a"
        self.border = "#3a3157"
        self.accent = "#d7444f"
        self.F_TITLE = getattr(app, "F_TITLE", "楷体")
        self.F_UI = getattr(app, "F_UI", "Microsoft YaHei UI")
        self.F_MONO = getattr(app, "F_MONO", ("Consolas", 10))

        self.step = 1
        self.provider = self._initial_provider()
        saved_base = str(self.cfg.get("base_url") or "").strip()
        # 帕秋莉：自定义的术式坐标不在书上的名录里；没点名换来源之前，就照原样留着。
        self.base_url = saved_base or self._base_for(self.provider)
        self.api_key = str(self.cfg.get("api_key") or "")
        # 安全：旧 Key 只用于“留空保留/测试”，绝不回填到输入框。
        self._has_saved_key = bool(self.api_key)
        self._clear_key = False
        self.models: list[str] = []
        self.model = str(self.cfg.get("model") or "")
        self.vision = str(self.cfg.get("vision_model") or "")
        self.api_skipped = False
        self._finished = False
        self._testing = False
        # 咲夜：探查式神的结果先放在托盘上，由主厅按节拍取，侍从不准直接摆弄陈设。
        self._test_queue: "queue.Queue[tuple]" = queue.Queue()
        self._test_gen = 0
        self._test_job = None
        self._avatar_refs: dict[str, object] = {}

        self.title("博麗神社 · 结界契约")
        self.configure(bg=self.bg)
        # 契约与新手引导都走全屏无边框，完成后直接切引导，不闪回主界面。
        self.overrideredirect(True)
        self.resizable(False, False)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")
        try:
            self.attributes("-topmost", True)
            self.grab_set()
        except Exception:
            pass
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _e: self._cancel())
        self._build_shell()
        self._show_step(max(1, min(3, int(start_step or 1))))
        try:
            self.grab_set()
        except Exception:
            pass

    # ------------------------------------------------------------------ shell
    def _build_shell(self) -> None:
        # 全屏铺开，不做居中的窄卷轴；只留四周安全边距。
        shell = tk.Frame(self, bg=self.bg)
        shell.pack(fill="both", expand=True, padx=24, pady=18)

        head = tk.Frame(shell, bg=self.bg)
        head.pack(fill="x", pady=(10, 8))
        tk.Label(head, text="博麗神社 · 结界契约", bg=self.bg, fg=self.gold,
                 font=(self.F_TITLE, 24), anchor="w").pack(side="left")
        tk.Label(head, text="～ 以灵力为引，开一条退治之路 ～", bg=self.bg, fg=self.muted,
                 font=(self.F_UI, 10), anchor="w").pack(side="left", padx=(18, 0), pady=(8, 0))
        right = tk.Frame(head, bg=self.bg)
        right.pack(side="right")
        tk.Button(right, text="先回人间", command=self._cancel,
                  bg=self.panel2, fg=self.text, activebackground="#322a52",
                  activeforeground=self.gold, relief="flat", bd=0,
                  padx=12, pady=4, cursor="hand2",
                  font=(self.F_UI, 9)).pack(side="right", padx=(12, 0))
        self.step_var = tk.StringVar(value="第 1 / 3 签")
        tk.Label(right, textvariable=self.step_var, bg=self.bg, fg=self.gold,
                 font=(self.F_UI, 10, "bold")).pack(side="left", padx=(0, 10))
        self.dots = tk.Canvas(right, width=58, height=16, bg=self.bg, highlightthickness=0)
        self.dots.pack(side="left")

        # 底部先固定，正文吃剩余高度；全屏下按钮不会被挤出窗口。
        foot = tk.Frame(shell, bg=self.bg)
        foot.pack(side="bottom", fill="x", pady=(0, 8))
        self.foot_left = tk.Frame(foot, bg=self.bg)
        self.foot_left.pack(side="left")
        self.foot_right = tk.Frame(foot, bg=self.bg)
        self.foot_right.pack(side="right")
        self.hint_var = tk.StringVar()
        tk.Label(self.foot_left, textvariable=self.hint_var, bg=self.bg, fg=self.muted,
                 font=(self.F_UI, 9), anchor="w").pack(side="left")

        body = tk.Frame(shell, bg=self.bg)
        body.pack(fill="both", expand=True, pady=(4, 8))
        self.left = tk.Frame(body, bg=self.panel, width=244, height=680)
        self.left.pack(side="left", fill="y", padx=(0, 18))
        self.left.pack_propagate(False)
        right = tk.Frame(body, bg=self.bg)
        right.pack(side="left", fill="both", expand=True)
        self._scroll = tk.Canvas(right, bg=self.bg, highlightthickness=0, bd=0)
        self._scroll.pack(side="left", fill="both", expand=True)
        style = ttk.Style(self)
        try:
            style.configure("Setup.Vertical.TScrollbar",
                            background=self.panel2, troughcolor=self.bg,
                            bordercolor=self.bg, arrowcolor=self.gold,
                            darkcolor=self.panel2, lightcolor=self.panel2,
                            relief="flat")
        except tk.TclError:
            pass
        self._scrollbar = ttk.Scrollbar(
            right, orient="vertical", command=self._scroll.yview,
            style="Setup.Vertical.TScrollbar",
        )
        self._scroll.configure(yscrollcommand=self._scrollbar.set)
        self.content = tk.Frame(self._scroll, bg=self.bg)
        self._content_window = self._scroll.create_window(
            (0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", self._sync_scroll_region)
        self._scroll.bind("<Configure>", self._sync_scroll_region)
        self.bind("<MouseWheel>", self._on_mousewheel)

    def _sync_scroll_region(self, _event=None) -> None:
        """内容比可视区高时显示滚动条；否则隐藏，避免无意义的滚动槽。"""
        try:
            self.content.update_idletasks()
            bbox = self._scroll.bbox("all")
            if not bbox:
                return
            self._scroll.configure(scrollregion=bbox)
            self._scroll.itemconfigure(self._content_window,
                                       width=max(1, self._scroll.winfo_width()))
            need = bbox[3] > self._scroll.winfo_height() + 1
            if need and not self._scrollbar.winfo_ismapped():
                self._scrollbar.pack(side="right", fill="y")
            elif not need and self._scrollbar.winfo_ismapped():
                self._scrollbar.pack_forget()
        except tk.TclError:
            pass

    def _on_mousewheel(self, event) -> None:
        try:
            bbox = self._scroll.bbox("all")
            if not bbox or bbox[3] <= self._scroll.winfo_height() + 1:
                return
            delta = -1 if event.delta > 0 else 1
            self._scroll.yview_scroll(delta * 2, "units")
        except tk.TclError:
            pass

    def _button(self, parent, text, command, primary=False, width=14):
        return tk.Button(
            parent, text=text, command=command,
            bg=self.gold if primary else self.panel2,
            fg="#241b12" if primary else self.text,
            activebackground="#f0d486" if primary else "#322a52",
            activeforeground="#241b12" if primary else "#ffffff",
            relief="flat", bd=0, padx=18, pady=8, cursor="hand2",
            font=(self.F_UI, 10, "bold" if primary else "normal"), width=width,
        )

    def _draw_dots(self) -> None:
        self.dots.delete("all")
        for i in range(3):
            x = 9 + i * 18
            color = self.gold if i + 1 <= self.step else self.border
            r = 5 if i + 1 == self.step else 4
            self.dots.create_oval(x-r, 8-r, x+r, 8+r, fill=color, outline="")

    def _set_left(self, key: str, name: str, role: str, quote: str) -> None:
        for w in self.left.winfo_children():
            w.destroy()
        av = _avatar(self.assets, key, 172)
        if av is not None:
            self._avatar_refs[key] = av
            tk.Label(self.left, image=av, bg=self.panel, bd=0).pack(pady=(30, 10))
        tk.Label(self.left, text=name, bg=self.panel, fg=self.gold,
                 font=(self.F_UI, 15, "bold")).pack()
        tk.Label(self.left, text=role, bg=self.panel, fg=self.muted,
                 font=(self.F_UI, 9)).pack(pady=(2, 14))
        tk.Label(self.left, text=quote, bg=self.panel, fg=self.text,
                 font=(self.F_UI, 10), justify="left", wraplength=196,
                 anchor="w").pack(fill="x", padx=20, pady=(0, 10))

    def _clear_content(self) -> None:
        for w in self.content.winfo_children():
            w.destroy()

    def _show_step(self, step: int) -> None:
        previous = getattr(self, "step", 1)
        self.step = max(1, min(3, step))
        if previous == 2 and self.step != 2:
            # 紫：离开这一签就把缝隙合上，别让上一趟的探查结果飘回来。
            self._cancel_test()
        self.step_var.set(f"第 {self.step} / 3 签")
        self._draw_dots()
        self._clear_content()
        try:
            if self.on_progress:
                self.on_progress(self.step)
        except Exception:
            pass
        if self.step == 1:
            self._page_provider()
        elif self.step == 2:
            self._page_key()
        else:
            self._page_models()
        self.after_idle(self._reset_scroll)

    def _reset_scroll(self) -> None:
        try:
            self._scroll.yview_moveto(0.0)
            self._sync_scroll_region()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ page 1
    def _page_provider(self) -> None:
        self._set_left("yukari", "八云紫", "境界的妖怪",
                       "「结界不是凭空开的。先选一柱灵力，神社才能替你引路。」\n\n"
                       "选错了也没关系，之后设置里还能改。")
        tk.Label(self.content, text="选择结界来源", bg=self.bg, fg=self.text,
                 font=(self.F_UI, 20, "bold"), anchor="w").pack(fill="x", pady=(8, 2))
        tk.Label(self.content, text="模型提供商 · 之后可随时更换", bg=self.bg, fg=self.muted,
                 font=(self.F_UI, 10), anchor="w").pack(fill="x", pady=(0, 12))
        grid = tk.Frame(self.content, bg=self.bg)
        grid.pack(fill="both", expand=True)
        for i in range(3):
            grid.columnconfigure(i, weight=1, uniform="prov")
        self._provider_frames = {}
        all_items = list(_FIRST_SIX)
        if getattr(self, "_more_open", False):
            all_items += list(_MORE)
        for idx, (name, tag, desc, footnote) in enumerate(all_items):
            row, col = divmod(idx, 3)
            card = tk.Frame(grid, bg=self.panel, highlightthickness=1,
                            highlightbackground=self.border, bd=0)
            card.grid(row=row, column=col, sticky="nsew", padx=(0 if col == 0 else 8, 0),
                      pady=(0 if row == 0 else 8, 0))
            top = tk.Frame(card, bg=self.panel)
            top.pack(fill="x", padx=14, pady=(12, 0))
            dot = tk.Canvas(top, width=18, height=18, bg=self.panel, highlightthickness=0)
            dot.pack(side="left")
            self._paint_radio(dot, name == self.provider)
            tk.Label(top, text=name, bg=self.panel, fg=self.text,
                     font=(self.F_UI, 10, "bold"), anchor="w").pack(side="left", padx=(6, 0))
            tk.Label(card, text=tag, bg=self.panel, fg=self.gold,
                     font=(self.F_UI, 9), anchor="w").pack(fill="x", padx=14, pady=(6, 0))
            tk.Label(card, text=desc, bg=self.panel, fg=self.muted,
                     font=(self.F_UI, 9), anchor="w").pack(fill="x", padx=14, pady=(2, 0))
            tk.Label(card, text=footnote, bg=self.panel, fg=self.muted,
                     font=(self.F_UI, 8), anchor="w").pack(fill="x", padx=14, pady=(6, 12))
            self._provider_frames[name] = card
            for w in (card, top, dot, *card.winfo_children()):
                w.bind("<Button-1>", lambda _e, n=name: self._choose_provider(n))
        if not getattr(self, "_more_open", False):
            more = tk.Button(self.content, text="更多提供商 ▾", command=self._toggle_more,
                             bg=self.bg, fg=self.gold, activebackground=self.panel2,
                             activeforeground=self.gold, relief="flat", bd=0,
                             cursor="hand2", font=(self.F_UI, 9, "underline"))
            more.pack(anchor="w", pady=(10, 0))
        else:
            tk.Label(self.content, text="点击卡片切换来源；选好后进入下一步。", bg=self.bg,
                     fg=self.muted, font=(self.F_UI, 9), anchor="w").pack(fill="x", pady=(10, 0))
        self._paint_provider_selection()
        # 「之后再配」只是不填 Key，不是退出契约；仍然进入下一签。
        self._render_foot(primary="就借这家 →", on_primary=self._to_key,
                          secondary="之后再配", on_secondary=self._to_key)
        if getattr(self, "_more_open", False):
            self.hint_var.set("更多提供商已展开——用滚轮查看全部，选好后进入下一步。")
        else:
            self.hint_var.set("本地来源不需要咒语：只要 Ollama / LM Studio 已经开着，就能直接借灵力。")

    def _paint_radio(self, canvas: tk.Canvas, selected: bool) -> None:
        canvas.delete("all")
        canvas.create_oval(2, 2, 16, 16, outline=self.gold if selected else self.border, width=1)
        if selected:
            canvas.create_oval(6, 6, 12, 12, fill=self.gold, outline="")

    def _paint_provider_selection(self) -> None:
        for name, frame in getattr(self, "_provider_frames", {}).items():
            frame.configure(highlightbackground=self.gold if name == self.provider else self.border,
                            highlightthickness=2 if name == self.provider else 1)
            for child in frame.winfo_children():
                if isinstance(child, tk.Frame):
                    for c in child.winfo_children():
                        if isinstance(c, tk.Canvas):
                            self._paint_radio(c, name == self.provider)

    def _choose_provider(self, name: str) -> None:
        self.provider = name
        self.base_url = self._base_for(name)
        # 魔理沙：换了灵力来源，旧式神就不算数了，从这一家的名录头一位重挑。
        self.models = []
        self.model = self._default_model_for(name)
        self._paint_provider_selection()

    def _toggle_more(self) -> None:
        self._more_open = True
        self._show_step(1)

    def _initial_provider(self) -> str:
        base = str(self.cfg.get("base_url") or "").rstrip("/")
        for name, preset in llm.PROVIDER_PRESETS:
            if preset.rstrip("/") == base:
                return name
        return "DeepSeek"

    @staticmethod
    def _base_for(name: str) -> str:
        for n, base in llm.PROVIDER_PRESETS:
            if n == name:
                return base
        return "https://api.deepseek.com/v1"

    @staticmethod
    def _default_model_for(name: str) -> str:
        """慧音：每一家的名录第一行，就是这一家的正统式神。"""
        return (_DEFAULT_MODELS.get(name) or [""])[0]

    # ------------------------------------------------------------------ page 2
    def _page_key(self) -> None:
        self._set_left("eirin", "八意永琳", "月之头脑",
                       "「把 API Key 交给我。我会把它封进符卡里，只留在你电脑上，"
                       "不写日志，也不让旁人看见。」\n\n我会替你试一试，接不通就换一条路。")
        tk.Label(self.content, text="灵力契约", bg=self.bg, fg=self.text,
                 font=(self.F_UI, 20, "bold"), anchor="w").pack(fill="x", pady=(8, 2))
        tk.Label(self.content, text=f"{self.provider} · API Key", bg=self.bg, fg=self.gold,
                 font=(self.F_UI, 10, "bold"), anchor="w").pack(fill="x", pady=(0, 14))

        row = tk.Frame(self.content, bg=self.bg)
        row.pack(fill="x")
        self.key_entry = ttk.Entry(row, show="•", font=(self.F_UI, 10))
        # 旧密钥不显示；留空表示继续使用已封存的那一道。
        self.key_entry.pack(side="left", fill="x", expand=True, ipady=4)
        self._button(row, "粘贴", self._paste_key, width=6).pack(side="left", padx=(8, 0))
        if self._has_saved_key:
            self._button(row, "清除已存", self._clear_saved_key, width=8).pack(
                side="left", padx=(6, 0))

        self.key_state = tk.StringVar(value=(
            "已封存一道灵力（不在界面显示）。留空保留；输入新密钥会替换，也可点「清除已存」。"
            if self._has_saved_key
            else "尚未测试——建议先测一下，免得退治到一半灵力断了。"))
        self.key_state_lbl = tk.Label(self.content, textvariable=self.key_state,
                                      bg=self.panel, fg=self.muted, font=(self.F_UI, 9),
                                      anchor="w", justify="left", wraplength=650,
                                      padx=12, pady=8)
        self.key_state_lbl.pack(fill="x", pady=(12, 10))

        actions = tk.Frame(self.content, bg=self.bg)
        actions.pack(fill="x")
        self.test_btn = self._button(actions, "测试连通性", self._test_key, width=12)
        self.test_btn.pack(side="left")
        self._button(actions, f"打开 {self.provider} 申请页", self._open_apply, width=22).pack(
            side="left", padx=(10, 0))

        tk.Label(self.content,
                 text="没有 Key？可以先跳过，之后在「设置 → 灵梦的通信术式」里补；不影响先看新手引导。",
                 bg=self.bg, fg=self.muted, font=(self.F_UI, 9), anchor="w",
                 justify="left", wraplength=650).pack(fill="x", pady=(16, 8))
        steps = tk.Frame(self.content, bg=self.bg)
        steps.pack(fill="x", pady=(4, 0))
        for i, (title, desc) in enumerate((("1. 创建 Key", "在浏览器完成"), ("2. 复制回来", "粘贴到上方"), ("3. 测试连通", "绿了再走"))):
            box = tk.Frame(steps, bg=self.panel2, padx=12, pady=8)
            box.pack(side="left", fill="x", expand=True, padx=(0 if i == 0 else 8, 0))
            tk.Label(box, text=title, bg=self.panel2, fg=self.gold,
                     font=(self.F_UI, 10, "bold"), anchor="w").pack(fill="x")
            tk.Label(box, text=desc, bg=self.panel2, fg=self.muted,
                     font=(self.F_UI, 9), anchor="w").pack(fill="x")
        self._render_foot(primary="下一步 →", on_primary=self._to_models,
                          secondary="先跳过这笔", on_secondary=lambda: self._to_models(skip_key=True))
        self.hint_var.set("API Key 会用 Windows DPAPI 加密，只保存在本机。")

    def _paste_key(self) -> None:
        try:
            txt = self.clipboard_get().strip()
        except Exception:
            txt = ""
        if txt:
            self.key_entry.delete(0, "end")
            self.key_entry.insert(0, txt)
            self._clear_key = False
            self.key_state.set("已从剪贴板贴入，记得测试一下。")
            self.key_state_lbl.configure(fg=self.muted)

    def _clear_saved_key(self) -> None:
        self._clear_key = True
        self.api_key = ""
        self._has_saved_key = False
        self.key_entry.delete(0, "end")
        self.key_state.set("已清除旧密钥；如果不需要 Key，可以直接跳过这一步。")
        self.key_state_lbl.configure(fg=self.C["warn"] if hasattr(self, "C") else "#f2a65a")

    def _current_key(self) -> str:
        try:
            entered = self.key_entry.get().strip()
        except Exception:
            entered = ""
        if entered:
            return entered
        if self._clear_key:
            return ""
        return self.api_key if self._has_saved_key else ""

    def _is_local(self) -> bool:
        return self.provider.startswith("本地")

    def _test_key(self) -> None:
        if self._testing:
            return
        key = self._current_key()
        if not self._is_local() and not key:
            self._set_key_state("还没有填通行密钥。可以填完再测，或者先跳过。", "#f2a65a")
            return
        self._testing = True
        self._test_gen += 1
        gen = self._test_gen
        try:
            self.test_btn.configure(state="disabled")
        except Exception:
            pass
        self._set_key_state("灵力探查中……", self.muted)
        base = self.base_url

        def work():
            # 咲夜：侍从只把托盘放下，不碰大厅里的任何陈设；取用由主厅按节拍来。
            try:
                models = llm.list_models(base, key)
            except Exception as exc:
                self._test_queue.put((gen, "err", str(exc)))
                return
            self._test_queue.put((gen, "ok", list(models or [])))

        threading.Thread(target=work, daemon=True).start()
        try:
            self._test_job = self.after(80, lambda g=gen: self._poll_test_result(g))
        except Exception:
            self._test_job = None
            self._testing = False

    def _poll_test_result(self, gen: int) -> None:
        """咲夜：按拍子取托盘。节拍对不上，就把旧结果留在缝隙里。"""
        self._test_job = None
        if self._finished or gen != self._test_gen:
            return
        try:
            item = self._test_queue.get_nowait()
        except queue.Empty:
            self._schedule_test_poll(gen)
            return
        try:
            got_gen, kind, payload = item
        except (TypeError, ValueError):
            self._schedule_test_poll(gen)
            return
        if got_gen != gen:
            self._schedule_test_poll(gen)
            return
        if kind == "ok":
            self._test_done(list(payload or []), "")
        else:
            self._test_done([], str(payload or ""))

    def _schedule_test_poll(self, gen: int) -> None:
        try:
            self._test_job = self.after(80, lambda g=gen: self._poll_test_result(g))
        except Exception:
            self._test_job = None

    def _cancel_test(self) -> None:
        """紫：这条缝隙先合上；旧结果再飘回来，也不认。"""
        self._test_gen += 1
        self._testing = False
        job = self._test_job
        self._test_job = None
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass

    def _set_key_state(self, text: str, color: str) -> None:
        """慧音：写下批注前先看看这页还在不在，别往烧掉的纸上写字。"""
        try:
            if not self.winfo_exists():
                return
            label = getattr(self, "key_state_lbl", None)
            if label is None or not label.winfo_exists():
                return
            self.key_state.set(text)
            label.configure(fg=color)
        except Exception:
            pass

    def _test_done(self, models: list, err: str) -> None:
        self._testing = False
        self._test_job = None
        button = getattr(self, "test_btn", None)
        try:
            if button is not None and button.winfo_exists():
                button.configure(state="normal")
        except Exception:
            pass
        if err:
            self._set_key_state(
                f"没接上：{err[:220]}\n可以再试，或者先跳过，之后在设置里补。", "#ff6b6b")
        else:
            self.models = list(models or [])
            if self.models:
                self._set_key_state(
                    f"连通了。灵力很稳（看到 {len(self.models)} 个可用式神）。", "#7ed6a5")
            else:
                self._set_key_state("连通了。灵力很稳。", "#7ed6a5")

    def _open_apply(self) -> None:
        try:
            import webbrowser
            webbrowser.open(_APPLY_URLS.get(self.provider, "https://platform.deepseek.com/api_keys"))
        except Exception:
            pass

    def _to_key(self) -> None:
        self._show_step(2)

    def _to_models(self, skip_key: bool = False) -> None:
        if self.step != 2:
            self._show_step(3)
            return
        key = self._current_key()
        self.api_key = key
        if skip_key or (not key and not self._is_local()):
            self.api_skipped = True
        self._show_step(3)

    # ------------------------------------------------------------------ page 3
    def _candidate_models(self) -> list[str]:
        # 帕秋莉：名录以书上的定式和实测到的为准，旧名字不强行塞到第一行。
        vals: list[str] = []
        for model in list(self.models) + list(_DEFAULT_MODELS.get(self.provider, [])):
            if model and model not in vals:
                vals.append(model)
        return vals

    def _page_models(self) -> None:
        self._set_left("keine", "上白泽慧音", "知识的半兽",
                       "「主模型负责解题与翻译；视觉模型负责看截图、图形和表格。"
                       "选好了，才能因材施教。」\n\n视觉模型可以留空，只是图形题会更多留给你。")
        tk.Label(self.content, text="式神择定", bg=self.bg, fg=self.text,
                 font=(self.F_UI, 20, "bold"), anchor="w").pack(fill="x", pady=(8, 2))
        tk.Label(self.content, text="主模型与视觉模型可以不同；之后在设置里也能改。",
                 bg=self.bg, fg=self.muted, font=(self.F_UI, 10), anchor="w").pack(
            fill="x", pady=(0, 18))

        values = self._candidate_models()
        if not self.model or (self.model == _LEGACY_DEFAULT_MODEL
                              and self.model not in values):
            # 灵梦：旧契约上的名字在名录里查无此人，就照这一家的头一位重写。
            self.model = values[0] if values else ""
        box1 = tk.Frame(self.content, bg=self.panel, padx=16, pady=14)
        box1.pack(fill="x", pady=(0, 12))
        tk.Label(box1, text="主模型", bg=self.panel, fg=self.gold,
                 font=(self.F_UI, 11, "bold"), anchor="w").pack(fill="x")
        tk.Label(box1, text="负责解题、翻译、长文", bg=self.panel, fg=self.muted,
                 font=(self.F_UI, 9), anchor="w").pack(fill="x", pady=(2, 8))
        self.model_var = tk.StringVar(value=self.model)
        self.model_box = ttk.Combobox(box1, textvariable=self.model_var, values=values,
                                      font=(self.F_UI, 10))
        self.model_box.pack(fill="x", ipady=3)

        box2 = tk.Frame(self.content, bg=self.panel, padx=16, pady=14)
        box2.pack(fill="x", pady=(0, 12))
        tk.Label(box2, text="视觉模型", bg=self.panel, fg=self.gold,
                 font=(self.F_UI, 11, "bold"), anchor="w").pack(fill="x")
        tk.Label(box2, text="负责看截图 / 图形 / 表格", bg=self.panel, fg=self.muted,
                 font=(self.F_UI, 9), anchor="w").pack(fill="x", pady=(2, 8))
        self.vision_var = tk.StringVar(
            value=self.vision if self.vision else "（不启用视觉模型）")
        self.vision_box = ttk.Combobox(
            box2, textvariable=self.vision_var,
            values=["（不启用视觉模型）"] + values, font=(self.F_UI, 10))
        self.vision_box.pack(fill="x", ipady=3)
        tk.Label(box2, text="可留空（不启用视觉）；图形题会转为人工确认。",
                 bg=self.panel, fg=self.muted, font=(self.F_UI, 9), anchor="w").pack(
            fill="x", pady=(6, 0))

        line = tk.Frame(self.content, bg=self.panel2, padx=14, pady=10)
        line.pack(fill="x")
        tk.Label(line, text="可选择默认模型，也可以直接输入模型名；稍后都能改。",
                 bg=self.panel2, fg=self.muted, font=(self.F_UI, 9), anchor="w").pack(
            fill="x")
        self._render_foot(primary="完成契约 →", on_primary=self._finish,
                          secondary="之后在设置里调", on_secondary=self._finish)
        self.hint_var.set("完成后进入新手引导；跳过引导也不会丢失已填内容。")

    # ------------------------------------------------------------------ footer
    def _render_foot(self, primary: str, on_primary, secondary: str, on_secondary) -> None:
        for w in self.foot_left.winfo_children():
            w.destroy()
        tk.Label(self.foot_left, textvariable=self.hint_var, bg=self.bg, fg=self.muted,
                 font=(self.F_UI, 9), anchor="w").pack(side="left")
        for w in self.foot_right.winfo_children():
            w.destroy()
        self._button(self.foot_right, secondary, on_secondary, width=14).pack(
            side="left", padx=(0, 10))
        self._button(self.foot_right, primary, on_primary, primary=True, width=14).pack(
            side="left")

    # ------------------------------------------------------------------ finish
    def _collect_models(self) -> tuple[str, str]:
        try:
            main = self.model_var.get().strip()
        except Exception:
            main = self.model
        try:
            vis = self.vision_var.get().strip()
        except Exception:
            vis = self.vision
        if vis == "（不启用视觉模型）":
            vis = ""
        return main, vis

    def _finish(self, skip_setup: bool = False) -> None:
        if self._finished:
            return
        self._finished = True
        self._cancel_test()
        if skip_setup:
            self.api_skipped = True
            result = {"skipped": True, "api_skipped": True}
        else:
            main, vis = self._collect_models()
            if not main:
                main = self._default_model_for(self.provider)
            result = {
                "skipped": False,
                "api_skipped": bool(self.api_skipped or not self.api_key),
                "provider": self.provider,
                "base_url": self.base_url,
                "api_key": self.api_key,
                "model": main,
                "vision_model": vis,
            }
        self._save_result(result)
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        try:
            self.on_done(result)
        except Exception:
            pass

    def _save_result(self, result: dict) -> None:
        try:
            if not result.get("skipped"):
                self.cfg["base_url"] = result.get("base_url") or self.base_url
                self.cfg["api_key"] = result.get("api_key", "")
                self.cfg["model"] = result.get("model") or self.cfg.get("model") or "deepseek-chat"
                if "vision_model" in result:
                    self.cfg["vision_model"] = result.get("vision_model", "")
                # 慧音：读图坐标和读图密钥是另一册笔记；这次契约没问，就原样留着。
                if "vision_base_url" in result:
                    self.cfg["vision_base_url"] = result.get("vision_base_url") or ""
                if "vision_api_key" in result:
                    self.cfg["vision_api_key"] = result.get("vision_api_key") or ""
                self.cfg["save_key"] = True
            self.app.cfg.update(self.cfg)
            settings.save(self.cfg)
        except Exception:
            pass

    def _cancel(self) -> None:
        if self._finished:
            return
        if not messagebox.askyesno(
                "结界契约",
                "现在离开，契约会先留着，不会关掉主程序。\n"
                "之后可在「设置 → 神社登记 → 继续契约」里续。\n"
                "要回人间吗？", parent=self):
            return
        self._finished = True
        self._cancel_test()
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        try:
            self.on_done({"cancelled": True})
        except Exception:
            pass
