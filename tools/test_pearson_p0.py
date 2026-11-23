"""P0 Pearson 交互层回归：字段 UID/快照签名、唯一 Check、Dojo player 状态、跳过账本。"""
from __future__ import annotations

import json
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

from modules import skip_ledger, web  # noqa: E402

PAGE_PORT = 8783
CDP_PORT = 9337

HTML = """<!doctype html><html><head><meta charset="utf-8"><title>P0</title>
<style>
#oldCheckWrap{position:absolute;left:10px;top:10px}
#contentHolderbottom{padding:40px}
.eqEditor{display:inline-block;width:140px;height:24px;border:1px solid #999}
</style></head><body>
<div id="contentHoldertop">Question 1: Find the value.</div>
<div id="contentHolderbottom">
  <div id="oldCheckWrap"><button id="oldCheck">Check answer</button></div>
  <button id="check">Check answer</button>
  <div><span class="eqEditor" id="f1" aria-label="type your answer"></span></div>
  <div><span class="eqEditor" id="decoy" aria-label="enter your response here"
       style="opacity:0.5"></span></div>
  <label><input type="radio" name="q" id="rA" aria-label="A. 1"></label>
  <label><input type="radio" name="q" id="rB" aria-label="B. 2"></label>
  <div class="playerViewer" id="pv"></div>
  <div class="inputField" id="a1"></div>
</div>
<script>
window.__checkClicks = 0;
window.__oldCheckClicks = 0;
window.__checkClicksBy = {};
document.getElementById('check').addEventListener('click', () => {
  window.__checkClicks++; window.__checkClicksBy.check = (window.__checkClicksBy.check||0)+1;
});
document.getElementById('oldCheck').addEventListener('click', () => {
  window.__oldCheckClicks++; window.__checkClicksBy.old = (window.__checkClicksBy.old||0)+1;
});
window.__byNode = (el) => (el && el.__widget) || null;
window.dijit = {byNode: window.__byNode};
document.getElementById('pv').__widget = {
  _correctness: 'correct', feedbackOpened: false, resultsposted: 1
};
document.getElementById('a1').__widget = {
  isAnswered: true, isCorrect: true, answeredStates: ['correct']
};
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
    profile = tempfile.mkdtemp(prefix="shinichi_p0_")
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
            if drv.state().get("fields"):
                break

        st = drv.state()
        print("state keys:", sorted(st.keys()))
        print("inventory:", st.get("inventory"), "incomplete:", st.get("incomplete"))
        assert st.get("signature"), "缺少 signature"
        assert st.get("problemKey"), "缺少 problemKey"
        inv = st.get("inventory") or {}
        assert inv.get("rendered", 0) >= 4, inv
        assert inv.get("captured", 0) >= 4, inv
        assert st.get("incomplete") is False, st.get("inventory")
        fields = {str(f.get("id")): f for f in (st.get("fields") or [])}
        assert "f1" in fields and "decoy" in fields, fields
        assert fields["f1"].get("uid"), fields["f1"]
        assert fields["f1"].get("disabled") is False, fields["f1"]
        assert fields["decoy"].get("disabled") is True, fields["decoy"]
        uid = fields["f1"]["uid"]
        assert drv.field_present(uid) is True
        assert drv.field_present("u-does-not-exist") is False

        # 唯一 Check：当前有旧/新两颗，必须拒绝点
        chk = drv.check_state()
        print("check state:", chk)
        assert chk.get("count") == 2, chk
        assert drv.click_check_unique() == "multiple", chk
        time.sleep(0.3)
        counts = drv.eval_main("(() => ({n: window.__checkClicks, o: window.__oldCheckClicks}))()")
        print("after multiple:", counts)
        assert counts["n"] == 0 and counts["o"] == 0, counts

        drv.eval_main("document.getElementById('oldCheckWrap').style.display='none'")
        time.sleep(0.2)
        chk = drv.check_state()
        print("single check:", chk)
        assert chk.get("ok") is True, chk
        assert drv.click_check_unique() == "ok"
        time.sleep(0.3)
        counts = drv.eval_main("(() => ({n: window.__checkClicks, o: window.__oldCheckClicks}))()")
        print("after single:", counts)
        assert counts["n"] == 1 and counts["o"] == 0, counts

        # Dojo player 状态
        ps = drv.player_state()
        print("player:", ps)
        assert ps.get("ok") is True, ps
        assert str(ps.get("correctness")).lower() == "correct", ps
        assert ps.get("correct", 0) >= 1, ps

        # 真实 Pearson 常见的是 AMD registry 而不是全局 dijit：模拟异步 require，
        # player_state 应等待 registry 就绪后拿到同一份状态。
        drv.eval_main(
            "window.dijit=null; window.__schDijitRegistry=null;"
            "window.__schDijitLoading=false; window.__schDijitError='';"
            "window.require=(_deps,ok)=>setTimeout(()=>ok({byNode:window.__byNode}),180)")
        ps_amd = drv.player_state()
        print("player amd:", ps_amd)
        assert ps_amd.get("ok") is True, ps_amd
        assert str(ps_amd.get("correctness")).lower() == "correct", ps_amd

        # 页面变化必须改签名
        old_sig = st.get("signature")
        drv.eval_main("document.getElementById('contentHoldertop').textContent += ' changed'")
        time.sleep(0.2)
        st2 = drv.state()
        print("sig changed:", old_sig != st2.get("signature"))
        assert old_sig != st2.get("signature")

        # inventory：可见 .xlMultipleChoice 里一个可答控件都没有，必须报 incomplete
        drv.eval_main("""(() => {
          const d = document.createElement('div');
          d.className = 'xlMultipleChoice'; d.id = 'brokenGroup';
          d.textContent = 'broken question choices';
          document.getElementById('contentHolderbottom').appendChild(d);
        })()""")
        time.sleep(0.2)
        st_bad = drv.state()
        print("broken inventory:", st_bad.get("inventory"))
        assert st_bad.get("incomplete") is True, st_bad.get("inventory")
        drv.eval_main("document.getElementById('brokenGroup').remove()")
        time.sleep(0.2)
        assert drv.state().get("incomplete") is False

        # element 身份：UID 还在，但 DOM 被替换成新节点，必须判定旧快照失效
        drv.eval_main("""(() => {
          const uid = %s;
          const old = document.querySelector('[data-sch-uid="' + uid + '"]');
          if (!old) return 'no';
          const clone = old.cloneNode(true);
          clone.removeAttribute('data-sch-uid');
          old.replaceWith(clone);
          return 'ok';
        })()""" % json.dumps(uid))
        time.sleep(0.2)
        print("replaced field present:", drv.field_present(uid))
        assert drv.field_present(uid) is False

        # skip 账本：写失败不允许静默；正常写入可读回
        tmp = tempfile.mkdtemp(prefix="shinichi_ledger_")
        os.environ["APPDATA"] = tmp
        item = skip_ledger.record(15, [2, 7], reason="测试跳过", source="test")
        again = skip_ledger.record_once(15, [2, 7], reason="测试跳过", source="test")
        loaded = skip_ledger.load()
        print("ledger:", loaded)
        assert item["qno"] == 15 and item["part"] == [2, 7], item
        assert again["qno"] == 15, again
        assert len(loaded) == 1, loaded
        assert loaded[-1]["reason"] == "测试跳过", loaded
        skip_ledger.clear()
        shutil.rmtree(tmp, ignore_errors=True)
        ok = True
        print("RESULT: PASS")
        return 0
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            pass
        try:
            srv.shutdown()
        except Exception:
            pass
        shutil.rmtree(profile, ignore_errors=True)
        if not ok:
            print("RESULT: FAIL")


if __name__ == "__main__":
    raise SystemExit(main())
