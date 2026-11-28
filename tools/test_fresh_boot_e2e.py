"""Regression: a fresh activation must launch the setup wizard before the main UI.

This drives the real app.boot() path with an isolated APPDATA, a fake activation
dialog and a fake license state machine, so it does not touch the user's profile
or pop a real activation window.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import tkinter as tk

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

tmp = tempfile.mkdtemp(prefix="sch_fresh_boot_")
os.environ["APPDATA"] = tmp
os.environ["LOCALAPPDATA"] = os.path.join(tmp, "local")
# 这是一个独立的测试实例；正式单实例会把它当成第二个窗口。
os.environ["SHINICHI_ALLOW_MULTI"] = "1"

import app  # noqa: E402
from modules import license as lic  # noqa: E402
from modules import setup_wizard, onboarding  # noqa: E402
from modules import update as upd  # noqa: E402

seen: dict[str, object] = {"setup": None, "onboarding": None, "errors": []}
calls = {"n": 0}
update_calls: list[int] = []


def fake_check_access(update=True):
    calls["n"] += 1
    if calls["n"] == 1:
        return "fresh", "首次安装", 0
    return "trial", "五天试用", 5


def fake_activation(root, reason="", allow_trial=False):
    return True


def fake_status():
    return "trial", "五天试用", 5


def capture(root):
    try:
        from PIL import ImageGrab
        ImageGrab.grab().save(os.path.join(ROOT, "tools", "shots", "fresh_boot_setup.png"))
    except Exception as exc:
        seen["errors"].append("screenshot: " + repr(exc))
    try:
        for w in root.winfo_children():
            if isinstance(w, setup_wizard.SetupWizard):
                seen["setup"] = True
                try:
                    w.destroy()
                except Exception:
                    pass
            elif isinstance(w, onboarding.OnboardingWizard):
                seen["onboarding"] = True
                try:
                    w.destroy()
                except Exception:
                    pass
    except Exception as exc:
        seen["errors"].append(repr(exc))
    try:
        root.destroy()
    except Exception:
        pass


orig_tk = tk.Tk
orig_show_activation = app.show_activation
orig_check_access = lic.check_access
orig_status = lic.status
orig_update_check = upd.check
try:
    lic.check_access = fake_check_access
    lic.status = fake_status
    app.show_activation = fake_activation

    def fake_update_check(*args, **kwargs):
        update_calls.append(1)
        return {"version": "9.9.9", "tag": "v9.9.9", "notes": "", "url": ""}

    upd.check = fake_update_check

    def make_root():
        r = orig_tk()
        r.withdraw()
        r.after(5500, lambda: capture(r))
        return r

    app.tk.Tk = make_root
    app.main()
finally:
    app.tk.Tk = orig_tk
    app.show_activation = orig_show_activation
    lic.check_access = orig_check_access
    lic.status = orig_status
    upd.check = orig_update_check
    shutil.rmtree(tmp, ignore_errors=True)

print("seen:", seen)
assert not seen["errors"], seen["errors"]
assert seen["setup"] is True, "fresh activation did not open SetupWizard"
assert not update_calls, "first launch must not check for updates"
print("RESULT: PASS")
