"""官网 BGM 测试：随机起步、唱片机、跨页面不中断、循环。"""
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
PORT = 8899
CDP = 9555
EDGE = next((p for p in (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
) if os.path.exists(p)), None)
if not EDGE:
    print("no Edge")
    sys.exit(2)

srv = subprocess.Popen(
    [PY, "-m", "http.server", str(PORT), "--bind", "127.0.0.1", "--directory", "docs"],
    cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
profile = tempfile.mkdtemp(prefix="bgm_")
proc = subprocess.Popen([
    EDGE, "--headless=new", f"--remote-debugging-port={CDP}",
    f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
    "--disable-gpu", "--mute-audio", "--autoplay-policy=no-user-gesture-required",
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

    def js(expr, gesture=True):
        r = cdp.call("Runtime.evaluate", {
            "expression": expr, "returnByValue": True,
            "awaitPromise": True, "userGesture": gesture,
        })
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"])
        return r["result"].get("value")

    time.sleep(1.2)
    info = js("(() => { const a=document.querySelector('audio');"
              "return {player: !!document.querySelector('#bgm-player'),"
              "src: a ? a.src.split('/').pop() : '',"
              "paused: a ? a.paused : null,"
              "playingClass: document.querySelector('#bgm-player').classList.contains('playing')}; })()")
    print("初始:", info)
    assert info["player"], "没有唱片机"
    assert info["src"] in ("bgm-1.mp3", "bgm-2.mp3"), info
    assert info["paused"] is False, "应该自动播放（测试浏览器已放开自动播放）"

    time.sleep(2.0)
    t1 = js("document.querySelector('audio').currentTime")
    print("播放进度:", round(t1, 2))
    assert t1 > 0.1

    # 点击「功能」：无刷新换页，音乐应继续
    js("document.querySelector('.nav-links a[href=\"features.html\"]').click()")
    time.sleep(1.2)
    nav = js("({path: location.pathname.split('/').pop(),"
             "title: document.title,"
             "player: !!document.querySelector('#bgm-player'),"
             "paused: document.querySelector('audio').paused,"
             "time: document.querySelector('audio').currentTime,"
             "navEntries: performance.getEntriesByType('navigation').length,"
             "h1: document.querySelector('main h1') ? document.querySelector('main h1').textContent : ''})")
    print("跳转功能页:", nav)
    assert nav["path"] == "features.html"
    assert "功能" in nav["title"]
    assert nav["player"] and nav["paused"] is False
    assert nav["time"] > t1, "换页后进度应继续"
    assert nav["navEntries"] == 1, "不应整页刷新"
    assert "术式" in nav["h1"] or nav["h1"]

    # 再点「下载」
    js("document.querySelector('.nav-links a[href=\"download.html\"]').click()")
    time.sleep(1.0)
    nav2 = js("({path: location.pathname.split('/').pop(),"
              "paused: document.querySelector('audio').paused,"
              "time: document.querySelector('audio').currentTime})")
    print("跳转下载页:", nav2)
    assert nav2["path"] == "download.html" and nav2["paused"] is False

    # 返回上一页（popstate）
    js("history.back()")
    time.sleep(1.2)
    back = js("({path: location.pathname.split('/').pop(),"
              "paused: document.querySelector('audio').paused})")
    print("后退:", back)
    assert back["path"] == "features.html" and back["paused"] is False

    # 循环：模拟当前曲目结束，应切到另一首
    before = js("document.querySelector('audio').src.split('/').pop()")
    js("document.querySelector('audio').dispatchEvent(new Event('ended'))")
    time.sleep(1.0)
    after = js("document.querySelector('audio').src.split('/').pop()")
    print("循环切歌:", before, "->", after)
    assert before != after, "ended 后应切换曲目"

    # 截图
    shot = cdp.call("Page.captureScreenshot", {"format": "png"})
    import base64
    os.makedirs(os.path.join(HERE, "shots"), exist_ok=True)
    with open(os.path.join(HERE, "shots", "site_bgm.png"), "wb") as f:
        f.write(base64.b64decode(shot["data"]))
    print("截图已保存")
    cdp.close()
    print("RESULT: PASS")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
    srv.terminate()
    try:
        srv.wait(timeout=5)
    except Exception:
        srv.kill()
