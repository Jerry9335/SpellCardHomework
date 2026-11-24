# -*- coding: utf-8 -*-
"""首次安装 -> 新手引导 -> 老用户/重开 的状态与界面流程测试。"""
from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ.setdefault("SHINICHI_CONFIG_DIR", os.path.join(HERE, ".test_config_onboarding_flow"))
sys.path.insert(0, ROOT)

import tkinter as tk

from app import App
from modules import first_run, settings


def pump(root: tk.Tk, seconds: float = 0.8) -> None:
    end = time.time() + seconds
    while time.time() < end:
        root.update_idletasks()
        root.update()
        time.sleep(0.02)


def clear_state(app: App) -> None:
    for key in list(app.cfg):
        if key.startswith("onboarding_"):
            app.cfg.pop(key, None)
    settings.save(app.cfg)
    app.cfg = settings.load()


def main() -> None:
    root = tk.Tk()
    root.withdraw()
    app = App(root)
    root.deiconify()
    root.update_idletasks()

    # 全新安装：先契约，再引导，完成后写 done。
    clear_state(app)
    app.maybe_start_first_run("fresh", False)
    pump(root, 0.9)
    assert app._setup_win is not None, "setup wizard did not open"
    assert app.cfg.get("onboarding_state") in (
        first_run.STATE_PENDING, first_run.STATE_IN_PROGRESS)
    # 「之后再配」必须进入第 2 签，而不是直接结束/退出契约。
    next_config = next(
        b for b in app._setup_win.foot_right.winfo_children()
        if str(b.cget("text")) == "之后再配")
    next_config.invoke()
    pump(root, 0.2)
    assert app._setup_win.step == 2, "之后再配 should enter step 2"
    app._setup_win.destroy()
    app._setup_win = None
    app._on_setup_done({"skipped": True})
    pump(root, 0.9)
    assert app._onboarding_win is not None, "onboarding did not open"
    app._on_onboarding_done(True)
    pump(root, 0.3)
    assert app.cfg.get("onboarding_state") == first_run.STATE_DONE
    assert app.cfg.get("onboarding_version") == settings.APP_VERSION

    # 已完成用户再次启动不弹。
    app.maybe_start_first_run("licensed", True)
    pump(root, 0.6)
    assert app._setup_win is None and app._onboarding_win is None

    # 升级用户没有 onboarding 字段，但已经配置过 API：只写 legacy，不弹。
    clear_state(app)
    app.cfg["api_key"] = "sk-test-old-user"
    settings.save(app.cfg)
    app.cfg = settings.load()
    app.maybe_start_first_run("licensed", True)
    pump(root, 0.6)
    assert app._setup_win is None and app._onboarding_win is None
    assert app.cfg.get("onboarding_state") == first_run.STATE_LEGACY

    # 手动重看：不改状态。
    app.open_onboarding(manual=True, start_step=1)
    pump(root, 0.7)
    assert app._onboarding_win is not None
    app._on_onboarding_done(True)
    pump(root, 0.3)
    assert app.cfg.get("onboarding_state") == first_run.STATE_LEGACY

    root.destroy()
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
