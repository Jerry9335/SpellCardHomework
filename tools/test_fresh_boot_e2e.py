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

import app  # noqa: E402
from modules import license as lic  # noqa: E402
from modules import setup_wizard, onboarding  # noqa: E402

seen: dict[str, object] = {"setup": None, "onboarding": None, "errors": []}
calls = {"n": 0}


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
try:
    lic.check_access = fake_check_access
    lic.status = fake_status
    app.show_activation = fake_activation

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
    shutil.rmtree(tmp, ignore_errors=True)

print("seen:", seen)
assert not seen["errors"], seen["errors"]
assert seen["setup"] is True, "fresh activation did not open SetupWizard"
print("RESULT: PASS")
