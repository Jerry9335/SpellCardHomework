"""多平台 API 余额 / 连通性查询。

不同平台的余额接口不一样，这里按常见平台依次尝试：
- DeepSeek:   GET {root}/user/balance
- OpenAI:     GET {root}/dashboard/billing/credit_grants
- Moonshot:   GET {base}/users/me/balance
- OpenRouter: GET {base}/credits
- 都不支持时退回 GET {root}/models，只验证密钥与连通性

返回统一的 dict：
    {"ok": bool, "kind": str, "text": str, "amount": float|None,
     "currency": str, "endpoint": str}
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request


class BalanceError(RuntimeError):
    """查询失败，消息可直接展示。"""


def _root(base: str) -> str:
    b = (base or "").strip().rstrip("/")
    for suffix in ("/chat/completions", "/models"):
        if b.endswith(suffix):
            b = b[: -len(suffix)]
    if b.endswith("/v1"):
        b = b[:-3]
    return b


def _get(url: str, key: str, timeout: float) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "User-Agent": "SpellCardHomework/1.0",
            "Accept": "application/json",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise BalanceError("平台返回的不是 JSON（可能不是余额接口）") from None


def _money(cur: str) -> str:
    cur = (cur or "").upper()
    if cur in ("CNY", "RMB"):
        return "¥"
    if cur == "USD":
        return "$"
    return (cur + " ") if cur else ""


def _parse(kind: str, data: dict) -> dict | None:
    if not isinstance(data, dict):
        return None
    if kind == "deepseek":
        infos = data.get("balance_infos") or []
        if not infos:
            return None
        parts = []
        amount = None
        cur = ""
        for i in infos:
            cur = str(i.get("currency") or "")
            sym = _money(cur)
            total = i.get("total_balance", "?")
            try:
                amount = float(total)
            except Exception:
                pass
            seg = f"{sym}{total}"
            extra = []
            if i.get("topped_up_balance") is not None:
                extra.append(f"充值 {sym}{i.get('topped_up_balance')}")
            if i.get("granted_balance") is not None:
                extra.append(f"赠金 {sym}{i.get('granted_balance')}")
            if extra:
                seg += "（" + " · ".join(extra) + "）"
            parts.append(seg)
        ok = bool(data.get("is_available"))
        head = "灵梦：钱包里还有 " if ok else "灵梦：钱包空得能跑老鼠了——"
        tail = "。……哼，别误会，我才不是担心你不够花。" if ok else "。……看什么看，神社不赊账。"
        return {"ok": ok, "kind": kind, "text": head + " / ".join(parts) + tail,
                "amount": amount, "currency": cur, "endpoint": "user/balance"}

    if kind == "openai":
        avail = data.get("total_available")
        if avail is None:
            return None
        try:
            amount = float(avail)
        except Exception:
            amount = None
        seg = f"${avail}"
        if data.get("total_granted") is not None:
            seg += f"（总额 ${data.get('total_granted')} · 已用 ${data.get('total_used', '?')}）"
        return {"ok": True, "kind": kind,
                "text": "灵梦：账上还能用 " + seg + "。省着点，别到时候又跑来求我。",
                "amount": amount, "currency": "USD", "endpoint": "credit_grants"}

    if kind == "moonshot":
        body = data.get("data") if isinstance(data.get("data"), dict) else data
        avail = body.get("available_balance")
        if avail is None:
            return None
        seg = f"¥{avail}"
        if body.get("voucher_balance") is not None:
            seg += f"（代金券 ¥{body.get('voucher_balance')}）"
        return {"ok": True, "kind": kind,
                "text": "灵梦：钱包里还有 " + seg + "……啧，连代金券都翻出来了？",
                "amount": float(avail) if _is_num(avail) else None,
                "currency": "CNY", "endpoint": "users/me/balance"}

    if kind == "openrouter":
        body = data.get("data") if isinstance(data.get("data"), dict) else data
        credits = body.get("total_credits")
        usage = body.get("total_usage")
        if credits is None:
            return None
        try:
            left = float(credits) - float(usage or 0)
        except Exception:
            left = None
        seg = f"${left:.2f}" if left is not None else f"${credits}"
        if usage is not None:
            seg += f"（总额 ${credits} · 已用 ${usage}）"
        return {"ok": True, "kind": kind,
                "text": "灵梦：账上还能用 " + seg + "。花得挺快嘛。",
                "amount": left, "currency": "USD", "endpoint": "credits"}

    return None


def _is_num(x) -> bool:
    try:
        float(x)
        return True
    except Exception:
        return False


def check(base: str, key: str, timeout: float = 6.0) -> dict:
    """查询余额；不支持余额的平台返回连通性结果。失败抛 BalanceError。"""
    base = (base or "").strip()
    if not base:
        raise BalanceError("术式坐标都没写，想让我凭空找神社？")
    if not key:
        raise BalanceError("连通行密钥都没填，你是来参拜的还是来许愿的？")

    root = _root(base)
    candidates: list[tuple[str, str]] = []
    for b in (root, base.rstrip("/")):
        candidates += [
            (b + "/user/balance", "deepseek"),
            (b + "/dashboard/billing/credit_grants", "openai"),
            (b + "/users/me/balance", "moonshot"),
            (b + "/credits", "openrouter"),
        ]

    seen: set[str] = set()
    last_error: Exception | None = None
    for url, kind in candidates:
        if url in seen:
            continue
        seen.add(url)
        try:
            data = _get(url, key, timeout)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise BalanceError("这张符不认路。密钥是不是抄错了？") from None
            last_error = e
            continue
        except Exception as e:
            last_error = e
            continue
        parsed = _parse(kind, data)
        if parsed:
            return parsed

    # 没有余额接口：至少验证一下密钥和连通性（root 与 base 各试一次）
    try:
        data = None
        last_models_err = None
        for url in (root + "/models", base.rstrip("/") + "/models"):
            try:
                data = _get(url, key, timeout)
                break
            except Exception as _e:
                last_models_err = _e
        if data is None and last_models_err is not None:
            raise last_models_err
        ids = [m.get("id") for m in (data.get("data") or []) if isinstance(m, dict)]
        n = len(ids)
        if n:
            sample = "、".join(str(x) for x in ids[:3])
            return {
                "ok": True, "kind": "models",
                "text": f"八云紫：这个平台不肯报家底呢～不过钥匙是真的，能看到 {n} 个式神（{sample}…）。",
                "amount": None, "currency": "", "endpoint": "models",
            }
        return {"ok": True, "kind": "models",
                "text": "八云紫：这个平台不肯报家底呢～不过连接是通的。",
                "amount": None, "currency": "", "endpoint": "models"}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise BalanceError("这张符不认路。密钥是不是抄错了？") from None
        raise BalanceError(f"八云紫：这平台连账房都不让进（HTTP {e.code}），去它自己的控制台看吧～") from None
    except Exception as e:
        raise BalanceError(f"魔理沙：连不上平台，网络是不是被结界挡住了？（{e}）") from None
