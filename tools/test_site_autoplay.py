"""自动播放被拦截时的兜底：点页面任意处就能出声，不必找唱片机。"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from modules import web  # noqa: E402

PY = sys.executable
PORT = 8898
CDP = 9556
EDGE = next((p for p in (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
) if os.path.exists(p)), None)
if not EDGE:
    print("no Edge")
    sys.exit(2)

srv = subprocess.Popen([PY, "-m", "http.server", str(PORT), "--bind", "127.0.0.1",
                        "--directory", "docs"], cwd=ROOT,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
profile = tempfile.mkdtemp(prefix="bgm_block_")
proc = subprocess.Popen([
    EDGE, "--headless=new", f"--remote-debugging-port={CDP}",
    f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
    "--disable-gpu", "--mute-audio",
    f"http://127.0.0.1:{PORT}/index.html",
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

try:
    for _ in range(40):
        time.sleep(0.4)
        try:
            pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{CDP}/json/list", timeout=2))
            if pages:
                break
        except Exception:
            pass
    else:
        raise RuntimeError("Edge CDP 没起来")

    target = next((p for p in pages if "index.html" in p.get("url", "")), pages[0])
    cdp = web.CDP(target["webSocketDebuggerUrl"])
    cdp.call("Runtime.enable")
    cdp.call("Page.enable")

    def js(expr):
        r = cdp.call("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                          "awaitPromise": True})
        return r["result"].get("value")

    time.sleep(2.0)
    before = js("(() => { const a=document.querySelector('audio');"
                "return {paused:a.paused, muted:a.muted, time:+a.currentTime.toFixed(2),"
                "tip:document.querySelector('.bgm-tip').textContent}; })()")
    print("首次打开:", before)

    # 真实鼠标点击页面空白处（不是唱片机）
    cdp.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": 20, "y": 20,
                                          "button": "left", "clickCount": 1})
    cdp.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": 20, "y": 20,
                                          "button": "left", "clickCount": 1})
    time.sleep(1.2)
    after = js("(() => { const a=document.querySelector('audio');"
               "return {paused:a.paused, muted:a.muted, time:+a.currentTime.toFixed(2),"
               "tip:document.querySelector('.bgm-tip').textContent}; })()")
    print("点击任意处后:", after)
    assert after["paused"] is False, "点击页面后应开始播放"
    assert after["muted"] is False, "点击页面后应取消静音"
    assert after["time"] > 0.1

    cdp.close()
    print("RESULT: PASS")
finally:
    proc.terminate()
    try: proc.wait(timeout=5)
    except Exception: proc.kill()
    srv.terminate()
    try: srv.wait(timeout=5)
    except Exception: srv.kill()
