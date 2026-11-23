"""列出 Pearson 所有 frame，并检查每个 frame 里是否有可见反馈弹窗。"""
import json
import sys

sys.path.insert(0, ".")
from modules.web import WebPlayer  # noqa: E402

JS = r"""
(() => {
  const t = (document.body && document.body.innerText) || '';
  const hits = [...document.querySelectorAll(
    '[role=dialog],[id*=Dialog],[class*=feedback],[class*=Feedback],[id*=Popup],[class*=Popup]')]
    .filter((e) => e.getBoundingClientRect().width > 2)
    .map((e) => ({
      tag: e.tagName, id: e.id, cls: (e.className || '').toString().slice(0, 80),
      text: (e.innerText || '').replace(/\s+/g, ' ').slice(0, 160),
      btns: [...e.querySelectorAll('button')].map((b) => b.innerText.trim()).slice(0, 6),
    }));
  return {hasCorrect: /Well done|That's correct|Correct/i.test(t),
          hasWrong: /That's incorrect|Try again|Incorrect/i.test(t), hits: hits.slice(0, 6)};
})()
"""


def main():
    d = WebPlayer(port=9222).connect()
    frames = []

    def walk(node):
        f = node["frame"]
        frames.append((f["id"], f.get("url", ""), f.get("name", "")))
        for c in node.get("childFrames", []):
            walk(c)

    walk(d.ws.call("Page.getFrameTree")["frameTree"])
    for fid, url, name in frames:
        try:
            ctx = d.ws.call("Page.createIsolatedWorld", {
                "frameId": fid, "worldName": "probe_fb", "grantUniveralAccess": True,
            })["executionContextId"]
            r = d.ws.call("Runtime.evaluate", {
                "expression": JS, "contextId": ctx, "returnByValue": True,
            })["result"].get("value")
            print(json.dumps({"frame": name or url[:100], "res": r}, ensure_ascii=False))
        except Exception as exc:
            print("ERR", name or url[:80], exc)


if __name__ == "__main__":
    main()
