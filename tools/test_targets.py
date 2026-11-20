"""单元测试：输入框选择逻辑（不需要浏览器）。"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ.setdefault("SHINICHI_CONFIG_DIR", os.path.join(HERE, ".test_config"))
sys.path.insert(0, ROOT)

import tkinter as tk

from app import App

root = tk.Tk()
root.withdraw()
app = App(root)


def ids(targets):
    return [b["id"] for b in targets]


cases = []

# 1) 多小问动态加框：当前是 Part 3，S2 是空框
st = {"fields": [
    {"id": "S1", "label": "67980"},
    {"id": "S4", "label": "67980"},
    {"id": "S5", "label": "180000"},
    {"id": "S2", "label": "enter your response here"},
]}
cases.append(("动态多小问", ids(app._web_targets(st, 3)), ["S2", "S1", "S4", "S5"]))

# 2) 单空题
st = {"fields": [{"id": "S1", "label": "enter your response here"}]}
cases.append(("单空题", ids(app._web_targets(st, 1)), ["S1"]))

# 3) 没有空框时按小问号
st = {"fields": [
    {"id": "S1", "label": "1"},
    {"id": "S2", "label": "2"},
]}
cases.append(("无空框按序号", ids(app._web_targets(st, 2)), ["S2", "S1"]))

# 4) readonly 的框要被排除
st = {"fields": [
    {"id": "S1", "label": "67980", "readonly": True},
    {"id": "S2", "label": "enter your response here"},
]}
cases.append(("排除 readonly", ids(app._web_targets(st, 1)), ["S2"]))

# 5) 两个空框（多空题）
st = {"fields": [
    {"id": "S3", "label": "enter your response here"},
    {"id": "S6", "label": "enter your response here"},
]}
cases.append(("两个空框", ids(app._web_targets(st, 1)), ["S3", "S6"]))

ok = True
for name, got, want in cases:
    good = got == want
    ok = ok and good
    print(("  ✓ " if good else "  ✗ ") + name, "->", got, "期望", want)

try:
    app.hotkeys.stop()
    app.clip_watcher.stop()
except Exception:
    pass
root.destroy()
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
