"""OpenAI 兼容接口客户端：模型列表 + 流式对话（支持 reasoning_effort）。

只用标准库 urllib，不依赖 requests。
"""
from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

# 常见平台预设（Base URL）
PROVIDER_PRESETS: list[tuple[str, str]] = [
    ("DeepSeek", "https://api.deepseek.com/v1"),
    ("OpenAI", "https://api.openai.com/v1"),
    ("硅基流动 SiliconFlow", "https://api.siliconflow.cn/v1"),
    ("OpenRouter", "https://openrouter.ai/api/v1"),
    ("阿里云百炼 DashScope", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    ("智谱 BigModel", "https://open.bigmodel.cn/api/paas/v4"),
    ("月之暗面 Kimi", "https://api.moonshot.cn/v1"),
    ("火山方舟 Ark", "https://ark.cn-beijing.volces.com/api/v3"),
    ("腾讯混元", "https://api.hunyuan.cloud.tencent.com/v1"),
    ("本地 Ollama", "http://127.0.0.1:11434/v1"),
    ("本地 LM Studio", "http://127.0.0.1:1234/v1"),
]

# 思考强度：界面显示 → 发送给接口的值（None = 不发送）
EFFORT_OPTIONS: list[tuple[str, str | None]] = [
    ("自动（默认）", None),
    ("最低 minimal", "minimal"),
    ("低 low", "low"),
    ("中 medium", "medium"),
    ("高 high", "high"),
]
EFFORT_MAP = dict(EFFORT_OPTIONS)


class LLMError(RuntimeError):
    """接口调用失败，消息可直接展示给用户。"""


def _pick_endpoint(base: str, path: str) -> str:
    b = (base or "").strip().rstrip("/")
    if not b:
        raise LLMError("请先填写 Base URL，例如 https://api.deepseek.com/v1")
    if b.endswith("/chat/completions") or b.endswith("/models"):
        return b
    lower = b.lower()
    if lower.endswith(("/v1", "/v2", "/v3", "/v4", "/v1beta", "/openai/v1")):
        return f"{b}/{path}"
    if "/compatible-mode/v1" in lower or "/compatible-mode" in lower:
        return f"{b}/{'chat/completions' if path == 'chat/completions' else path}"
    return f"{b}/v1/{path}"


def _headers(api_key: str) -> dict[str, str]:
    h = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream, application/json",
        "User-Agent": "AI-Quiz-Helper/1.0",
    }
    if api_key.strip():
        h["Authorization"] = f"Bearer {api_key.strip()}"
    return h


def _friendly_http_error(code: int, body: str) -> LLMError:
    detail = ""
    try:
        obj = json.loads(body)
        err = obj.get("error")
        if isinstance(err, dict):
            detail = str(err.get("message") or err.get("code") or "")
        elif isinstance(err, str):
            detail = err
        else:
            detail = str(obj.get("message") or "")
    except Exception:
        detail = body.strip()
    detail = detail.strip()[:400]
    if code == 401:
        return LLMError(f"API Key 无效或已过期（401）。{detail}")
    if code == 403:
        return LLMError(f"没有权限访问该模型（403）。{detail}")
    if code == 404:
        return LLMError(f"接口地址不对（404）。请检查 Base URL 是否以 /v1 结尾。{detail}")
    if code == 429:
        return LLMError(f"请求过于频繁或额度不足（429）。{detail}")
    if code >= 500:
        return LLMError(f"平台服务器错误（{code}）。{detail}")
    return LLMError(f"接口返回 {code}。{detail}")


@dataclass
class StreamResult:
    text: str = ""
    reasoning: str = ""
    usage: dict = field(default_factory=dict)
    model: str = ""
    elapsed: float = 0.0


