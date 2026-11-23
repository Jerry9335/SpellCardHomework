"""反馈弹窗状态机回归（参考 Auto-Pearson completionState）。

验证：
- 成功弹窗 visibleFeedback 优先于页面旧 Check；
- Next 只从弹窗内部取，不点弹窗背后的旧 Next；
- 离开警告识别为 leave，不当成答对。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from modules import web  # noqa: E402

PAGE_PORT = 8781
CDP_PORT = 9335

HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Feedback</title>
<style>
#fbDialog{position:fixed;left:20px;top:80px;background:#fff;padding:12px;border:1px solid #000}
</style></head><body>
<span id="mathFormula" data-latex="\\frac{x+2}{x-5}">x+2 / x-5</span>
<label><input type="radio" name="q" id="rA" aria-label="A. 10%"> A</label>
<label><input type="radio" name="q" id="rB" aria-label="B. 20%"> B</label>
<button id="pageSave">Save</button>
<button id="check">Check answer</button>
<button id="oldNext">Next</button>
<div id="fbDialog" role="dialog">
  <span id="fbText">Good job!</span>
  <button id="ok">OK</button>
  <button id="next">Next question</button>
</div>
<script>
window.__checkClicks = 0;
window.__oldNextClicks = 0;
window.__okClicks = 0;
window.__nextClicks = 0;
document.getElementById('check').addEventListener('click', () => window.__checkClicks++);
document.getElementById('oldNext').addEventListener('click', () => window.__oldNextClicks++);
document.getElementById('ok').addEventListener('click', () => {
  window.__okClicks++;
  document.getElementById('fbDialog').style.display = 'none';
});
document.getElementById('next').addEventListener('click', () => window.__nextClicks++);
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        data = HTML.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_a):
        pass


EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def main() -> int:
    edge = next((p for p in EDGE_CANDIDATES if os.path.exists(p)), None)
    if not edge:
        print("没找到 Edge，跳过")
        return 2
    srv = ThreadingHTTPServer(("127.0.0.1", PAGE_PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    profile = tempfile.mkdtemp(prefix="shinichi_fb_")
    proc = subprocess.Popen([
        edge, "--headless=new", f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
        "--disable-gpu", f"http://127.0.0.1:{PAGE_PORT}/",
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
        drv = web.WebPlayer(CDP_PORT).connect()
        for _ in range(20):
            time.sleep(0.3)
            if drv.state().get("hasCheck") or drv.completion_state().get("kind") != "none":
                break
        cs = drv.completion_state()
        print("completion:", cs)
        assert cs.get("kind") == "correct", cs
        assert cs.get("hasOk") is True, cs
        assert cs.get("hasNext") is True, cs
        assert cs.get("checkEnabled") is True, cs
        math = drv.math_text()
        print("math:", math)
        assert any("frac{x+2}" in m for m in math), math

        # 只点弹窗 OK；页面旧 Check / 旧 Next 都不能被点
        assert drv.dismiss_feedback() == "ok"
        time.sleep(0.3)
        vals = drv.eval_main("(() => ({c: window.__checkClicks, o: window.__oldNextClicks,"
                              " ok: window.__okClicks, n: window.__nextClicks}))()")
        print("after dismiss:", vals)
        assert vals["c"] == 0 and vals["o"] == 0 and vals["ok"] == 1, vals
        assert drv.completion_state().get("kind") == "none"

        # choiceIndex 集成：B. 20% 必须点中 B，不能按位置/首字母瞎点
        assert drv.pick_choice("B. 20%") == "ok"
        picked = drv.eval_main("(() => ({a: document.getElementById('rA').checked,"
                               " b: document.getElementById('rB').checked}))()")
        print("choice:", picked)
        assert picked["b"] is True and picked["a"] is False, picked
        assert drv.pick_choice("C") == "no-match"

        # Pearson 残留反馈：Dojo 已认为弹窗关闭，但 DOM 还显示；必须兜底隐藏
        drv.eval_main("""(() => {
          window.dijit = {byId: () => ({open: false})};
          const d = document.createElement('div');
          d.id = 'staleFeedback'; d.className = 'feedbackDialog';
          d.innerHTML = '<div>Good job!</div><button id="staleOk">OK</button>';
          document.body.appendChild(d); return 'ok';
        })()""")
        assert drv.dismiss_feedback() == "ok-stale"
        stale = drv.eval_main("document.getElementById('staleFeedback').style.display")
        print("stale display:", stale)
        assert stale == "none", stale

        # 离开警告：识别为 leave，不当作答对
        drv.eval_main("""(() => {
          window.__leaveNo = 0; window.__leaveYes = 0;
          const d = document.createElement('div');
          d.id = 'leaveDialog'; d.setAttribute('role','dialog');
          d.innerHTML = '<div>You have not completed this question; you will receive credit only for the work you have done. Are you sure you want to leave this question?</div>'
            + '<button id="yes">Yes</button><button id="no">No</button>';
          d.querySelector('#no').addEventListener('click', () => { window.__leaveNo++; });
          d.querySelector('#yes').addEventListener('click', () => { window.__leaveYes++; });
          document.body.appendChild(d); return 'ok';
        })()""")
        cs2 = drv.completion_state()
        print("leave:", cs2.get("kind"), cs2.get("text")[:80])
        assert cs2.get("kind") == "leave", cs2
        ls = drv.leave_state()
        print("leave state:", ls)
        assert ls.get("visible") is True and ls.get("kind") == "incomplete", ls
        assert ls.get("yes_count") == 1 and ls.get("no_count") == 1, ls
        assert drv.click_leave("no") == "ok"
        time.sleep(0.2)
        vals = drv.eval_main("(() => ({no: window.__leaveNo, yes: window.__leaveYes}))()")
        print("leave clicked:", vals)
        assert vals["no"] == 1 and vals["yes"] == 0, vals

        # 另一类警告：答案还没检查就离开；必须精确识别为 unchecked
        drv.eval_main("""(() => {
          const d = document.createElement('div');
          d.id = 'uncheckedDialog'; d.setAttribute('role','dialog');
          d.style.cssText = 'position:fixed;left:20px;top:200px;width:500px;height:180px;background:#fff;z-index:99';
          d.innerHTML = '<div>You will not receive any credit for this attempt until you have checked your answer. Are you sure you want to continue without checking your answer?</div>'
            + '<button id="uyes">Yes</button><button id="uno">No</button>';
          document.body.appendChild(d); return 'ok';
        })()""")
        time.sleep(0.2)
        ls2 = drv.leave_state()
        print("unchecked state:", ls2)
        assert ls2.get("visible") is True and ls2.get("kind") == "unchecked", ls2
        drv.eval_main("document.getElementById('leaveDialog').remove()")
        drv.eval_main("document.getElementById('uncheckedDialog').remove()")
        drv.close()
        ok = True
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=6)
        except Exception:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)
        srv.shutdown()
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
