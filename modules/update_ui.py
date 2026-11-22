"""号外下载窗口 / 下载完成窗口（东方风）。"""
from __future__ import annotations

import os
import shutil
import time
import tkinter as tk
from tkinter import filedialog, ttk
from urllib.parse import unquote, urlparse

from PIL import Image, ImageTk

from modules import shell_drag
from modules.update_download import DownloadJob

BG = "#0c0912"
PANEL = "#15111d"
PANEL2 = "#211a2b"
TEXT = "#fffaf6"
MUTED = "#d6c8df"
GOLD = "#f1c75b"
RED = "#b33844"
GREEN = "#8fd3a8"
BORDER = "#3a2d47"


def _fmt_size(n: int) -> str:
    n = max(0, int(n or 0))
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n:.2f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return f"{n:.2f} GiB"


def _safe_name(info: dict) -> str:
    name = str(info.get("asset_name") or "").strip()
    if not name:
        name = os.path.basename(unquote(urlparse(str(info.get("download") or "")).path))
    if not name.lower().endswith((".exe", ".msi")):
        name = f"SpellCardHomework-Setup-{info.get('version', 'new')}.exe"
    name = "".join(c if c not in '\\/:*?"<>|' else "_" for c in name)
    return name


def _updates_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "SpellCardHomework", "updates")
    os.makedirs(d, exist_ok=True)
    return d


def _style(root: tk.Misc) -> None:
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass
    st.configure("Touhou.TNotebook", background=BG, borderwidth=0)
    st.configure("Touhou.TNotebook.Tab", background=PANEL2, foreground=MUTED,
                 padding=(14, 5), font=("Microsoft YaHei UI", 10))
    st.map("Touhou.TNotebook.Tab",
           background=[("selected", PANEL)], foreground=[("selected", GOLD)])
    st.configure("Touhou.Horizontal.TProgressbar", troughcolor="#09070f",
                 background=GOLD, lightcolor=RED, darkcolor=RED,
                 bordercolor=BORDER, thickness=12)
    st.configure("Touhou.Treeview", background=PANEL, fieldbackground=PANEL,
                 foreground=TEXT, rowheight=24, borderwidth=0)
    st.configure("Touhou.Treeview.Heading", background=PANEL2, foreground=GOLD,
                 font=("Microsoft YaHei UI", 9, "bold"))
    st.configure("Treeview.Heading", background=PANEL2, foreground=GOLD,
                 font=("Microsoft YaHei UI", 9, "bold"))
    st.map("Touhou.Treeview", background=[("selected", "#34263f")])


