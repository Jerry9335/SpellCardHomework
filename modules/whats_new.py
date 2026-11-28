"""新版本更新说明（全屏更新绘卷）。

- 按版本号记录一次已读，升级后自动播放一次；
- 设置中心可随时手动重看；
- 只做展示与状态标记，不碰自动答题。
"""
from __future__ import annotations

import os
import tkinter as tk

from PIL import Image, ImageTk

from modules import settings

SEEN_KEY = "whats_new_seen_version"
_ASSETS_FALLBACK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

STEPS = [
    {
        "key": "marisa",
        "name": "雾雨魔理沙",
        "role": "普通的魔法使",
        "title": "自动答题修复",
        "sub": "多小问与判分",
        "quote": "魔理沙：这次我把卡住的题都拎出来重打了一遍。",
        "bullets": [
            ("多小问做完才走", "第 1/8 小问 … 第 8/8 小问，全部做完才离开当前题目；不再答完一小问就跳下一题。"),
            ("补齐已知条件", "从第 2 小问起把整题上下文交给模型；第 8 题的 lim f=5 / lim g=10 不再丢。"),
            ("不要化简", "题目要求不化简时保留 5/10，不再自动约成 1/2。"),
            ("无穷符号", "∞ 改走公式调色板插入；不再被答题平台当成普通文字。"),
            ("失败不跳题", "失败停在当前题重试；多路被截断时追加单路非流式兜底。"),
        ],
    },
    {
        "key": "patchouli",
        "name": "帕秋莉·诺蕾姬",
        "role": "不动的大图书馆",
        "title": "新版说明",
        "sub": "更新概览",
        "quote": "帕秋莉：这次的改动，我按章节整理好了。",
        "bullets": [
            ("设置中心", "六个分区：结界契约 / 读符术式 / 退治术式 / 绘卷外观 / 香火钱 / 神社登记。"
                         "所有功能都留在原来的位置上，只是重新排了卷轴。"),
            ("主窗口", "默认放大成 1660×987 的宽长方形；三栏标题、誊抄和抹去按钮一起重新排过，"
                       "高缩放比例下也不会被挤掉。"),
            ("全屏契约", "首次安装的结界契约改为全屏无边框；内容铺满宽度，不再缩在中间的小窗口里。"),
            ("全屏引路", "契约完成后的 0 毫秒直接接全屏新手引导；不会在中间闪一下主界面。"),
            ("门与账本", "单实例只开一扇门；香火钱账本可筛选、排序、导出，柱形/折线都能看。"),
        ],
    },
    {
        "key": "remilia",
        "name": "蕾米莉亚·斯卡蕾特",
        "role": "永远鲜红的幼月",
        "title": "结界契约",
        "sub": "模型与接口",
        "quote": "蕾米莉亚：契约要先看清条款，别随便签字。",
        "bullets": [
            ("六个分区", "模型与接口、读图与截图、自动答题、主题与通知、用量与费用、授权与版本。"
                         "左侧是东方名，下面一行是白话副标题。"),
            ("结界契约", "模型平台、接口地址、接口密钥、视觉模型、推理强度和附加参数都归在这一页。"),
            ("试探式神", "可以测试连接、拉取模型；主模型与视觉模型分开选，读图模型也能单独指定。"),
            ("保存反馈", "保存失败会明说，不再假装已经保存；参数格式、端口、温度会在保存前校验。"),
            ("取消与重看", "契约取消回主界面，不退出；设置里可去结界契约补，也可随时重看引路。"),
        ],
    },
    {
        "key": "sakuya",
        "name": "十六夜咲夜",
        "role": "红魔馆的女仆长",
        "title": "香火钱账本",
        "sub": "用量与费用",
        "quote": "咲夜：香火钱的账，要按秒记清楚。",
        "bullets": [
            ("筛选与排序", "日期范围、式神、搜索、表头排序；双击单条还能看输入/输出、耗时和费用。"),
            ("柱状 / 折线", "图表右上角自由切换，并记住上一次选择；下次打开还是同一种图。"),
            ("走势动画", "每次打开账本都会按走势播放一次：折线沿数据点生长，柱形从基线长起。"),
            ("导出与清空", "导出当前筛选结果；清空账本只动本机记录，不动配置和接口密钥。"),
            ("底部栏", "说明、状态、倒空赛钱箱和关上账本固定在底部，不会被表格挤掉。"),
        ],
    },
    {
        "key": "flandre",
        "name": "芙兰朵露·斯卡蕾特",
        "role": "恶魔之妹",
        "title": "门与引路",
        "sub": "单实例 / 全屏引路",
        "quote": "芙兰：门只要一扇，陪我玩就够啦。",
        "bullets": [
            ("单实例", "博麗神社只开一扇门；第二次启动会聚焦已有窗口，然后自己退场。"),
            ("全屏引路", "契约与新手引导都是全屏无边框，不再被主界面挡住，也不会闪回主界面。"),
            ("进度提示", "契约是第 X / 3 签，引路是第 X / 6 站；顶部的圆点会跟着走。"),
            ("重看引路", "设置 → 神社登记 → 重看引路，随时从第一站重看；不改变完成状态。"),
            ("契约未完成", "设置 → 结界契约补上即可；半截流程不会每次启动都自动弹。"),
        ],
    },
]


