"""在真实 Pearson 页面上做一次完整的单问测试：读题 → 模型作答 → 填 → 交 → 判分截图。"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from modules import capture, latex, llm, prompts, settings, web

CAPTURE = os.path.join(ROOT, "docs")
os.makedirs(CAPTURE, exist_ok=True)

cfg = settings.load()
drv = web.WebPlayer(9222, log=print).connect()
st = drv.state()
text = st.get("text") or ""
print("=== 题目 ===")
print(text[:260])
print("\n控件: fields=%s radios=%d hasCheck=%s" % (
    [f["id"] for f in st.get("fields", [])], len(st.get("radios", [])), st.get("hasCheck")))

if st.get("radios"):
    print("（这道是选择题，本次测试只做填空式，先跳过）")
    drv.close()
    raise SystemExit(0)

res = llm.chat_once(cfg["base_url"], cfg["api_key"], cfg.get("model") or "deepseek-flash",
                    prompts.web_messages(text), temperature=0.2)
spec = prompts.parse_web_answer(res.text)
print("\n=== 模型返回 ===")
print(repr(res.text[:160]))
print("解析:", spec)

if not spec.get("value"):
    print("模型没给出 VALUE，停止")
    drv.close()
    raise SystemExit(1)

val = latex.to_editor_input(spec["value"])
print("编辑器输入:", repr(val))

fid = st["fields"][0]["id"]
drv.focus_field(fid)
drv.clear_field()
drv.insert(val)
time.sleep(0.8)
after = drv.state()
print("填入后:", [(f["id"], f.get("value")) for f in after.get("fields", [])])

print("\n点 Check answer ->", drv.click_text(r"^check answer$"))
fb = ""
for _ in range(12):
    time.sleep(0.6)
    fb = (drv.feedback() or "").strip()
    if fb:
        break
print("判分:", repr(fb))

# 截图
time.sleep(0.8)
shot = os.path.join(CAPTURE, "pearson_test.png")
win = None
for w in capture.list_windows(include_own=True):
    if "Pearson" in w.title or "Do Homework" in w.title or "MyLab" in w.title:
        win = w
        break
if win is None:
    for w in capture.list_windows(include_own=True):
        if "Edge" in w.title or "msedge" in (w.cls or "").lower():
            win = w
            break
try:
    import base64
    r = drv.ws.call("Page.captureScreenshot", {"format": "png"})
    open(shot, "wb").write(base64.b64decode(r["data"]))
    print("截图(CDP):", shot)
except Exception as e:
    print("CDP 截图失败:", e)

drv.close()
print("\nRESULT:", "PASS" if fb == "correct" else "FAIL")
sys.exit(0 if fb == "correct" else 1)
