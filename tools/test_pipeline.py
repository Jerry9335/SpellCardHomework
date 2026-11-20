"""端到端测试：模型列表 / 视觉 OCR 流式 / 翻译 / 作答 / reasoning 渲染 / 参数重试。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import llm, ocr_local, prompts
from tools.mock_server import serve

srv = serve(8765)
BASE = "http://127.0.0.1:8765/v1"
KEY = "test-key"

try:
    print("== 模型列表 ==")
    print(llm.list_models(BASE, KEY))

    print("\n== 视觉 OCR（流式）==")
    chunks = []
    msgs = prompts.ocr_messages("data:image/jpeg;base64,AAAA")
    res = llm.chat_stream(BASE, KEY, "mock-vision", msgs, temperature=0.0,
                          on_delta=chunks.append)
    print(f"chunks={len(chunks)} text_len={len(res.text)}")
    print(res.text[:120].replace("\n", " | "))

    print("\n== 翻译（流式）==")
    tchunks = []
    res2 = llm.chat_stream(BASE, KEY, "mock-chat", prompts.translate_messages(res.text),
                           on_delta=tchunks.append)
    print(f"chunks={len(tchunks)}")
    print(res2.text[:80].replace("\n", " | "))
    print("looks_english(原文) =", ocr_local.looks_english(res.text))
    print("looks_english(译文) =", ocr_local.looks_english(res2.text))

    print("\n== 作答 + reasoning 渲染 ==")
    rchunks, cchunks = [], []
    res3 = llm.chat_stream(BASE, KEY, "mock-reasoner",
                           prompts.answer_messages(res.text, True, res2.text),
                           reasoning_effort="high", on_delta=cchunks.append,
                           on_reasoning=rchunks.append)
    print("reason chunks:", len(rchunks), "content chunks:", len(cchunks))
    print("reasoning:", res3.reasoning[:40])
    print("answer:", res3.text[:60].replace("\n", " | "))
    print("usage:", res3.usage)

    print("\n== reasoning_effort 被拒绝时自动重试 ==")
    res4 = llm.chat_stream(BASE, KEY, "no-effort-model", prompts.answer_messages("1+1=?"),
                           reasoning_effort="high")
    print("ok, answer =", res4.text[:30].replace("\n", " | "))

    print("\n== 错误信息 ==")
    try:
        llm.chat_stream(BASE, KEY, "bad-key", prompts.answer_messages("1+1=?"))
    except llm.LLMError as e:
        print("预期报错:", e)

    print("\n全部通过")
finally:
    srv.shutdown()