class DownloadWindow:
    def __init__(self, root, info: dict, colors: dict, font_ui: str,
                 font_title: str, avatar_path: str, on_install):
        _style(root)
        self.root = root
        self.info = dict(info or {})
        self.on_install = on_install
        self.job: DownloadJob | None = None
        self.dest = os.path.join(_updates_dir(), _safe_name(self.info))
        self.verified = False
        self.last_done = 0
        self.last_time = time.time()
        self.speed = 0.0
        self._paused = False
        self._closing = False
        self._seg_items: list[str] = []
        self._spark: list[float] = []
        self._last_status = ""

        w, h = 740, 680
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        win = tk.Toplevel(root)
        self.win = win
        win.title("博麗神社 · 号外取件")
        win.configure(bg=BG)
        win.transient(root)
        win.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2)}")
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", self._close)
        try:
            win.grab_set()
        except Exception:
            pass

        # 顶部：文文头像 + 标题
        head = tk.Frame(win, bg=BG)
        head.pack(fill="x", padx=18, pady=(16, 8))
        self._avatar_photo = None
        try:
            if avatar_path and os.path.exists(avatar_path):
                im = Image.open(avatar_path).convert("RGBA").resize((58, 58), Image.LANCZOS)
                self._avatar_photo = ImageTk.PhotoImage(im)
                tk.Label(head, image=self._avatar_photo, bg=BG, bd=0).pack(side="left")
        except Exception:
            pass
        ht = tk.Frame(head, bg=BG)
        ht.pack(side="left", padx=(12, 0))
        tk.Label(ht, text="文文：号外正在从人间之里送来……", bg=BG, fg=GOLD,
                 font=(font_title, 17), anchor="w").pack(anchor="w")
        self.sub = tk.Label(ht, text=f"{self.info.get('version', '')} · {_safe_name(self.info)}",
                            bg=BG, fg=MUTED, font=(font_ui, 9), anchor="w")
        self.sub.pack(anchor="w", pady=(2, 0))

        self.nb = ttk.Notebook(win, style="Touhou.TNotebook")
        self.nb.pack(fill="both", expand=True, padx=18, pady=(0, 8))

        # --- 信息页 ---
        self.info_tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(self.info_tab, text="号外信息")
        grid = tk.Frame(self.info_tab, bg=BG)
        grid.pack(fill="x", padx=8, pady=(10, 4))
        grid.columnconfigure(1, weight=1)
        self.vals = {}
        rows = [
            ("名称", "name"), ("状态", "status"), ("大小", "size"),
            ("已取", "done"), ("脚程", "speed"), ("剩余", "eta"),
            ("分片", "threads"), ("续传", "resume"), ("校验", "sha"),
        ]
        for i, (label, key) in enumerate(rows):
            tk.Label(grid, text=label, bg=BG, fg=MUTED, font=(font_ui, 9),
                     width=8, anchor="e").grid(row=i, column=0, sticky="e", pady=1)
            var = tk.StringVar(value="—")
            self.vals[key] = var
            tk.Label(grid, textvariable=var, bg=BG, fg=TEXT, font=(font_ui, 9),
                     anchor="w").grid(row=i, column=1, sticky="w", padx=(12, 0), pady=1)
        self.vals["name"].set(_safe_name(self.info))
        self.vals["status"].set("正在向人间之里打听…")
        self.vals["sha"].set("等待校验")

        self.prog = ttk.Progressbar(self.info_tab, style="Touhou.Horizontal.TProgressbar",
                                    mode="determinate", maximum=100)
        self.prog.pack(fill="x", padx=8, pady=(8, 8))

        tbl = tk.Frame(self.info_tab, bg=PANEL, highlightbackground=BORDER,
                       highlightthickness=1)
        tbl.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self._seg_table = tbl
        head = tk.Frame(tbl, bg=PANEL2)
        head.pack(fill="x")
        for j, (text, wdt) in enumerate((("#", 6), ("状态", 14), ("已取", 12), ("总大小", 12))):
            lab = tk.Label(head, text=text, bg=PANEL2, fg=GOLD,
                           font=(font_ui, 9, "bold"), anchor="w", width=wdt)
            lab.grid(row=0, column=j, sticky="ew", padx=6, pady=3)
            head.columnconfigure(j, weight=1)
        body = tk.Frame(tbl, bg=PANEL)
        body.pack(fill="both", expand=True)
        self._seg_canvas = tk.Canvas(body, bg=PANEL, highlightthickness=0)
        sb = ttk.Scrollbar(body, orient="vertical", command=self._seg_canvas.yview)
        self._seg_canvas.configure(yscrollcommand=sb.set)
        self._seg_canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._seg_inner = tk.Frame(self._seg_canvas, bg=PANEL)
        self._seg_window = self._seg_canvas.create_window(
            (0, 0), window=self._seg_inner, anchor="nw")
        self._seg_inner.bind("<Configure>", lambda _e: self._seg_canvas.configure(
            scrollregion=self._seg_canvas.bbox("all")))
        self._seg_canvas.bind("<Configure>", lambda e: self._seg_canvas.itemconfigure(
            self._seg_window, width=e.width))

        # --- 脚程页 ---
        speed_tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(speed_tab, text="脚程")
        tk.Label(speed_tab, text="文文的脚程", bg=BG, fg=GOLD,
                 font=(font_ui, 14)).pack(anchor="w", padx=12, pady=(12, 2))
        self.speed_canvas = tk.Canvas(speed_tab, bg="#09070f", height=240,
                                      highlightthickness=1, highlightbackground=BORDER)
        self.speed_canvas.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self.speed_label = tk.Label(speed_tab, text="0 B/s", bg=BG, fg=MUTED,
                                    font=(font_ui, 10))
        self.speed_label.pack(anchor="w", padx=12, pady=(0, 10))

        # --- 完成后页 ---
        after_tab = tk.Frame(self.nb, bg=BG)
        self.nb.add(after_tab, text="张贴之后")
        tk.Label(after_tab, text="号外到手之后", bg=BG, fg=GOLD,
                 font=(font_ui, 14)).pack(anchor="w", padx=12, pady=(14, 6))
        for line in (
            "① 验明正身：核对 SHA256",
            "② 自动覆盖安装：由更新助手张贴号外",
            "③ 提示重启：现在重开或稍后自己开",
            "④ 若校验失败，安装包会被烧掉，不会安装",
        ):
            tk.Label(after_tab, text=line, bg=BG, fg=TEXT, font=(font_ui, 10),
                     anchor="w").pack(fill="x", padx=20, pady=3)
        tk.Label(after_tab, text="～ 文文新闻 · 号外取件 ～", bg=BG, fg=MUTED,
                 font=(font_ui, 9)).pack(anchor="w", padx=12, pady=(20, 0))

        # --- 底部按钮 ---
        foot = tk.Frame(win, bg=BG)
        foot.pack(fill="x", padx=18, pady=(0, 14))
        self.pause_btn = tk.Button(foot, text="暂停取件", command=self._toggle_pause,
                                   bg=PANEL2, fg=TEXT, relief="flat", bd=0,
                                   padx=16, pady=5, cursor="hand2", font=(font_ui, 10))
        self.pause_btn.pack(side="left")
        self.retry_btn = tk.Button(foot, text="再取一次", command=self._retry,
                                   bg=PANEL2, fg=GOLD, relief="flat", bd=0,
                                   padx=14, pady=5, cursor="hand2", font=(font_ui, 10))
        self.retry_btn.pack(side="left", padx=(8, 0))
        self.retry_btn.pack_forget()
        tk.Button(foot, text="取消", command=self._close, bg=PANEL2, fg=MUTED,
                  relief="flat", bd=0, padx=14, pady=5, cursor="hand2",
                  font=(font_ui, 10)).pack(side="left", padx=(8, 0))
        tk.Button(foot, text="打开取件匣", command=self._open_folder, bg=PANEL2,
                  fg=TEXT, relief="flat", bd=0, padx=14, pady=5, cursor="hand2",
                  font=(font_ui, 10)).pack(side="right")

        self._font_ui = font_ui
        self._font_title = font_title
        self.win.after(80, self._start)
        self.win.after(120, self._poll)

    def _start(self) -> None:
        url = str(self.info.get("download") or "")
        if not url:
            self._set_error("文文：这张号外没带安装包地址，先去号外页看看。")
            return
        sha = str(self.info.get("sha256") or "")
        threads = int(self.info.get("max_threads") or 8)
        self.job = DownloadJob(url, self.dest, sha, max_threads=threads)
        self.job.start()

    def _poll(self) -> None:
        if self._closing:
            return
        if self.job is not None:
            try:
                while True:
                    ev = self.job.events.get_nowait()
                    self._handle_event(ev)
            except Exception:
                pass
        try:
            self.win.after(120, self._poll)
        except Exception:
            pass

    def _handle_event(self, ev: dict) -> None:
        kind = ev.get("type")
        if kind == "meta":
            self.total = int(ev.get("total") or 0)
            self.vals["status"].set("正在取件 · 人间之里")
            self.vals["size"].set(_fmt_size(self.total))
            self.vals["threads"].set(f"{ev.get('threads', 1)} 个")
            self.vals["resume"].set("是")
            self._build_segments(ev.get("segments") or [])
        elif kind == "status":
            self.vals["status"].set(ev.get("text") or "正在取件…")
        elif kind == "progress":
            self._handle_progress(ev)
        elif kind == "paused":
            self._paused = True
            self.pause_btn.configure(text="继续取件")
            self.vals["status"].set("文文：先歇一会儿，号外还在取件匣里。")
        elif kind == "canceled":
            self._close()
        elif kind == "error":
            self._set_error(self._error_text(ev.get("code")))
        elif kind == "done":
            self.verified = bool(ev.get("verified"))
            self._finish(ev.get("path") or self.dest)

    def _handle_progress(self, ev: dict) -> None:
        done = int(ev.get("done") or 0)
        total = int(ev.get("total") or getattr(self, "total", 0) or 0)
        now = time.time()
        dt = max(0.001, now - self.last_time)
        self.speed = max(0.0, (done - self.last_done) / dt)
        self.last_done, self.last_time = done, now
        pct = (100.0 * done / total) if total else 0.0
        self.prog.configure(value=max(0.0, min(100.0, pct)))
        self.vals["done"].set(f"{_fmt_size(done)} ({pct:.1f}%)")
        if not self._paused:
            self.vals["speed"].set(f"{_fmt_size(self.speed)}/s")
            if self.speed > 0 and total > done:
                self.vals["eta"].set(self._fmt_eta((total - done) / self.speed))
            else:
                self.vals["eta"].set("—")
        self.speed_label.configure(text=f"{_fmt_size(self.speed)}/s")
        self._spark.append(self.speed)
        if len(self._spark) > 240:
            self._spark = self._spark[-240:]
        self._draw_spark()
        for i, seg in enumerate(ev.get("segments") or []):
            if i >= len(getattr(self, "_seg_rows", [])):
                break
            rv = self._seg_rows[i]["vars"]
            rv["state"].set("正在取件")
            rv["done"].set(_fmt_size(seg.get("done", 0)))
            if int(seg.get("done") or 0) >= int(seg["end"]) - int(seg["start"]) + 1:
                rv["state"].set("已取到")
                for lab in self._seg_rows[i]["labels"]:
                    lab.configure(fg=MUTED)

    def _build_segments(self, segs: list[dict]) -> None:
        for w in getattr(self, "_seg_rows", []):
            try:
                w["frame"].destroy()
            except Exception:
                pass
        self._seg_rows = []
        parent = self._seg_inner
        for i, seg in enumerate(segs):
            total = int(seg["end"]) - int(seg["start"]) + 1
            row = tk.Frame(parent, bg=PANEL)
            row.grid(row=i, column=0, columnspan=4, sticky="ew")
            vals = {
                "no": tk.StringVar(value=str(i + 1)),
                "state": tk.StringVar(value="等待"),
                "done": tk.StringVar(value=_fmt_size(seg.get("done", 0))),
                "total": tk.StringVar(value=_fmt_size(total)),
            }
            labels = []
            for j, (key, wdt) in enumerate((("no", 6), ("state", 14), ("done", 12), ("total", 12))):
                lab = tk.Label(row, textvariable=vals[key], bg=PANEL, fg=TEXT,
                               font=(self._font_ui, 9), anchor="w", width=wdt)
                lab.grid(row=0, column=j, sticky="ew", padx=6, pady=1)
                labels.append(lab)
            self._seg_rows.append({"frame": row, "vars": vals, "labels": labels})
        try:
            self._seg_canvas.configure(scrollregion=self._seg_canvas.bbox("all"))
        except Exception:
            pass

    def _draw_spark(self) -> None:
        c = self.speed_canvas
        c.delete("all")
        w = max(100, c.winfo_width())
        h = max(60, c.winfo_height())
        c.create_line(0, h - 1, w, h - 1, fill=BORDER)
        if len(self._spark) < 2:
            return
        mx = max(self._spark) or 1
        pts = []
        for i, v in enumerate(self._spark):
            x = i / max(1, len(self._spark) - 1) * (w - 2) + 1
            y = h - 4 - (v / mx) * (h - 12)
            pts.extend((x, y))
        if len(pts) >= 4:
            c.create_line(*pts, fill=GOLD, width=2, smooth=True)

    @staticmethod
    def _fmt_eta(sec: float) -> str:
        sec = max(0, int(sec))
        if sec >= 3600:
            return f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"
        return f"{sec // 60:02d}:{sec % 60:02d}"

    def _toggle_pause(self) -> None:
        if self.job is None:
            return
        if self._paused:
            self._paused = False
            self.pause_btn.configure(text="暂停取件")
            self.job.resume()
        else:
            self._paused = True
            self.pause_btn.configure(text="继续取件")
            self.job.pause()

    def _retry(self) -> None:
        url = str(self.info.get("download") or "")
        if not url:
            return
        self.retry_btn.pack_forget()
        self.pause_btn.pack(side="left")
        self._paused = False
        self.pause_btn.configure(text="暂停取件")
        self.vals["status"].set("文文：再跑一趟，这次别被结界挡住。")
        sha = str(self.info.get("sha256") or "")
        threads = int(self.info.get("max_threads") or 8)
        self.job = DownloadJob(url, self.dest, sha, max_threads=threads)
        self.job.start()

    def _error_text(self, code) -> str:
        code = str(code or "")
        if code == "sha256":
            return "文文：这张号外被掉包了！SHA256 对不上，已经烧掉了。"
        if "disk" in code:
            return "文文：取件匣塞满了……请清理后再来。"
        if code == "incomplete":
            return "文文：号外少了几页，没取完整。要再试一次吗？"
        if code.startswith("segment"):
            return "文文：有一片号外被风吹走了……要再试一次吗？"
        if code.startswith("exception"):
            return "文文：路被结界挡住了……要再试一次吗？"
        return "文文：号外没取成，要再试一次吗？"

    def _set_error(self, text: str) -> None:
        self.vals["status"].set(text)
        self.vals["speed"].set("—")
        self.vals["eta"].set("—")
        self.retry_btn.pack(side="left", padx=(8, 0))
        self.pause_btn.pack_forget()
        try:
            self.nb.select(0)
        except Exception:
            pass

    def _finish(self, path: str) -> None:
        try:
            size = os.path.getsize(path)
        except Exception:
            size = 0
        self._closing = True
        try:
            self.win.grab_release()
        except Exception:
            pass
        try:
            self.win.destroy()
        except Exception:
            pass
        CompleteWindow(self.root, path, self.info, size, self.verified,
                       self._font_ui, self._font_title, self.on_install)

    def _open_folder(self) -> None:
        try:
            os.startfile(os.path.dirname(self.dest))
        except Exception:
            pass

    def _close(self) -> None:
        self._closing = True
        try:
            if self.job is not None:
                self.job.cancel()
        except Exception:
            pass
        try:
            self.win.grab_release()
        except Exception:
            pass
        try:
            self.win.destroy()
        except Exception:
            pass


