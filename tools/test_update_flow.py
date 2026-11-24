"""更新结果 / Toast 结果 / 去重 / 安静时段 功能测试。"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import tkinter as tk

import app as appmod
from modules import toast as toastmod

root = tk.Tk()
a = appmod.App(root)
root.withdraw()

shown = []
notified = []
_original_show_dialog = a._show_update_dialog
a._show_update_dialog = lambda info: shown.append(info)
a._notify = lambda *args, **kwargs: notified.append((args, kwargs))
toastmod.show = lambda *args, **kwargs: True

info = {"version": "1.0.7", "tag": "v1.0.7", "source": "gitee",
        "date": "2026-11-30", "notes": "说明", "url": "https://example.com",
        "download": "https://example.com/Setup.exe"}

# 手动点击「立即打听」，发现新版本：窗口 + Toast
a._on_update_result(info, "", True)
assert a._update_offered == "v1.0.7"
assert shown and shown[0]["version"] == "1.0.7"
assert notified and notified[-1][1].get("force") is True
assert "文文" in notified[-1][0][2]
print("  OK  manual new version -> dialog + forced toast")

# 手动再次检查同一版本：不重复弹窗，但仍有结果 Toast
shown.clear()
notified.clear()
a._on_update_result(info, "", True)
assert not shown, "同一版本不应重复弹窗"
assert notified and notified[-1][1].get("force") is True
assert "已经给你看过" in a.status_var.get() or "文文" in a.status_var.get()
print("  OK  manual repeat -> toast without duplicate dialog")

# 手动检查：已是最新
shown.clear()
notified.clear()
a._update_offered = ""
newest = {"version": appmod.settings.APP_VERSION, "tag": "v" + appmod.settings.APP_VERSION,
          "source": "gitee", "date": "", "notes": ""}
a._on_update_result(newest, "", True)
assert notified and notified[-1][1].get("force") is True
assert "最新" in notified[-1][0][2]
print("  OK  manual up-to-date -> toast")

# 手动检查：连接失败
notified.clear()
a._on_update_result(None, "SSL handshake failed", True)
assert notified and notified[-1][1].get("force") is True
assert "结界" in notified[-1][0][2]
print("  OK  manual error -> toast")

# 自动检查发现新版本：只弹提示，不再额外 Toast（避免同一件事说两遍）
shown.clear()
notified.clear()
a._update_offered = ""
a._on_update_result(info, "", False)
assert shown
assert not notified
print("  OK  automatic new version -> dialog only (no toast)")

# 首次启动完全不检查；后续启动只查一次
calls = []
a._check_updates = lambda manual=False: calls.append(manual)
a._suppress_update_this_run = False
a._update_startup_scheduled = False
a._schedule_update_check(first_launch=True)
assert a._suppress_update_this_run
a._update_check_startup()
assert calls == [], "首次启动不应检查更新"
a._schedule_update_check(first_launch=False)
a._update_check_startup()
assert calls == [False], "后续启动应只自动检查一次"
print("  OK  first launch skipped; later launch checks once")

# 更新窗口：只给下载页/复制/稍后，不再提供代下载
opened = []
a._open_url = lambda url: opened.append(url)
a._show_update_dialog = _original_show_dialog
a._show_update_dialog(info)
for _ in range(10):
    root.update()
    time.sleep(0.03)
texts = []
def walk(w):
    for c in w.winfo_children():
        try:
            texts.append(str(c.cget("text")))
        except Exception:
            pass
        walk(c)
for w in root.winfo_children():
    if isinstance(w, tk.Toplevel) and "号外" in w.title():
        walk(w)
assert "前往下载页" in texts
assert "复制链接" in texts
assert "稍后再说" in texts
assert "让文文去取" not in texts
print("  OK  update dialog offers manual download only")

# 去重键（避开安静时段，否则 _do_notify 会按设计不写 seen）
a._toast_seen = {}
a.cfg["toast_seen"] = {}
a.cfg["toast_quiet_start"] = 0
a.cfg["toast_quiet_end"] = 0
a._do_notify("update", "博麗神社 · 号外", "测试", key="v1.0.7")
assert a.cfg["toast_seen"].get("update") == "v1.0.7"
print("  OK  notify dedupe key stored")

# 安静时段：手动 force 仍然写 seen / 不因 quiet 丢弃
a.cfg["toast_quiet_start"] = 0
a.cfg["toast_quiet_end"] = 24
before = dict(a.cfg.get("toast_seen") or {})
a._do_notify("balance", "博麗神社 · 香火钱", "测试", key="quiet-test")
assert "balance" not in a.cfg["toast_seen"], "安静时段不应弹余额"
a._do_notify("balance", "博麗神社 · 香火钱", "测试", key="force-test", force=True)
assert a.cfg["toast_seen"].get("balance") == "force-test"
a.cfg["toast_quiet_start"] = 23
a.cfg["toast_quiet_end"] = 8
a.cfg["toast_seen"] = before
print("  OK  quiet hours / force")

root.destroy()
print("RESULT: PASS")
