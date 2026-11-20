"""网页模式端到端测试：假题目页面 + 真 Edge（headless）+ CDP。

验证：读 DOM、点选项、点 Check answer、读判分、点 Next。
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from modules import web
from tools.mock_server import serve

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

srv = serve(8767)
port = 9333
profile = tempfile.mkdtemp(prefix="shinichi_edge_")

edge = next((p for p in EDGE_CANDIDATES if os.path.exists(p)), None)
if not edge:
    print("没找到 Edge，跳过网页模式测试")
    srv.shutdown()
    sys.exit(2)

proc = subprocess.Popen([
    edge, "--headless=new", f"--remote-debugging-port={port}",
    f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
    "--disable-gpu", "http://127.0.0.1:8767/quiz",
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

ok = False
try:
    drv = None
    for _ in range(40):
        time.sleep(0.5)
        try:
            drv = web.WebPlayer(port, log=print).connect()
            break
        except Exception as e:
            last = e
    if drv is None:
        print("连不上 CDP：", last)
        sys.exit(1)

    # 等页面就绪
    st = {}
    for _ in range(30):
        st = drv.state() or {}
        if st.get("radios"):
            break
        time.sleep(0.3)

    print("题目文本:", (st.get("text") or "")[:80].replace("\n", " "))
    print("单选项:", len(st.get("radios", [])), "输入框:", len(st.get("fields", [])))
    print("hasCheck:", st.get("hasCheck"), "hasNext:", st.get("hasNext"))
    assert st.get("radios"), "没读到单选项"
    assert st.get("hasCheck"), "没读到 Check answer 按钮"

    print("\n-- 点选项 B --")
    print("pick_choice ->", drv.pick_choice("B"))
    checked = [r for r in drv.state()["radios"] if r.get("checked")]
    print("已选中:", [r["label"] for r in checked])
    assert checked and checked[0]["label"].startswith("B"), "选项没选中"

    print("\n-- 点 Check answer --")
    print("click ->", drv.click_text(r"^check answer$"))
    fb = ""
    for _ in range(10):
        time.sleep(0.4)
        fb = drv.feedback()
        if fb:
            break
    print("判分:", fb)
    assert fb == "correct", f"判分不对：{fb!r}"

    print("\n-- 关弹窗 + 点 Next --")
    drv.click_text(r"^\s*ok\s*$")
    time.sleep(0.4)
    drv.click_text(r"^next( question)?$")
    time.sleep(0.8)
    st2 = drv.state()
    print("新题:", (st2.get("text") or "")[:50].replace("\n", " "))
    assert "2 + 2" in (st2.get("text") or ""), "Next 没翻页"

    ok = True
    drv.close()
finally:
    proc.terminate()
    try:
        proc.wait(timeout=6)
    except Exception:
        proc.kill()
    srv.shutdown()
    shutil.rmtree(profile, ignore_errors=True)

print("\nRESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)