def should_show(cfg: dict, config_existed: bool) -> bool:
    """自动展示条件：已有配置、非首次安装、当前版本还没看过。"""
    if not config_existed:
        return False
    state = str(cfg.get("onboarding_state") or "").strip().lower()
    if state in ("pending", "in_progress"):
        return False
    return str(cfg.get(SEEN_KEY) or "") != str(settings.APP_VERSION)


def mark_seen(cfg: dict) -> None:
    cfg[SEEN_KEY] = str(settings.APP_VERSION)


def _avatar(assets: str, key: str, size: int):
    for folder in ("fan", ""):
        path = (os.path.join(assets, "char", folder, f"avatar_{key}.png")
                if folder else os.path.join(assets, "char", f"avatar_{key}.png"))
        if os.path.exists(path):
            try:
                return ImageTk.PhotoImage(
                    Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS))
            except Exception:
                continue
    return None


class WhatsNewWizard(tk.Toplevel):
    def __init__(self, app, on_finish=None, start_step: int = 1,
                 manual: bool = False):
        super().__init__(app.root)
        self.app = app
        self.on_finish = on_finish or (lambda _skipped=False, _manual=False: None)
        self.manual = bool(manual)
        self.assets = getattr(app, "ASSETS", _ASSETS_FALLBACK)
        self.bg = "#0f0b1b"
        self.panel = "#171224"
        self.panel2 = "#231d3a"
        self.text = "#f2eef8"
        self.muted = "#a89fc7"
        self.gold = "#e8c46a"
        self.border = "#3a3157"
        self.accent = "#d7444f"
        self.F_TITLE = getattr(app, "F_TITLE", "楷体")
        self.F_UI = getattr(app, "F_UI", "Microsoft YaHei UI")
        self.F_MONO = getattr(app, "F_MONO", ("Consolas", 10))
        self.step = max(1, min(len(STEPS), int(start_step or 1)))
        self._avatar_ref = None
        self._finished = False
        self._dots = None

        self.title("更新说明 · 符卡作业簿")
        self.configure(bg=self.bg)
        self.overrideredirect(True)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self._screen = (sw, sh)
        self.geometry(f"{sw}x{sh}+0+0")
        try:
            self.attributes("-topmost", True)
            self.grab_set()
            self.focus_force()
        except Exception:
            pass
        self.bind("<Escape>", lambda _e: self._finish(True))
        self.bind("<Right>", lambda _e: self._next())
        self.bind("<Left>", lambda _e: self._prev())
        self._build()
        self._show_step(self.step)

    # ------------------------------------------------------------------ ui
    def _build(self) -> None:
        sw, sh = self._screen
        head = tk.Frame(self, bg=self.bg)
        head.pack(fill="x", padx=48, pady=(26, 12))
        tk.Label(head, text="更新说明", bg=self.bg, fg=self.gold,
                 font=(self.F_TITLE, 30), anchor="w").pack(side="left")
        tk.Label(head, text=f"v{settings.APP_VERSION} · 新版绘卷", bg=self.bg,
                 fg=self.muted, font=(self.F_UI, 10), anchor="w").pack(
            side="left", padx=(18, 0), pady=(10, 0))
        right = tk.Frame(head, bg=self.bg)
        right.pack(side="right")
        tk.Button(right, text="关掉", command=lambda: self._finish(True),
                  bg=self.panel2, fg=self.text, activebackground="#322a52",
                  activeforeground=self.gold, relief="flat", bd=0,
                  padx=14, pady=5, cursor="hand2",
                  font=(self.F_UI, 9)).pack(side="right", padx=(14, 0))
        self.step_var = tk.StringVar()
        tk.Label(right, textvariable=self.step_var, bg=self.bg, fg=self.gold,
                 font=(self.F_UI, 11, "bold")).pack(side="left", padx=(0, 12))
        self.dots = tk.Canvas(right, width=90, height=18, bg=self.bg,
                              highlightthickness=0)
        self.dots.pack(side="left")

        body = tk.Frame(self, bg=self.bg)
        body.pack(fill="both", expand=True, padx=48, pady=(4, 10))

        # 左：角色卡
        left = tk.Frame(body, bg=self.panel, width=360)
        left.pack(side="left", fill="y", padx=(0, 26))
        left.pack_propagate(False)
        self.avatar_lbl = tk.Label(left, bg=self.panel, bd=0)
        self.avatar_lbl.pack(pady=(28, 12))
        self.name_lbl = tk.Label(left, text="", bg=self.panel, fg=self.gold,
                                 font=(self.F_UI, 19, "bold"))
        self.name_lbl.pack()
        self.role_lbl = tk.Label(left, text="", bg=self.panel, fg=self.muted,
                                 font=(self.F_UI, 9))
        self.role_lbl.pack(pady=(3, 18))
        tk.Frame(left, bg=self.border, height=1).pack(fill="x", padx=24)
        self.quote_lbl = tk.Label(left, text="", bg=self.panel, fg=self.text,
                                  font=(self.F_UI, 11), justify="left",
                                  anchor="nw", wraplength=292)
        self.quote_lbl.pack(fill="both", expand=True, padx=26, pady=20)

        # 左侧也当成目录：四页标题常驻，点击可直接跳页，顺便填满留白。
        self.left_nav = tk.Frame(left, bg=self.panel)
        self.left_nav.pack(side="bottom", fill="x", padx=24, pady=(0, 20))
        self.left_items = []
        for i, s in enumerate(STEPS):
            lbl = tk.Label(self.left_nav, text=f"{i + 1:02d}  {s['title']}",
                           bg=self.panel, fg=self.muted, anchor="w",
                           font=(self.F_UI, 9), cursor="hand2")
            lbl.pack(fill="x", pady=2)
            lbl.bind("<Button-1>", lambda _e, n=i + 1: self._show_step(n))
            self.left_items.append(lbl)

        # 右：本页内容
        right = tk.Frame(body, bg=self.bg)
        right.pack(side="left", fill="both", expand=True)
        self.title_lbl = tk.Label(right, text="", bg=self.bg, fg=self.gold,
                                  anchor="w", font=(self.F_TITLE, 30))
        self.title_lbl.pack(fill="x", pady=(8, 0))
        self.sub_lbl = tk.Label(right, text="", bg=self.bg, fg=self.text,
                                anchor="w", font=(self.F_UI, 11))
        self.sub_lbl.pack(fill="x", pady=(2, 18))
        self.cards = tk.Frame(right, bg=self.bg)
        self.cards.pack(fill="both", expand=True)

        foot = tk.Frame(self, bg=self.bg)
        foot.pack(side="bottom", fill="x", padx=48, pady=(0, 24))
        self.hint_lbl = tk.Label(foot, text="", bg=self.bg, fg=self.muted,
                                 font=(self.F_UI, 9), anchor="w")
        self.hint_lbl.pack(side="left", fill="x", expand=True)
        self.next_btn = tk.Button(
            foot, text="下一页 →", command=self._next, bg=self.gold,
            fg="#241b12", activebackground="#f0d486", activeforeground="#241b12",
            relief="flat", bd=0, padx=22, pady=8, cursor="hand2",
            font=(self.F_UI, 10, "bold"))
        self.next_btn.pack(side="right")
        self.prev_btn = tk.Button(
            foot, text="← 上一页", command=self._prev, bg=self.panel2,
            fg=self.text, activebackground="#322a52", activeforeground=self.gold,
            relief="flat", bd=0, padx=16, pady=7, cursor="hand2",
            font=(self.F_UI, 9))
        self.prev_btn.pack(side="right", padx=(0, 10))
        self.skip_btn = tk.Button(
            foot, text="跳过", command=lambda: self._finish(True),
            bg=self.bg, fg=self.muted, activebackground=self.bg,
            activeforeground=self.text, relief="flat", bd=0,
            cursor="hand2", font=(self.F_UI, 9))
        self.skip_btn.pack(side="right", padx=(0, 16))

    def _show_step(self, step: int) -> None:
        self.step = max(1, min(len(STEPS), int(step)))
        d = STEPS[self.step - 1]
        self.step_var.set(f"更新 · 第 {self.step} / {len(STEPS)} 页")
        self._draw_dots()
        av = _avatar(self.assets, d["key"], 244)
        if av is not None:
            self._avatar_ref = av
            self.avatar_lbl.configure(image=av)
        self.name_lbl.configure(text=d["name"])
        self.role_lbl.configure(text=d["role"])
        self.quote_lbl.configure(text=d["quote"])
        self.title_lbl.configure(text=d["title"])
        self.sub_lbl.configure(text=d["sub"])
        for w in self.cards.winfo_children():
            w.destroy()
        self.cards.columnconfigure(0, weight=1)
        wrap = max(520, min(1280, self.winfo_screenwidth() - 620))
        for i, (title, desc) in enumerate(d.get("bullets") or []):
            self.cards.rowconfigure(i, weight=1)
            card = tk.Frame(self.cards, bg=self.panel, highlightbackground=self.border,
                            highlightthickness=1)
            card.grid(row=i, column=0, sticky="nsew", pady=5)
            head = tk.Frame(card, bg=self.panel)
            head.pack(fill="x", padx=20, pady=(16, 4))
            tk.Label(head, text=f"{i + 1:02d}", bg=self.panel, fg=self.accent,
                     font=(self.F_MONO[0], 11, "bold")).pack(side="left")
            tk.Label(head, text=f"✦  {title}", bg=self.panel, fg=self.gold,
                     anchor="w", justify="left",
                     font=(self.F_UI, 13, "bold")).pack(side="left", padx=(12, 0))
            tk.Label(card, text=desc, bg=self.panel, fg=self.text, anchor="nw",
                     justify="left", wraplength=wrap,
                     font=(self.F_UI, 10)).pack(
                fill="both", expand=True, padx=20, pady=(0, 16))
        for i, lbl in enumerate(getattr(self, "left_items", [])):
            lbl.configure(fg=self.gold if i + 1 == self.step else self.muted)
        self.prev_btn.configure(state="normal" if self.step > 1 else "disabled",
                                fg=self.text if self.step > 1 else "#5b5470")
        self.next_btn.configure(text="开始使用" if self.step == len(STEPS) else "下一页 →")
        self.hint_lbl.configure(
            text="帕秋莉：旧版本留下的设置不会丢；这里只是把新改动指给你看。"
            if self.manual else
            "帕秋莉：新版已经展开。看完就去忙吧；设置里还能再看。")

    def _draw_dots(self) -> None:
        self.dots.delete("all")
        for i in range(len(STEPS)):
            x = 10 + i * 20
            color = self.gold if i + 1 <= self.step else self.border
            r = 5 if i + 1 == self.step else 4
            self.dots.create_oval(x - r, 9 - r, x + r, 9 + r, fill=color, outline="")

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
            self.on_finish(bool(skipped), self.manual)
        except Exception:
            pass
