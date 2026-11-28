"""升级不重弹，只有安装器重装标记才重走契约。"""
from __future__ import annotations

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import tkinter as tk

CFG = tempfile.mkdtemp(prefix="sch_reinstall_marker_")
os.environ["SHINICHI_CONFIG_DIR"] = CFG
os.environ["APPDATA"] = CFG
os.environ["LOCALAPPDATA"] = os.path.join(CFG, "local")
os.environ["SHINICHI_ALLOW_MULTI"] = "1"
if "--test-config" not in sys.argv:
    sys.argv.append("--test-config")

from app import App  # noqa: E402
from modules import first_run, settings  # noqa: E402


def pump(root: tk.Tk, seconds: float = 0.3) -> None:
    import time

    end = time.time() + seconds
    while time.time() < end:
        root.update_idletasks()
        root.update()
        time.sleep(0.02)


def main() -> None:
    root = tk.Tk()
    root.withdraw()
    app = App(root)

    # 升级：config 里 done，且残留旧的 onboarding_reinstall。
    app.cfg["onboarding_state"] = first_run.STATE_DONE
    app.cfg["onboarding_reinstall"] = True
    app.cfg["onboarding_version"] = settings.APP_VERSION
    settings.save(app.cfg)
    app.cfg = settings.load()
    app._apply_onboarding_request()
    pump(root)
    assert app.cfg["onboarding_reinstall"] is False
    assert app.cfg["onboarding_state"] == first_run.STATE_DONE
    assert first_run.should_show(app.cfg, "licensed", True) is False

    # 新装/重装：安装器标记存在，只消费一次，并且重置引导。
    marker = first_run.onboarding_request_path()
    os.makedirs(os.path.dirname(marker), exist_ok=True)
    with open(marker, "w", encoding="utf-8") as f:
        f.write('{"reason":"fresh_or_reinstall"}')
    app._apply_onboarding_request()
    pump(root)
    assert not os.path.exists(marker)
    assert app.cfg["onboarding_reinstall"] is True
    assert app.cfg["onboarding_state"] == first_run.STATE_PENDING
    assert first_run.should_show(app.cfg, "licensed", True) is True

    # 消费后再次启动：不重复弹。
    app.cfg["onboarding_reinstall"] = False
    settings.save(app.cfg)
    app.cfg = settings.load()
    app._apply_onboarding_request()
    pump(root)
    assert app.cfg["onboarding_reinstall"] is False
    assert first_run.should_show(app.cfg, "licensed", True) is False

    root.destroy()
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