class CompleteWindow:
    def __init__(self, root, path: str, info: dict, size: int,
                 verified: bool, font_ui: str, font_title: str, on_install):
        self.root = root
        self.path = path
        self.on_install = on_install
        self.verified = verified
        self.size = size
        self._countdown = 3 if verified else 0
        self._job = None
        self._closed = False
        self._font_ui = font_ui

        w, h = 660, 250
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        win = tk.Toplevel(root)
        self.win = win
        win.title("博麗神社 · 号外取件")
        win.configure(bg=BG)
        win.transient(root)
        win.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2)}")
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", self._close)
        try:
            win.grab_set()
        except Exception:
            pass

        head = tk.Frame(win, bg=BG)
        head.pack(fill="x", padx=20, pady=(18, 4))
        self.avatar_photo = None
        try:
            p = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets",
                             "char", "toast", "avatar_aya.png")
            if os.path.exists(p):
                im = Image.open(p).convert("RGBA").resize((62, 62), Image.LANCZOS)
                self.avatar_photo = ImageTk.PhotoImage(im)
                tk.Label(head, image=self.avatar_photo, bg=BG, bd=0).pack(side="left")
        except Exception:
            pass
        title_box = tk.Frame(head, bg=BG)
        title_box.pack(side="left", padx=(14, 0))
        tk.Label(title_box, text="号外已经取到", bg=BG, fg=GOLD,
                 font=(font_title, 21), anchor="w").pack(anchor="w")
        self.sub_var = tk.StringVar(
            value="SHA256 已验 · 可以张贴" if verified else "符咒缺失 · 只能手动处理")
        tk.Label(title_box, textvariable=self.sub_var, bg=BG,
                 fg=GREEN if verified else "#e7b96a",
                 font=(font_ui, 10), anchor="w").pack(anchor="w", pady=(2, 0))

        row = tk.Frame(win, bg=BG)
        row.pack(fill="x", padx=20, pady=(8, 2))
        tk.Label(row, text=_fmt_size(size), bg=BG, fg=TEXT,
                 font=(font_ui, 10)).pack(side="left")
        tk.Label(row, text=os.path.basename(path), bg=BG, fg=MUTED,
                 font=(font_ui, 10)).pack(side="left", padx=(18, 0))

        self.count_var = tk.StringVar(
            value=f"{self._countdown} 秒后自动张贴……" if verified else "不会自动张贴")
        tk.Label(win, textvariable=self.count_var, bg=BG, fg=MUTED,
                 font=(font_ui, 9)).pack(anchor="w", padx=20, pady=(4, 6))

        sep = tk.Frame(win, bg=BORDER, height=1)
        sep.pack(fill="x", padx=20, pady=(0, 8))

        foot = tk.Frame(win, bg=BG)
        foot.pack(fill="x", padx=20, pady=(0, 16))
        self.install_btn = tk.Button(foot, text="立即张贴", command=self._install,
                                     bg=RED, fg="#ffffff", relief="flat", bd=0,
                                     padx=18, pady=6, cursor="hand2",
                                     font=(font_ui, 10, "bold"))
        self.install_btn.pack(side="left")
        tk.Button(foot, text="打开取件匣", command=self._open_folder,
                  bg=PANEL2, fg=TEXT, relief="flat", bd=0, padx=14, pady=6,
                  cursor="hand2", font=(font_ui, 10)).pack(side="left", padx=(8, 0))
        drag = tk.Button(foot, text="✥", command=self._fallback_move, bg=PANEL2,
                         fg=GOLD, relief="flat", bd=0, padx=10, pady=6,
                         cursor="fleur", font=(font_ui, 14, "bold"))
        drag.pack(side="left", padx=(8, 0))
        drag.bind("<ButtonPress-1>", self._start_drag)
        drag.bind("<Enter>", lambda _e: self.count_var.set(
            "按住 ✥ 拖到桌面/文件夹；单击可选择位置"))
        drag.bind("<Leave>", lambda _e: self._show_count())
        tk.Button(foot, text="关闭", command=self._close, bg=PANEL2, fg=MUTED,
                  relief="flat", bd=0, padx=14, pady=6, cursor="hand2",
                  font=(font_ui, 10)).pack(side="right")

        if verified:
            self._job = self.win.after(1000, self._tick)

    def _tick(self) -> None:
        self._job = None
        if self._closed:
            return
        self._countdown -= 1
        if self._countdown <= 0:
            self.count_var.set("正在张贴……")
            self._install()
        else:
            self.count_var.set(f"{self._countdown} 秒后自动张贴……")
            self._job = self.win.after(1000, self._tick)

    def _install(self) -> None:
        if not os.path.exists(self.path):
            self.count_var.set("文文：号外已经不在取件匣里了。")
            return
        self._closed = True
        try:
            if self._job:
                self.win.after_cancel(self._job)
        except Exception:
            pass
        try:
            self.win.grab_release()
        except Exception:
            pass
        try:
            self.win.destroy()
        except Exception:
            pass
        try:
            self.on_install(self.path)
        except Exception:
            pass

    def _start_drag(self, _ev=None) -> None:
        # 拖出时暂停自动张贴
        try:
            if self._job:
                self.win.after_cancel(self._job)
                self._job = None
        except Exception:
            pass
        self.count_var.set("把号外拖到桌面或文件夹……")
        try:
            res = shell_drag.drag_file(self.path)
        except Exception:
            res = {"exists": True, "ok": False}
        if self._closed:
            return
        if not res.get("exists") or not os.path.exists(self.path):
            self.count_var.set("文文：号外已经贴到别处，自动张贴取消。")
            self.install_btn.configure(state="disabled")
            self.sub_var.set("号外已移动到新位置")
            return
        self.count_var.set("文文：号外副本还在取件匣里，继续准备张贴。")
        self.sub_var.set("SHA256 已验 · 可以张贴" if self.verified else "符码缺失")
        if self.verified:
            self._countdown = 3
            self.count_var.set(f"{self._countdown} 秒后自动张贴……")
            self._job = self.win.after(1000, self._tick)

    def _show_count(self) -> None:
        if self._closed:
            return
        if self.verified and self._countdown > 0:
            self.count_var.set(f"{self._countdown} 秒后自动张贴……")
        elif not self.verified:
            self.count_var.set("不会自动张贴；可手动张贴或拖走号外")

    def _fallback_move(self) -> None:
        if self._closed or not os.path.exists(self.path):
            return
        folder = filedialog.askdirectory(
            parent=self.win, title="把号外放到哪个文件夹？")
        if not folder:
            self._show_count()
            return
        try:
            target = os.path.join(folder, os.path.basename(self.path))
            shutil.copy2(self.path, target)
            self.count_var.set(f"文文：号外副本已放到 {folder}")
        except Exception as e:
            self.count_var.set(f"文文：号外贴不过去……{e}")

    def _open_folder(self) -> None:
        try:
            os.startfile(os.path.dirname(self.path))
        except Exception:
            pass

    def _close(self) -> None:
        self._closed = True
        try:
            if self._job:
                self.win.after_cancel(self._job)
        except Exception:
            pass
        try:
            self.win.grab_release()
        except Exception:
            pass
        try:
            self.win.destroy()
        except Exception:
            pass


def start_download(root, info: dict, colors: dict, font_ui: str, font_title: str,
                   avatar_path: str, on_install) -> DownloadWindow:
    return DownloadWindow(root, info, colors, font_ui, font_title,
                          avatar_path, on_install)
