"""本地 mock：模拟 OpenAI 兼容平台，用于无外网时的端到端测试。"""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OCR_TEXT = (
    "Give the domain of the function defined as follows.\n"
    "f(x) = $\\sqrt{361 - x^2}$\n\n"
    "What inequality must x satisfy in order for x to be in the domain of this function?\n"
    "A. $x^2 > 361$\nB. $x \\le 361$\nC. $0 \\le x \\le 19$\nD. $x \\ge 361$\n"
    "E. $0 < x < 19$\nF. $x^2 \\le 361$\nG. $x^2 < 361$\nH. $x^2 \\ge 361$"
)
TRANS_TEXT = (
    "求如下函数的定义域。\n\nf(x) = √(361 − x²)\n\n"
    "要使 x 属于该函数的定义域，x 必须满足哪个不等式？\n"
    "A. x² > 361\nB. x ≤ 361\nC. 0 ≤ x ≤ 19\nD. x ≥ 361\n"
    "E. 0 < x < 19\nF. x² ≤ 361\nG. x² < 361\nH. x² ≥ 361"
)
WEB_ANSWER = "CHOICE: B\nMATRIX: ->\nVALUE: ->"
GRAPH_ANSWER = "VALUE: (5,25); 18\nMATRIX: ->\nCHOICE: ->"

ANSWER_TEXT = (
    "【答案】F. $x^2 \\le 361$\n"
    "【解析】根号内的表达式必须非负，所以 361 − x² ≥ 0，即 x² ≤ 361，"
    "也就是 −19 ≤ x ≤ 19。选项 F 是唯一与之一致的表述。"
)


QUIZ_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>HW Quiz</title>
<style>
body{font-family:sans-serif;padding:20px}
#fbDialog{display:none;position:fixed;left:20px;top:160px;background:#fff;padding:10px;border:1px solid #000}
</style></head><body>
<div id="q">-</div>
<div><label><input type="radio" id="rA" name="q" aria-label="A. choice A"> A</label></div>
<div><label><input type="radio" id="rB" name="q" aria-label="B. choice B"> B</label></div>
<div><label><input type="radio" id="rC" name="q" aria-label="C. choice C"> C</label></div>
<div style="margin:12px 0">
  <span class="eqEditor" id="f1" aria-label="answer box"
        style="display:none;height:26px;width:180px;border:1px solid #999"></span>
</div>
<div>
  <button id="check">Check answer</button>
  <button id="next">Next</button>
</div>
<div id="fbDialog" role="dialog"><span id="fbText">Well done!</span> <button id="ok">OK</button></div>
<script>
const QUESTIONS = [
  { text: 'Q1: What is 1 + 1 ?', correct: 'B' },
  { text: 'Q2: What is 2 + 2 ?', correct: 'A' },
  { text: 'Q3: What is 3 + 3 ?', correct: 'B' },
];
let idx = 0;
const qEl = document.getElementById('q');
const nextBtn = document.getElementById('next');

function render() {
  const q = QUESTIONS[idx];
  qEl.textContent = q.text;
  document.querySelectorAll('input[type=radio]').forEach((r) => { r.checked = false; r.disabled = false; });
  nextBtn.style.display = (idx < QUESTIONS.length - 1) ? 'inline-block' : 'none';
  document.getElementById('fbDialog').style.display = 'none';
}
render();

