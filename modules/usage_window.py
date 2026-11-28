"""博麗神社 · 香火钱账本（用量与费用）。

纯 UI + usage.py 数据函数；不碰自动答题。
"""
from __future__ import annotations

import datetime as dt
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import ImageTk

from modules import usage


class UsageWindow(tk.Toplevel):
    RANGES = ("今日", "近 7 天", "近 30 天", "全部")

    def __init__(self, app, palette: dict):
        super().__init__(app.root)
        self.app = app
        self.C = palette
        self.F_UI = app.F_UI
        self.F_TITLE = app.F_TITLE
        self.F_JP = app.F_JP
        self.F_MONO = app.F_MONO
        self._closed = False
        self._all_rows: list[dict] = []
        self._rows: list[dict] = []
        self._sort_key = "t"
        self._sort_rev = True
        self._chart_w = 0
        self._chart_shown = None
        self._chart_anim_job = None
        self._initial_anim_job = None
        self._initial_pending = True
        self._search_job = None
        self._model_values: list[str] = ["全部"]

        saved_kind = str(app.cfg.get("usage_chart_kind") or "bar").lower()
        self._range_var = tk.StringVar(value="近 30 天")
        self._model_var = tk.StringVar(value="全部")
        self._chart_kind = tk.StringVar(
            value="折线图" if saved_kind == "line" else "柱状图")
        self._search_var = tk.StringVar()
        self._status_var = tk.StringVar(value="灵梦：账本翻开了。")
        self._today_var = tk.StringVar()
        self._picked_var = tk.StringVar()
        self._total_var = tk.StringVar()
        self._calls_var = tk.StringVar()

        self._build()
        self.refresh_data()
        self.app._usage_win = self
        # 每次打开账本都播放一次走势动画，而不是只有切换图表时才有。
        self._initial_anim_job = self.after(220, self._start_initial_chart_anim)

    # ------------------------------------------------------------------ ui
    def _build(self) -> None:
        C = self.C
        self.title("博麗神社 · 香火钱账本")
        self.configure(bg=C["bg"])
        self.transient(self.app.root)
        self.resizable(True, True)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        min_w = max(820, min(1020, sw - 80))
        min_h = max(620, min(820, sh - 90))
        self.minsize(min_w, min_h)
        w = max(min_w, min(1240, sw - 80))
        h = max(min_h, min(1000, sh - 90))
        x = max(20, min(self.app.root.winfo_rootx() + 40, sw - w - 20))
        y = max(20, min(self.app.root.winfo_rooty() + 20, sh - h - 20))
        self.geometry(f"{w}x{h}+{x}+{y}")

        head = tk.Frame(self, bg=C["bg"])
        head.pack(fill="x", padx=24, pady=(16, 4))
        tk.Label(head, text="香火钱 · 赛钱箱", bg=C["bg"], fg=C["gold"],
                 font=(self.F_TITLE, 22)).pack(anchor="w")
        tk.Label(head, text="用量与费用", bg=C["bg"], fg=C["text"],
                 font=(self.F_UI, 10)).pack(anchor="w", pady=(1, 0))
        tk.Label(head, text="灵梦：香火钱要算清楚，别到时候又装傻。",
                 bg=C["bg"], fg=C["muted"], font=(self.F_UI, 9)).pack(anchor="w", pady=(2, 0))
        tk.Frame(self, bg=C["border"], height=1).pack(fill="x", padx=24, pady=(8, 0))

        cards = tk.Frame(self, bg=C["bg"])
        cards.pack(fill="x", padx=24, pady=(10, 0))
        for title, var, note in (
            ("今日香火", self._today_var, "今天花掉多少（估算）"),
            ("所选区间", self._picked_var, "当前筛选范围"),
            ("累计香火", self._total_var, "总共花掉多少（估算）"),
            ("累计抽符", self._calls_var, "一共调用了几次 API"),
        ):
            card = tk.Frame(cards, bg=C["panel"], highlightbackground=C["border"],
                            highlightthickness=1)
            card.pack(side="left", expand=True, fill="x", padx=(0, 8))
            tk.Label(card, text=title, bg=C["panel"], fg=C["muted"],
                     font=(self.F_UI, 9)).pack(anchor="w", padx=12, pady=(8, 0))
            tk.Label(card, textvariable=var, bg=C["panel"], fg=C["gold"],
                     font=(self.F_MONO[0], 15, "bold")).pack(anchor="w", padx=12)
            tk.Label(card, text=note, bg=C["panel"], fg=C["muted"],
                     font=(self.F_UI, 8)).pack(anchor="w", padx=12, pady=(0, 8))

        filters = tk.Frame(self, bg=C["bg"])
        filters.pack(fill="x", padx=24, pady=(10, 6))
        tk.Label(filters, text="范围", bg=C["bg"], fg=C["muted"],
                 font=(self.F_UI, 9)).pack(side="left")
        rng = ttk.Combobox(filters, textvariable=self._range_var,
                           values=list(self.RANGES), state="readonly", width=10)
        rng.pack(side="left", padx=(4, 14))
        rng.bind("<<ComboboxSelected>>", lambda _e: self._refresh_view())
        tk.Label(filters, text="式神", bg=C["bg"], fg=C["muted"],
                 font=(self.F_UI, 9)).pack(side="left")
        self._model_box = ttk.Combobox(filters, textvariable=self._model_var,
                                       values=["全部"], state="readonly", width=22)
        self._model_box.pack(side="left", padx=(4, 14))
        self._model_box.bind("<<ComboboxSelected>>", lambda _e: self._refresh_view())
        tk.Label(filters, text="搜索", bg=C["bg"], fg=C["muted"],
                 font=(self.F_UI, 9)).pack(side="left")
        ent = ttk.Entry(filters, textvariable=self._search_var, width=22)
        ent.pack(side="left", padx=(4, 14))
        self._search_var.trace_add("write", lambda *_a: self._schedule_search())
        tk.Button(filters, text="整理账本", command=self.refresh_data,
                  bg=C["panel2"], fg=C["text"], activebackground=C["accent_dark"],
                  activeforeground="#ffffff", relief="flat", bd=0,
                  padx=10, pady=2, cursor="hand2",
                  font=(self.F_UI, 9)).pack(side="left")
        tk.Button(filters, text="抄录一份", command=self._export,
                  bg=C["panel2"], fg=C["text"], activebackground=C["accent_dark"],
                  activeforeground="#ffffff", relief="flat", bd=0,
                  padx=10, pady=2, cursor="hand2",
                  font=(self.F_UI, 9)).pack(side="left", padx=(8, 0))

        chart_box = tk.Frame(self, bg=C["panel"], highlightbackground=C["border"],
                             highlightthickness=1)
        chart_box.pack(fill="x", padx=24, pady=(2, 8))
        chart_head = tk.Frame(chart_box, bg=C["panel"])
        chart_head.pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(chart_head, text="香火钱走势（按天）", bg=C["panel"], fg=C["gold"],
                 font=(self.F_UI, 10, "bold")).pack(side="left")
        kind = ttk.Combobox(chart_head, textvariable=self._chart_kind,
                            values=["柱状图", "折线图"], state="readonly", width=8)
        kind.pack(side="right")
        kind.bind("<<ComboboxSelected>>", self._on_chart_kind)
        self._chart_lbl = tk.Label(chart_box, bg=C["panel"], bd=0)
        self._chart_lbl.pack(anchor="w", padx=12, pady=(2, 8))

        table_box = tk.Frame(self, bg=C["panel"], highlightbackground=C["border"],
                             highlightthickness=1)
        table_box.pack(fill="both", expand=True, padx=24, pady=(0, 6))
        tk.Label(table_box, text="最近的法术记录（每次调用）", bg=C["panel"],
                 fg=C["gold"], font=(self.F_UI, 10, "bold")).pack(
            anchor="w", padx=12, pady=(8, 4))

        wrap = tk.Frame(table_box, bg=C["panel"])
        wrap.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        style = ttk.Style(self)
        style.configure("Usage.Treeview", background=C["panel2"],
                        fieldbackground=C["panel2"], foreground=C["text"],
                        rowheight=25, borderwidth=0)
        style.configure("Usage.Treeview.Heading", background=C["panel"],
                        foreground=C["muted"], padding=(6, 4))
        style.map("Usage.Treeview",
                  background=[("selected", C["accent"])],
                  foreground=[("selected", "#ffffff")])
        cols = ("time", "model", "tokens", "sec", "cost")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", height=9,
                                 style="Usage.Treeview")
        heads = {"time": ("时间", 160), "model": ("式神", 220),
                 "tokens": ("灵力", 110), "sec": ("耗时", 90), "cost": ("香火钱", 110)}
        for c in cols:
            text, width = heads[c]
            self.tree.heading(c, text=text,
                              command=lambda k=c: self._sort_by(k))
            self.tree.column(c, width=width, anchor="w" if c == "model" else "e")
        self.tree.column("time", anchor="w")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(wrap, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)
        self.tree.bind("<Double-1>", self._show_detail)

        bottom = tk.Frame(self, bg=C["bg"])
        bottom.pack(side="bottom", fill="x")
        foot = tk.Frame(bottom, bg=C["bg"])
        foot.pack(fill="x", padx=24, pady=(0, 8))
        tk.Label(foot, text="灵力 = tokens；香火钱按参考单价估算，实际以平台账单为准。",
                 bg=C["bg"], fg=C["muted"], anchor="w",
                 font=(self.F_UI, 8)).pack(anchor="w", pady=(0, 2))
        row = tk.Frame(foot, bg=C["bg"])
        row.pack(fill="x")
        # 先固定右侧按钮，再让状态文字占用剩余宽度；长状态不会把按钮挤掉。
        tk.Button(row, text="关上账本", command=self._close, bg=C["accent"],
                  fg="#ffffff", activebackground=C["accent_dark"],
                  activeforeground="#ffffff", relief="flat", bd=0,
                  padx=18, pady=5, cursor="hand2",
                  font=(self.F_UI, 10, "bold")).pack(side="right")
        tk.Button(row, text="倒空赛钱箱", command=self._clear,
                  bg=C["panel2"], fg=C["err"], activebackground=C["accent_dark"],
                  activeforeground="#ffffff", relief="flat", bd=0,
                  padx=12, pady=4, cursor="hand2",
                  font=(self.F_UI, 9)).pack(side="right", padx=(8, 0))
        tk.Label(row, textvariable=self._status_var, bg=C["bg"], fg=C["muted"],
                 anchor="w", font=(self.F_UI, 9)).pack(side="left", fill="x", expand=True)

        # pack 顺序：底部栏先占住底部，再让表格吃剩余高度；
        # 否则 Treeview 的 expand 会把“倒空/关闭/说明”顶到窗口外。
        table_box.pack_forget()
        bottom.pack_forget()
        bottom.pack(side="bottom", fill="x")
        table_box.pack(fill="both", expand=True, padx=24, pady=(0, 6))

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _e: self._close())
        self.bind("<Configure>", self._on_resize)

    # --------------------------------------------------------------- data
    def refresh_data(self) -> None:
        try:
            self._all_rows = usage.load()
        except Exception as e:
            self._all_rows = []
            self._status_var.set(f"灵梦：账本打不开——{e}")
        models = sorted({str(r.get("model") or "?") for r in self._all_rows})
        self._model_values = ["全部"] + models
        cur = self._model_var.get()
        self._model_box.configure(values=self._model_values)
        if cur not in self._model_values:
            self._model_var.set("全部")
        self._refresh_view()

    def _range_days(self) -> int | None:
        r = self._range_var.get()
        return {"今日": 1, "近 7 天": 7, "近 30 天": 30, "全部": None}.get(r, 30)

    def _day(self, ts: int) -> dt.date:
        return dt.datetime.fromtimestamp(int(ts or 0)).date()

    def _filtered(self) -> list[dict]:
        days = self._range_days()
        today = dt.date.today()
        q = self._search_var.get().strip().lower()
        model = self._model_var.get()
        out = []
        for r in self._all_rows:
            try:
                d = self._day(r.get("t", 0))
            except Exception:
                continue
            if days is not None and d < today - dt.timedelta(days=days - 1):
                continue
            if model != "全部" and str(r.get("model") or "?") != model:
                continue
            if q:
                hay = (str(r.get("model") or "") + " " + d.isoformat()).lower()
                if q not in hay:
                    continue
            out.append(r)
        key = self._sort_key
        if key == "time":
            key = "t"
        out.sort(key=lambda r: r.get(key, 0), reverse=self._sort_rev)
        return out

    def _refresh_view(self) -> None:
        self._rows = self._filtered()
        all_today = sum(1 for r in self._all_rows
                        if self._day(r.get("t", 0)) == dt.date.today())
        today_cost = sum(float(r.get("cost") or 0) for r in self._all_rows
                         if self._day(r.get("t", 0)) == dt.date.today())
        picked_cost = sum(float(r.get("cost") or 0) for r in self._rows)
        all_cost = sum(float(r.get("cost") or 0) for r in self._all_rows)
        self._today_var.set(f"{self._fmt_cost(today_cost)} · {all_today} 抽")
        self._picked_var.set(f"{self._fmt_cost(picked_cost)} · {len(self._rows)} 抽")
        self._total_var.set(self._fmt_cost(all_cost))
        self._calls_var.set(f"{len(self._all_rows)} 抽")
        self._refresh_tree()
        if not self._initial_pending:
            self._draw_chart()
        self._status_var.set(
            f"灵梦：账面 {len(self._rows)} 条"
            + (f"（全部 {len(self._all_rows)} 条）" if len(self._rows) != len(self._all_rows) else "")
            + "。")

    def _refresh_tree(self) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for r in self._rows[:300]:
            ts = dt.datetime.fromtimestamp(int(r.get("t", 0))).strftime("%m-%d %H:%M")
            self.tree.insert("", "end", values=(
                ts, str(r.get("model") or "?")[:28],
                self._fmt_tokens(r.get("tokens", 0)),
                f"{float(r.get('sec') or 0):.1f}s",
                self._fmt_cost(r.get("cost", 0))))
        if not self._rows:
            self.tree.insert("", "end", values=("赛钱箱空得能跑老鼠。", "", "", "", ""))

    def _draw_chart(self, animate: bool = False) -> None:
        days = self._range_days() or 30
        days = max(7, min(days, 30))
        start = dt.date.today() - dt.timedelta(days=days - 1)
        buckets: dict[str, list[float]] = {}
        for r in self._rows:
            d = self._day(r.get("t", 0)).isoformat()
            b = buckets.setdefault(d, [0.0, 0])
            b[0] += float(r.get("cost") or 0)
            b[1] += int(r.get("tokens") or 0)
        by_day = []
        for i in range(days):
            d = (start + dt.timedelta(days=i)).isoformat()
            c, t = buckets.get(d, [0.0, 0])
            by_day.append((d, c, t))
        width = max(640, min(1080, self.winfo_width() - 90))
        self._chart_w = width
        try:
            kind = "line" if self._chart_kind.get() == "折线图" else "bar"
            if animate:
                if kind == "line":
                    self._animate_line(by_day, width, 150)
                else:
                    self._animate_bar(by_day, width, 150)
                return
            img = usage.render_chart(by_day, width=width, height=150, kind=kind)
            self._show_chart(img)
        except Exception as e:
            self._chart_lbl.configure(text=f"图表画不出来：{e}", fg=self.C["err"],
                                      bg=self.C["panel"])

    def _show_chart(self, img) -> None:
        if self._chart_anim_job:
            try:
                self.after_cancel(self._chart_anim_job)
            except Exception:
                pass
            self._chart_anim_job = None
        photo = ImageTk.PhotoImage(img)
        self._chart_lbl.configure(image=photo, text="")
        self._chart_lbl.image = photo
        self._chart_shown = img

    def _animate_line(self, by_day, width: int, height: int,
                      frames: int = 22) -> None:
        """折线按走势从左到右生长；不是整图淡入。"""
        if self._closed:
            return
        if self._chart_anim_job:
            try:
                self.after_cancel(self._chart_anim_job)
            except Exception:
                pass
            self._chart_anim_job = None

        def step(i: int) -> None:
            if self._closed:
                return
            t = min(1.0, i / max(1, frames))
            eased = 1 - (1 - t) ** 3  # ease-out：先画得快，末段慢下来
            frame = usage.render_chart(
                by_day, width=width, height=height, kind="line",
                progress=max(0.01, eased))
            photo = ImageTk.PhotoImage(frame)
            self._chart_lbl.configure(image=photo, text="")
            self._chart_lbl.image = photo
            self._chart_shown = frame
            if i < frames:
                self._chart_anim_job = self.after(28, lambda: step(i + 1))
            else:
                self._chart_shown = frame
                self._chart_anim_job = None

        step(1)

    def _animate_bar(self, by_day, width: int, height: int,
                     frames: int = 22) -> None:
        """柱子从基线各自长起来，带一点左→右错峰。"""
        if self._closed:
            return
        if self._chart_anim_job:
            try:
                self.after_cancel(self._chart_anim_job)
            except Exception:
                pass
            self._chart_anim_job = None

        def step(i: int) -> None:
            if self._closed:
                return
            t = min(1.0, i / max(1, frames))
            eased = 1 - (1 - t) ** 3
            frame = usage.render_chart(
                by_day, width=width, height=height, kind="bar",
                progress=max(0.01, eased))
            photo = ImageTk.PhotoImage(frame)
            self._chart_lbl.configure(image=photo, text="")
            self._chart_lbl.image = photo
            self._chart_shown = frame
            if i < frames:
                self._chart_anim_job = self.after(28, lambda: step(i + 1))
            else:
                self._chart_shown = frame
                self._chart_anim_job = None

        step(1)

    def _on_chart_kind(self, _ev=None) -> None:
        if self._initial_anim_job:
            try:
                self.after_cancel(self._initial_anim_job)
            except Exception:
                pass
            self._initial_anim_job = None
        self._initial_pending = False
        self.app.cfg["usage_chart_kind"] = (
            "line" if self._chart_kind.get() == "折线图" else "bar")
        self._draw_chart(animate=True)

    def _start_initial_chart_anim(self) -> None:
        if self._closed:
            return
        self._initial_anim_job = None
        self._initial_pending = False
        self.update_idletasks()
        self._draw_chart(animate=True)

    def _on_resize(self, e) -> None:
        # 窗口刚映射时也会触发 <Configure>；不能在动画播放中直接重绘，
        # 否则 _show_chart 会把刚发出的逐帧 after 取消掉。
        if self._closed or self._initial_pending:
            return
        if self._chart_anim_job or self._initial_anim_job:
            return
        if abs(e.width - self._chart_w) > 40:
            self._chart_w = e.width
            self.after(250, self._draw_chart)

    def _schedule_search(self) -> None:
        if self._search_job:
            try:
                self.after_cancel(self._search_job)
            except Exception:
                pass
        self._search_job = self.after(250, self._refresh_view)

    def _sort_by(self, key: str) -> None:
        if self._sort_key == key:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_key = key
            self._sort_rev = key in ("t", "tokens", "sec", "cost")
        self._refresh_view()

    def _show_detail(self, _ev=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        idx = self.tree.index(sel[0])
        if idx < 0 or idx >= len(self._rows):
            return
        r = self._rows[idx]
        ts = dt.datetime.fromtimestamp(int(r.get("t", 0))).strftime("%Y-%m-%d %H:%M:%S")
        body = (f"时间：{ts}\n式神：{r.get('model') or '?'}\n"
                f"输入：{r.get('prompt', 0)} tokens\n"
                f"输出：{r.get('completion', 0)} tokens\n"
                f"总灵力：{r.get('tokens', 0)} tokens\n"
                f"耗时：{float(r.get('sec') or 0):.2f} 秒\n"
                f"香火钱：{self._fmt_cost(r.get('cost', 0))}")
        messagebox.showinfo("香火钱账本 · 单条记录", body, parent=self)

    def _export(self) -> None:
        dest = filedialog.asksaveasfilename(
            parent=self, title="抄录香火钱账本", defaultextension=".csv",
            filetypes=[("CSV 账本", "*.csv")])
        if not dest:
            return
        try:
            n = usage.export_csv(dest, self._rows)
            self._status_var.set(f"灵梦：抄录了 {n} 条，放在 {dest}。")
            messagebox.showinfo("香火钱账本", f"已抄录 {n} 条记录到：\n{dest}", parent=self)
        except Exception as e:
            messagebox.showerror("香火钱账本", f"抄录失败：{e}", parent=self)

    def _clear(self) -> None:
        if not messagebox.askyesno(
                "倒空赛钱箱",
                "灵梦：真要把赛钱箱倒空？倒出去可就捡不回来了。\n"
                "只会清空本机用量记录，不会动配置和 API Key。",
                parent=self):
            return
        try:
            ok = usage.clear()
        except Exception:
            ok = False
        if not ok:
            messagebox.showerror("香火钱账本", "赛钱箱倒不空——账本文件写不了。", parent=self)
            return
        self.refresh_data()
        self._status_var.set("灵梦：赛钱箱倒空了，账本又是新的一页。")

    def _fmt_tokens(self, n) -> str:
        try:
            return f"{int(n):,}"
        except Exception:
            return "0"

    def _fmt_cost(self, n) -> str:
        try:
            return f"¥{float(n):.4f}"
        except Exception:
            return "¥0.0000"

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.app.cfg["usage_chart_kind"] = (
            "line" if self._chart_kind.get() == "折线图" else "bar")
        for job in (self._chart_anim_job, self._initial_anim_job):
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        self._chart_anim_job = None
        self._initial_anim_job = None
        try:
            if getattr(self.app, "_usage_win", None) is self:
                self.app._usage_win = None
            self.destroy()
        except Exception:
            pass