def list_models(base: str, api_key: str, timeout: float = 20.0) -> list[str]:
    """拉取平台可用模型列表。"""
    url = _pick_endpoint(base, "models")
    req = urllib.request.Request(url, headers=_headers(api_key), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise _friendly_http_error(e.code, e.read().decode("utf-8", "replace")) from None
    except urllib.error.URLError as e:
        raise LLMError(f"连不上服务器：{e.reason}") from None
    except socket.timeout:
        raise LLMError("连接超时，请检查网络或 Base URL") from None

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        raise LLMError(f"模型列表不是合法 JSON：{raw[:200]}") from None

    items = obj.get("data")
    if items is None and isinstance(obj.get("models"), list):
        items = obj["models"]
    if not isinstance(items, list):
        raise LLMError(f"返回格式不符合预期：{raw[:200]}")

    ids: list[str] = []
    for it in items:
        if isinstance(it, str):
            ids.append(it)
        elif isinstance(it, dict):
            mid = it.get("id") or it.get("name") or it.get("model")
            if mid:
                ids.append(str(mid))
    return sorted(set(ids))


def chat_stream(
    base: str,
    api_key: str,
    model: str,
    messages: list[dict],
    *,
    reasoning_effort: str | None = None,
    temperature: float | None = 0.2,
    extra_body: dict | None = None,
    timeout: float = 300.0,
    on_delta: Callable[[str], None] | None = None,
    on_reasoning: Callable[[str], None] | None = None,
    cancel: threading.Event | None = None,
) -> StreamResult:
    """流式对话。on_delta 收到正文增量，on_reasoning 收到思考过程增量。"""
    if not model.strip():
        raise LLMError("请先选择或填写模型名称")

    url = _pick_endpoint(base, "chat/completions")
    payload: dict = {
        "model": model.strip(),
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    if extra_body:
        for k, v in extra_body.items():
            payload[k] = v

    result = StreamResult(model=model)
    started = time.time()
    attempt = 0
    while True:
        attempt += 1
        drop_effort = False
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=_headers(api_key), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                ctype = (resp.headers.get("Content-Type") or "").lower()
                if "text/event-stream" not in ctype and "application/json" in ctype:
                    result = _parse_json_once(resp.read(), result, on_delta)
                    break
                result = _read_sse(resp, result, on_delta, on_reasoning, cancel)
                break
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code == 400 and "stream_options" in body.lower() and attempt == 1:
                payload.pop("stream_options", None)
                continue
            if e.code == 400 and reasoning_effort and "reasoning" in body.lower() and attempt == 1:
                drop_effort = True
            else:
                raise _friendly_http_error(e.code, body) from None
        except urllib.error.URLError as e:
            if attempt == 1 and not isinstance(e.reason, socket.timeout):
                time.sleep(0.6)
                continue
            raise LLMError(f"连不上服务器：{e.reason}") from None
        except socket.timeout:
            raise LLMError("请求超时（模型可能正在思考，可稍后重试或换更快模型）") from None

        if drop_effort:
            payload.pop("reasoning_effort", None)
            reasoning_effort = None

    result.elapsed = time.time() - started
    _record_usage(result)
    return result


def _record_usage(result: StreamResult) -> None:
    try:
        from . import usage as _usage

        _usage.record(result.model, result.usage, result.elapsed)
    except Exception:
        pass


def _read_sse(resp, result: StreamResult, on_delta, on_reasoning, cancel) -> StreamResult:
    text_parts: list[str] = []
    reason_parts: list[str] = []
    for raw in resp:
        if cancel is not None and cancel.is_set():
            raise LLMError("已停止")
        if not raw:
            continue
        line = raw.decode("utf-8", "replace").strip()
        if not line or line.startswith(":"):
            continue
        if line.startswith("data:"):
            line = line[5:].strip()
        if line == "[DONE]":
            break
        if not line.startswith("{"):
            continue
        try:
            chunk = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "error" in chunk and not chunk.get("choices"):
            msg = chunk["error"]
            if isinstance(msg, dict):
                msg = msg.get("message") or msg
            raise LLMError(f"接口返回错误：{msg}")
        if chunk.get("usage"):
            result.usage = chunk["usage"]
        choices = chunk.get("choices") or []
        if not choices:
            continue
        ch = choices[0] or {}
        delta = ch.get("delta") or ch.get("message") or {}
        rc = delta.get("reasoning_content") or delta.get("reasoning")
        if rc:
            reason_parts.append(rc)
            if on_reasoning:
                on_reasoning(rc)
        content = delta.get("content")
        if content:
            text_parts.append(content)
            if on_delta:
                on_delta(content)
    result.text = "".join(text_parts)
    result.reasoning = "".join(reason_parts)
    return result


def chat_once(
    base: str,
    api_key: str,
    model: str,
    messages: list[dict],
    *,
    reasoning_effort: str | None = None,
    temperature: float | None = 0.2,
    extra_body: dict | None = None,
    timeout: float = 180.0,
) -> StreamResult:
    """非流式调用，返回完整结果（网页模式、余额等场景用）。"""
    if not model.strip():
        raise LLMError("请先选择或填写模型名称")
    url = _pick_endpoint(base, "chat/completions")
    payload: dict = {"model": model.strip(), "messages": messages, "stream": False}
    if temperature is not None:
        payload["temperature"] = temperature
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    if extra_body:
        payload.update(extra_body)

    result = StreamResult(model=model)
    started = time.time()
    attempt = 0
    while True:
        attempt += 1
        drop_effort = False
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=_headers(api_key), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return _parse_json_once(resp.read(), result, None)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code == 400 and "stream_options" in body.lower() and attempt == 1:
                payload.pop("stream_options", None)
                continue
            if e.code == 400 and reasoning_effort and "reasoning" in body.lower() and attempt == 1:
                drop_effort = True
            else:
                raise _friendly_http_error(e.code, body) from None
        except urllib.error.URLError as e:
            if attempt == 1:
                time.sleep(0.6)
                continue
            raise LLMError(f"连不上服务器：{e.reason}") from None
        except socket.timeout:
            raise LLMError("请求超时") from None
        if drop_effort:
            payload.pop("reasoning_effort", None)
            reasoning_effort = None
        result.elapsed = time.time() - started


def deepseek_balance(api_key: str, base: str = "https://api.deepseek.com", timeout: float = 15.0) -> dict:
    """查询 DeepSeek 余额（只有 DeepSeek 支持）。"""
    root = base.rstrip("/")
    for suffix in ("/chat/completions", "/v1"):
        if root.endswith(suffix):
            root = root[: -len(suffix)]
    url = root + "/user/balance"
    req = urllib.request.Request(url, headers=_headers(api_key), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise _friendly_http_error(e.code, e.read().decode("utf-8", "replace")) from None
    except urllib.error.URLError as e:
        raise LLMError(f"连不上服务器：{e.reason}") from None


def _parse_json_once(raw: bytes, result: StreamResult, on_delta) -> StreamResult:
    try:
        obj = json.loads(raw.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        raise LLMError(f"接口返回内容无法解析：{raw[:200]!r}") from None
    if "error" in obj and not obj.get("choices"):
        err = obj["error"]
        if isinstance(err, dict):
            err = err.get("message") or err
        raise LLMError(f"接口返回错误：{err}")
    if obj.get("usage"):
        result.usage = obj["usage"]
    choices = obj.get("choices") or []
    if choices:
        msg = choices[0].get("message") or {}
        content = msg.get("content") or ""
        if on_delta and content:
            on_delta(content)
        result.text = content
        result.reasoning = msg.get("reasoning_content") or ""
    return result
