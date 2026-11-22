"""封笔日历：自绘月历，选一个「暂停更新到」的日期。

不依赖第三方库；周一作为每周第一天。
"""
from __future__ import annotations

import calendar
import datetime as dt
import tkinter as tk

DEFAULT_COLORS = {
    "bg": "#141221",
    "panel": "#1c1830",
    "panel2": "#231d3a",
    "input": "#2a2342",
    "text": "#f2eef8",
    "muted": "#a89fc7",
    "accent": "#d7444f",
    "gold": "#e8c46a",
    "ok": "#7ed6a5",
    "border": "#3a3157",
}

WEEKDAYS = ("一", "二", "三", "四", "五", "六", "日")


def month_matrix(year: int, month: int) -> list[list[dt.date]]:
    """返回 4–6 周，每周 7 天，周一开头；包含相邻月份的日期。"""
    cal = calendar.Calendar(firstweekday=0)
    return [list(w) for w in cal.monthdatescalendar(year, month)]


def pick_date(
    parent: tk.Misc,
    initial: dt.date | None = None,
    min_date: dt.date | None = None,
    max_date: dt.date | None = None,
    colors: dict | None = None,
    title: str = "封笔日历",
    subtitle: str = "让文文歇到哪天？",
) -> dt.date | None:
    """打开月历，返回选中的日期；取消返回 None。"""
    c = dict(DEFAULT_COLORS)
    c.update(colors or {})
    today = dt.date.today()
    min_date = min_date or today
    max_date = max_date or (today + dt.timedelta(days=365))

    start = initial if (initial and min_date <= initial <= max_date) else today
    state = {"selected": start, "year": start.year, "month": start.month}

    win = tk.Toplevel(parent)
    win.title(title)
    win.configure(bg=c["bg"])
    win.resizable(False, False)
    win.transient(parent)
    try:
        win.grab_set()
    except Exception:
        pass

    tk.Label(win, text=title, bg=c["bg"], fg=c["gold"],
             font=("Microsoft YaHei UI", 13, "bold")).pack(pady=(14, 2))
    tk.Label(win, text=subtitle, bg=c["bg"], fg=c["muted"],
             font=("Microsoft YaHei UI", 9)).pack(pady=(0, 8))

    head = tk.Frame(win, bg=c["bg"])
    head.pack(fill="x", padx=16)
    month_var = tk.StringVar()

    def shift(delta: int) -> None:
        y, m = state["year"], state["month"] + delta
        while m < 1:
            y, m = y - 1, m + 12
        while m > 12:
            y, m = y + 1, m - 12
        state["year"], state["month"] = y, m
        render()

    tk.Button(head, text="‹", width=3, command=lambda: shift(-1),
              bg=c["panel"], fg=c["text"], relief="flat",
              activebackground=c["panel2"], activeforeground=c["gold"],
              bd=0, font=("Microsoft YaHei UI", 12, "bold")).pack(side="left")
    tk.Label(head, textvariable=month_var, bg=c["bg"], fg=c["text"],
             font=("Microsoft YaHei UI", 11, "bold")).pack(side="left", expand=True)
    tk.Button(head, text="›", width=3, command=lambda: shift(1),
              bg=c["panel"], fg=c["text"], relief="flat",
              activebackground=c["panel2"], activeforeground=c["gold"],
              bd=0, font=("Microsoft YaHei UI", 12, "bold")).pack(side="right")

    grid = tk.Frame(win, bg=c["bg"])
    grid.pack(padx=16, pady=(8, 4))

    status = tk.StringVar()
    tk.Label(win, textvariable=status, bg=c["bg"], fg=c["gold"],
             font=("Microsoft YaHei UI", 9), wraplength=320,
             justify="left").pack(pady=(2, 8))

    quick = tk.Frame(win, bg=c["bg"])
    quick.pack(pady=(0, 8))

    def pick_quick(days: int) -> None:
        d = min(today + dt.timedelta(days=days), max_date)
        state["selected"] = d
        state["year"], state["month"] = d.year, d.month
        render()

    for label, days in (("歇 1 天", 1), ("歇 3 天", 3), ("歇 7 天", 7), ("歇 30 天", 30)):
        tk.Button(quick, text=label, command=lambda d=days: pick_quick(d),
                  bg=c["panel"], fg=c["muted"], relief="flat", bd=0,
                  activebackground=c["panel2"], activeforeground=c["gold"],
                  font=("Microsoft YaHei UI", 9), padx=8, pady=2).pack(side="left", padx=3)

    result: dict = {"date": None}

    def confirm() -> None:
        d = state["selected"]
        if d and min_date <= d <= max_date:
            result["date"] = d
            win.destroy()

    def cancel() -> None:
        result["date"] = None
        win.destroy()

    bottom = tk.Frame(win, bg=c["bg"])
    bottom.pack(fill="x", padx=16, pady=(0, 14))
    tk.Button(bottom, text="算了", command=cancel,
              bg=c["panel"], fg=c["muted"], relief="flat", bd=0,
              activebackground=c["panel2"], activeforeground=c["text"],
              font=("Microsoft YaHei UI", 10), padx=14, pady=4).pack(side="right")
    tk.Button(bottom, text="就这天", command=confirm,
              bg=c["accent"], fg="white", relief="flat", bd=0,
              activebackground=c["gold"], activeforeground=c["bg"],
              font=("Microsoft YaHei UI", 10, "bold"), padx=14, pady=4).pack(side="right", padx=(0, 8))

    def refresh_status() -> None:
        d = state["selected"]
        if not d:
            status.set("灵梦：挑个日子吧。")
            return
        left = (d - today).days
        if left <= 0:
            status.set("灵梦：今天就封笔？行吧，反正也拦不住你。")
        else:
            status.set(
                f"灵梦：行吧，让文文歇到 {d.month} 月 {d.day} 日（{left} 天）。"
                "别到时候又忘了。")

    def select(day: dt.date) -> None:
        if not (min_date <= day <= max_date):
            return
        state["selected"] = day
        render()

    def render() -> None:
        month_var.set(f"{state['year']} 年 {state['month']} 月")
        for w in grid.winfo_children():
            w.destroy()
        for i, name in enumerate(WEEKDAYS):
            tk.Label(grid, text=name, bg=c["bg"], fg=c["muted"],
                     font=("Microsoft YaHei UI", 9), width=4).grid(
                         row=0, column=i, pady=(0, 4))

        for r, week in enumerate(month_matrix(state["year"], state["month"]), start=1):
            for col, day in enumerate(week):
                if day.month != state["month"]:
                    tk.Label(grid, text="", bg=c["bg"], width=4).grid(row=r, column=col)
                    continue
                enabled = min_date <= day <= max_date
                selected = (day == state["selected"])
                is_today = (day == today)
                bg = c["accent"] if selected else (c["panel"] if enabled else c["bg"])
                fg = "#ffffff" if selected else (c["text"] if enabled else c["border"])
                if is_today and not selected:
                    fg = c["gold"]
                btn = tk.Button(
                    grid, text=str(day.day), width=4,
                    command=lambda d=day: select(d),
                    bg=bg, fg=fg, relief="flat", bd=0,
                    activebackground=c["panel2"], activeforeground=c["gold"],
                    font=("Microsoft YaHei UI", 9, "bold" if selected else "normal"),
                    state=("normal" if enabled else "disabled"),
                    disabledforeground=c["border"],
                )
                btn.grid(row=r, column=col, padx=1, pady=1)
                if enabled:
                    btn.bind("<Double-Button-1>",
                             lambda _e, d=day: (select(d), confirm()))
        refresh_status()

    win.bind("<Escape>", lambda _e: cancel())
    win.bind("<Return>", lambda _e: confirm())

    render()
    win.update_idletasks()
    try:
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = win.winfo_width(), win.winfo_height()
        win.geometry(f"+{px + max(0, (pw - w) // 2)}+{py + max(0, (ph - h) // 2)}")
    except Exception:
        pass
    win.wait_window()
    return result["date"]
