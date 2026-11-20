"""全自动模式端到端测试（用独立 headless 浏览器，绝不碰用户正在用的窗口）。

3 道题连续作答：Q1 答对 -> Next -> Q2 答错（继续）-> Next -> Q3 答对 -> 收工。
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.environ.setdefault("SHINICHI_CONFIG_DIR", os.path.join(HERE, ".test_config"))
sys.path.insert(0, ROOT)

import tkinter as tk

from app import App
from modules import capture, web
from tools.mock_server import serve

LLM_PORT = 8776
PAGE_PORT = 8777
CDP_PORT = 9333

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

llm_srv = serve(LLM_PORT)
page_srv = serve(PAGE_PORT)

edge = next((p for p in EDGE_CANDIDATES if os.path.exists(p)), None)
if not edge:
    print("没找到 Edge，跳过")
    llm_srv.shutdown()
    page_srv.shutdown()
    sys.exit(2)

profile = tempfile.mkdtemp(prefix="shinichi_auto_")
proc = subprocess.Popen([
    edge, "--headless=new", f"--remote-debugging-port={CDP_PORT}",
    f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
    "--disable-gpu", f"http://127.0.0.1:{PAGE_PORT}/quiz",
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

ok = False
try:
    for _ in range(40):
        time.sleep(0.5)
        try:
            web.cdp_pages(CDP_PORT)
            break
        except Exception:
            pass
    else:
        raise RuntimeError("测试浏览器没起来")

    capture.make_dpi_aware()
    root = tk.Tk()
    root.withdraw()
    app = App(root)
    app.base_var.set(f"http://127.0.0.1:{LLM_PORT}/v1")
    app.key_var.set("test-key")
    app.model_var.set("mock-chat")
    app.vision_var.set("（使用答题模型）")
    app.web_port_var.set(CDP_PORT)
    app.continue_wrong_var.set(True)
    app.trans_var.set(True)          # 全自动也要翻译

    app.web_var.set(True)
    app._toggle_web()

    status_log = []
    done = False
    deadline = time.time() + 120
    while time.time() < deadline:
        root.update()
        app._pump()
        s = app.status_var.get()
        if not status_log or status_log[-1] != s:
            status_log.append(s)
            print(f"[{len(status_log):02d}] {s[:80]}")
        if "收工" in s:
            done = True
            break
        time.sleep(0.2)

    root.update()
    app._pump()
    ans = app._panel_text("ans")
    trans = app._panel_text("trans")
    print("\n=== 答案面板 ===")
    print(ans[:500])
    print("\n=== 翻译面板 ===")
    print(trans[:200])
    print("\n=== 状态 ===")
    print(app.status_var.get())

    q_count = sum(1 for n in (1, 2, 3) if f"【第 {n} 题】" in ans)
    ok = (done and q_count >= 3 and "对 2" in app.status_var.get()
          and "错 1" in app.status_var.get() and len(trans.strip()) > 0)
    print(f"\n处理题数: {q_count}/3 | 翻译: {'有' if trans.strip() else '无'}")

    app.web_var.set(False)
    app._toggle_web()
    app.web_stop.set()
    try:
        app.hotkeys.stop()
        if app.clip_watcher:
            app.clip_watcher.stop()
    except Exception:
        pass
    root.destroy()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=6)
    except Exception:
        proc.kill()
    shutil.rmtree(profile, ignore_errors=True)
    llm_srv.shutdown()
    page_srv.shutdown()

print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