document.getElementById('check').addEventListener('click', function () {
  const picked = [...document.querySelectorAll('input[type=radio]')].find((r) => r.checked);
  const ok = picked && picked.getAttribute('aria-label').trim().toUpperCase().startsWith(QUESTIONS[idx].correct);
  document.getElementById('fbText').textContent = ok ? 'Well done!' : 'Incorrect, try again';
  document.getElementById('fbDialog').style.display = 'block';
});
document.getElementById('ok').addEventListener('click', function () {
  document.getElementById('fbDialog').style.display = 'none';
});
nextBtn.addEventListener('click', function () {
  idx = Math.min(idx + 1, QUESTIONS.length - 1);
  render();
});
</script>
</body></html>"""



GRAPH_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Graph Quiz</title>
<style>
body{font-family:sans-serif;padding:16px;width:760px}
#contentHolderbottom{margin-top:10px}
.eqEditor{display:inline-block;min-width:130px;height:24px;border:1px solid #999;padding:2px 4px}
#GraphZoomPopup_1{display:none;position:fixed;left:30px;top:60px;z-index:99;background:#fff;border:2px solid #000;padding:10px}
#fbDialog{display:none;position:fixed;left:30px;top:400px;background:#fff;padding:12px;border:1px solid #000}
</style></head><body>
<div id="contentHoldertop">
  <p>GRAPHQUIZ: Let C(x) be the cost to produce x batches, and let R(x) be the revenue.</p>
  <p>R(x) = -x^2 + 10x, C(x) = x + 18</p>
  <p>(a) Graph both functions. Identify the vertex of R(x).</p>
  <p>Identify the y-intercept of C(x).</p>
</div>
<div id="contentHolderbottom">
  <div><span class="eqEditor" id="f1" contenteditable="true" aria-label="The vertex of R(x) is at" style="min-width:130px"></span></div>
  <div><span class="eqEditor" id="f2" contenteditable="true" aria-label="The y-intercept of C(x) is at y=" style="min-width:100px"></span></div>
  <button id="enlarge">Click to enlarge graph</button>
  <div class="graphControl" style="width:340px;height:280px;margin-top:8px;background:#eef">
    <div class="xygraph" id="g1" style="width:340px;height:280px;position:relative">
      <div data-dojo-props='orientation:"horizontal", minimum:0, maximum:20'></div>
      <div data-dojo-props='orientation:"vertical", minimum:0, maximum:40'></div>
    </div>
  </div>
</div>
<div id="GraphZoomPopup_1">
  <div class="xygraph" id="popGraph" style="width:380px;height:250px;background:#fff"></div>
  <button id="psave">Save</button>
</div>
<div><button id="pageSave">Save</button><button id="check" disabled>Check answer</button><button id="next" style="display:none">Next</button></div>
<div id="fbDialog" role="dialog"><span id="fbText">Your answer is correct.</span> <button id="ok">OK</button></div>
<script>
window.__objects = null;
window.__saved = false;
window.__graphValid = false;
window.__topSaveClicks = 0;
window.__popupSaveClicks = 0;
const f1 = document.getElementById('f1'), f2 = document.getElementById('f2');
const check = document.getElementById('check');
function updateCheck() {
  check.disabled = !(f1.innerText.trim() && f2.innerText.trim() && window.__saved);
}
function hidePopup() {
  const p = document.getElementById('GraphZoomPopup_1');
  if (p) p.style.display = 'none';
}
function saveGraph() {
  window.__popupSaveClicks++;
  window.__saved = true;
  hidePopup();
  updateCheck();
}
const mgr = {
  clearGraphObjects: function () {},
  initGraphObjects: function (o) { window.__objects = o; window.__graphValid = true; }
};
const ctl = {
  getGraphManager: function () { return mgr; },
  getGraph: function () { return { validateGraph: function () { window.__graphValid = true; } }; }
};
window.dijit = {
  byId: function (id) {
    if (id === 'g1' || id === 'popGraph') return {_graphControl: ctl, hide: hidePopup};
    if (id === 'GraphZoomPopup_1') return {hide: hidePopup};
    if (id === 'psave') return {onClick: saveGraph};
    return null;
  }
};
document.getElementById('enlarge').addEventListener('click', function () {
  document.getElementById('GraphZoomPopup_1').style.display = 'block';
});
document.getElementById('pageSave').addEventListener('click', function () {
  window.__topSaveClicks++;
});
document.getElementById('psave').addEventListener('click', saveGraph);
f1.addEventListener('input', updateCheck);
f2.addEventListener('input', updateCheck);
document.getElementById('check').addEventListener('click', function () {
  const got1 = f1.innerText.replace(/\\s+/g, '');
  const got2 = f2.innerText.replace(/\\s+/g, '');
  const good = window.__saved && window.__objects && window.__objects.length >= 2
    && got1.indexOf('5') >= 0 && got1.indexOf('25') >= 0 && got2.indexOf('18') >= 0;
  document.getElementById('fbText').textContent =
    good ? 'Your answer is correct.' : 'Incorrect, try again';
  document.getElementById('fbDialog').style.display = 'block';
});
document.getElementById('ok').addEventListener('click', function () {
  document.getElementById('fbDialog').style.display = 'none';
});
</script>
</body></html>"""



class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _html(self, text):
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/graphquiz"):
            self._html(GRAPH_HTML)
            return
        if self.path.rstrip("/").endswith("/quiz"):
            self._html(QUIZ_HTML)
            return
        if self.path.rstrip("/").endswith("/models"):
            self._json(200, {"data": [{"id": "mock-vision"}, {"id": "mock-chat"},
                                      {"id": "mock-reasoner"}, {"id": "no-effort-model"}]})
        else:
            self._json(404, {"error": {"message": "not found"}})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(n) or b"{}")
        model = payload.get("model", "")
        effort = payload.get("reasoning_effort")

        if model == "no-effort-model" and effort:
            self._json(400, {"error": {"message": "Unsupported parameter: reasoning_effort"}})
            return
        if model == "bad-key":
            self._json(401, {"error": {"message": "invalid api key"}})
            return

        msgs = payload.get("messages") or []
        joined = json.dumps(msgs, ensure_ascii=False)
        has_image = "image_url" in joined
        if has_image:
            text = OCR_TEXT
        elif "翻译" in joined:
            text = TRANS_TEXT
        elif "C(x)=x+18" in joined.replace(" ", "") or "GRAPHQUIZ" in joined:
            text = GRAPH_ANSWER
        elif "CHOICE:" in joined:
            text = WEB_ANSWER
        else:
            text = ANSWER_TEXT

        if model == "mock-reasoner" and not payload.get("stream"):
            pass

        if not payload.get("stream"):
            self._json(200, {
                "id": "mock", "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            })
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        def send(obj):
            self.wfile.write(("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8"))
            self.wfile.flush()

        if model == "mock-reasoner":
            reasoning = "先看根号下的表达式必须非负，所以要 361−x² ≥ 0，也就是 x² ≤ 361。"
            for i in range(0, len(reasoning), 8):
                send({"choices": [{"delta": {"reasoning_content": reasoning[i:i + 8]}}]})
                time.sleep(0.01)

        for i in range(0, len(text), 10):
            send({"choices": [{"delta": {"content": text[i:i + 10]}}]})
            time.sleep(0.01)
        send({"choices": [{"delta": {}}], "usage": {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200}})
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def serve(port: int = 8765) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    s = serve(port)
    print(f"mock server on http://127.0.0.1:{port}/v1")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        s.shutdown()

