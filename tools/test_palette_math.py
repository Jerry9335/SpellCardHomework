"""公式调色板按钮选择/More 展开的 headless 回归测试。

不依赖真实 Pearson 账号：用最小 DOM 模拟
- 可见调色板 + 隐藏调色板，确认不会点到隐藏的那个；
- 矩阵按钮在 More 第二页，确认 palette_click 会展开 More 后轮询到按钮。
"""
from __future__ import annotations

import os
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

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>
  body { margin: 20px; font-family: sans-serif; }
  .eqEditor { display:inline-block; width:180px; height:28px; border:1px solid #999; }
  .xlInlineMathPalette { position:absolute; left:240px; top:120px;
    width:220px; height:120px; background:#eee; border:1px solid #888; }
  .morePaletteNode { display:none; }
</style></head><body>
<span id="f1" class="eqEditor" contenteditable="true"></span>
<div id="palVisible" class="xlInlineMathPalette">
  <button class="toolButton iconFrac" id="frac" title="Fraction">Fraction</button>
  <button class="toolButton" id="more" title="More">More</button>
  <div class="morePaletteNode" id="moreNode">
    <button class="toolButton iconMatrix" id="matrix" title="Matrix">Matrix</button>
  </div>
</div>
<div id="palHidden" class="xlInlineMathPalette" style="visibility:hidden">
  <button class="toolButton iconMatrix" id="hiddenMatrix" title="Matrix">Hidden Matrix</button>
</div>
<div id="out" style="margin-top:220px"></div>
<div id="MatrixSizePopup_hidden" style="display:none">
  <input id="hr" value="2"><input id="hc" value="2"><button>OK</button>
</div>
<div id="MatrixSizePopup_visible" style="position:absolute; left:500px; top:220px;
     width:220px; height:100px; background:#ddd; border:1px solid #777;">
  <input id="vr" value="2"><input id="vc" value="2">
  <button onclick="this.parentElement.style.display='none'">Cancel</button>
  <button>OK</button>
</div>
<script>
  document.getElementById('more').addEventListener('click', () => {
    document.getElementById('moreNode').style.display = 'block';
  });
  document.getElementById('matrix').addEventListener('click', () => {
    document.getElementById('out').textContent = 'matrix-clicked';
  });
  document.getElementById('hiddenMatrix').addEventListener('click', () => {
    document.getElementById('out').textContent = 'hidden-clicked';
  });
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = PAGE.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def find_edge():
    for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if os.path.exists(p):
            return p
    return None


def main() -> int:
    edge = find_edge()
    if not edge:
        print("没找到 Edge，跳过")
        return 2
    srv = ThreadingHTTPServer(("127.0.0.1", 8791), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    profile = tempfile.mkdtemp(prefix="shinichi_palette_")
    proc = subprocess.Popen([
        edge, "--headless=new", "--disable-gpu", "--no-first-run",
        "--no-default-browser-check", "--remote-debugging-port=9341",
        f"--user-data-dir={profile}", "http://127.0.0.1:8791/",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    drv = None
    try:
        for _ in range(40):
            time.sleep(0.3)
            try:
                drv = web.WebPlayer(9341, log=lambda _m: None)
                drv.connect()
                break
            except Exception:
                drv = None
        if drv is None:
            raise RuntimeError("测试浏览器没起来")
        time.sleep(1.0)
        st = drv.state()
        if not (st.get("fields") or []):
            raise RuntimeError(f"没读到模拟 eqEditor：{st}")
        fid = st["fields"][0]["id"]
        drv.focus_field(fid)
        time.sleep(0.3)

        # 隐藏调色板里也有 iconMatrix；必须只点可见调色板里的那个。
        r1 = drv.palette_click(fid, ("iconMatrix",), r"matrix")
        time.sleep(0.3)
        out1 = (drv.js("document.getElementById('out').textContent") or "").strip()
        print(f"palette hidden/More: res={r1!r} out={out1!r}")
        assert r1 == "ok", r1
        assert out1 == "matrix-clicked", out1

        # 隐藏调色板不能自己变成可点目标。
        drv.js("document.getElementById('palVisible').style.display='none'")
        r2 = drv.palette_click(fid, ("iconMatrix",), r"matrix")
        out2 = (drv.js("document.getElementById('out').textContent") or "").strip()
        print(f"palette hidden only: res={r2!r} out={out2!r}")
        assert r2 == "no-palette", r2
        assert out2 == "matrix-clicked", out2

        # 隐藏的矩阵尺寸弹窗不能抢在可见弹窗前面。
        pop = drv.matrix_popup()
        print(f"matrix popup: {pop}")
        assert pop and pop.get("id") == "MatrixSizePopup_visible", pop
        cr = drv.close_matrix_popup()
        print(f"close residual popup: {cr}")
        assert cr == "ok", cr
        assert drv.matrix_popup() is None, "残留矩阵弹窗没有关掉"

        print("RESULT: PASS")
        return 0
    finally:
        try:
            if drv is not None:
                drv.close()
        except Exception:
            pass
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        srv.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
