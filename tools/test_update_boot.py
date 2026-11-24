"""Regression: subsequent launches check for updates exactly once."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

tmp = tempfile.mkdtemp(prefix="sch_update_boot_")
os.environ["APPDATA"] = tmp
os.environ["LOCALAPPDATA"] = os.path.join(tmp, "local")
cfg_dir = os.path.join(tmp, "SpellCardHomework")
os.makedirs(cfg_dir, exist_ok=True)
with open(os.path.join(cfg_dir, "config.json"), "w", encoding="utf-8") as fh:
    json.dump({
        "api_key": "sk-test-update-boot",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-flash",
        "onboarding_state": "done",
        "onboarding_version": "1.0.6-rc.04",
        "onboarding_resume_step": 9,
    }, fh)

import tkinter as tk  # noqa: E402

import app  # noqa: E402
from modules import license as lic  # noqa: E402
from modules import update as upd  # noqa: E402

calls: list[int] = []
seen = {"error": ""}
orig_tk = tk.Tk
orig_check_access = lic.check_access
orig_status = lic.status
orig_update_check = upd.check


def fake_check_access(update=True):
    return "licensed", "永久许可", 0


def fake_status():
    return "licensed", "永久许可", 0


def fake_update_check(*args, **kwargs):
    calls.append(1)
    return {
        "version": "1.0.6-rc.04",
        "tag": "v1.0.6-rc.04",
        "notes": "",
        "url": "https://example.invalid/releases",
        "source": "test",
    }


def make_root():
    root = orig_tk()
    root.withdraw()

    def finish():
        try:
            if len(calls) != 1:
                seen["error"] = f"expected exactly one update check, got {len(calls)}"
        finally:
            try:
                root.destroy()
            except Exception:
                pass

    root.after(6500, finish)
    return root


try:
    lic.check_access = fake_check_access
    lic.status = fake_status
    upd.check = fake_update_check
    app.tk.Tk = make_root
    app.main()
finally:
    app.tk.Tk = orig_tk
    lic.check_access = orig_check_access
    lic.status = orig_status
    upd.check = orig_update_check
    shutil.rmtree(tmp, ignore_errors=True)

assert not seen["error"], seen["error"]
print("RESULT: PASS")
