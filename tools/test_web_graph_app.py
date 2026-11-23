"""图形+填空题的端到端测试（headless mock）。

模拟 Pearson：题干有两个函数、两个 eqEditor、一个内嵌 xygraph、一个放大弹窗。
验证 App 会：多路求解填空 -> 填两个框 -> 用 GraphControl API 画两条函数 ->
保存放大图 -> Check -> 收工；且绝不会点页面顶部 Save。
"""
import json
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

LLM_PORT = 8778
PAGE_PORT = 8779
CDP_PORT = 9334

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def fake_paste_math(self, text):
    """测试页没有 Pearson 的粘贴事件，直接把文本写进当前编辑框。"""
    js = ("(() => { const a = document.activeElement; if (!a) return 'no';"
          " a.innerText = %s;"
          " a.dispatchEvent(new Event('input', {bubbles: true}));"
          " return 'ok'; })()") % json.dumps(text)
    self.js(js)
    return True


llm_srv = serve(LLM_PORT)
page_srv = serve(PAGE_PORT)
web.WebPlayer.paste_math = fake_paste_math

edge = next((p for p in EDGE_CANDIDATES if os.path.exists(p)), None)
if not edge:
    print("没找到 Edge，跳过")
    llm_srv.shutdown()
    page_srv.shutdown()
    sys.exit(2)

profile = tempfile.mkdtemp(prefix="shinichi_graph_")
proc = subprocess.Popen([
    edge, "--headless=new", f"--remote-debugging-port={CDP_PORT}",
    f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
    "--disable-gpu", f"http://127.0.0.1:{PAGE_PORT}/graphquiz",
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
    app.trans_var.set(False)
    app.web_var.set(True)
    app._toggle_web()

    status_log = []
    done = False
    deadline = time.time() + 150
    while time.time() < deadline:
        root.update()
        app._pump()
        s = app.status_var.get()
        if not status_log or status_log[-1] != s:
            status_log.append(s)
            print(f"[{len(status_log):02d}] {s[:100]}")
        if "收工" in s:
            done = True
            break
        time.sleep(0.2)

    root.update()
    app._pump()
    ans = app._panel_text("ans")
    print("\n=== 答案面板 ===")
    print(ans[:600])

    # 页面侧证据：图形对象已写入、放大图已 Save、页面顶部 Save 没被点
    drv = web.WebPlayer(CDP_PORT).connect()
    page_js = (
        "(() => ({saved: !!window.__saved, valid: !!window.__graphValid,"
        " objects: (window.__objects || []).map(o => o.objectType),"
        " topSaveClicks: window.__topSaveClicks || 0,"
        " popupSaveClicks: window.__popupSaveClicks || 0,"
        " checkDisabled: (document.getElementById('check') || {}).disabled,"
        " f1: (document.getElementById('f1') || {}).innerText,"
        " f2: (document.getElementById('f2') || {}).innerText}))()")
    try:
        page_state = drv.eval_main(page_js)
    except Exception:
        page_state = drv.js(page_js)
    print("\n=== 图形页状态 ===")
    print(page_state)
    drv.close()

    ok = (done and "第 1 题" in ans
          and isinstance(page_state, dict) and page_state.get("saved")
          and len(page_state.get("objects") or []) >= 2
          and page_state.get("topSaveClicks") == 0
          and (page_state.get("popupSaveClicks") or 0) >= 1)

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
