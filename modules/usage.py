"""API 用量记账：每次调用记录 tokens、耗时、估算费用，并提供汇总与图表。

数据文件：%APPDATA%\\SpellCardHomework\\usage.jsonl（一行一条）
"""
from __future__ import annotations

import csv
import json
import os
import time
from datetime import date, datetime, timedelta

from . import settings

# 参考单价：元 / 百万 tokens（输入, 输出）。仅用于估算，实际以平台账单为准。
PRICES: list[tuple[str, float, float]] = [
    ("deepseek-reasoner", 4.0, 16.0),
    ("deepseek", 2.0, 8.0),
    ("gpt-4o-mini", 1.1, 4.3),
    ("gpt-4o", 18.0, 72.0),
    ("o1", 36.0, 144.0),
    ("qwen", 0.8, 2.0),
    ("glm", 0.5, 0.5),
    ("claude", 21.0, 105.0),
    ("gemini", 1.0, 4.0),
]
DEFAULT_PRICE = (2.0, 8.0)

_listener = None


def set_listener(fn) -> None:
    """注册回调：每记一笔就通知界面刷新（fn(row)）。"""
    global _listener
    _listener = fn


def path() -> str:
    return os.path.join(settings.config_dir(), "usage.jsonl")


def price_for(model: str) -> tuple[float, float]:
    m = (model or "").lower()
    for prefix, pin, pout in PRICES:
        if m.startswith(prefix) or prefix in m:
            return pin, pout
    return DEFAULT_PRICE


def record(model: str, usage: dict, elapsed: float) -> dict:
    """记一笔。usage 为接口返回的 usage 字段（可能为空）。"""
    prompt = int((usage or {}).get("prompt_tokens") or 0)
    completion = int((usage or {}).get("completion_tokens") or 0)
    total = int((usage or {}).get("total_tokens") or (prompt + completion))
    pin, pout = price_for(model)
    cost = prompt / 1e6 * pin + completion / 1e6 * pout
    row = {
        "t": int(time.time()),
        "model": model or "?",
        "prompt": prompt,
        "completion": completion,
        "tokens": total,
        "sec": round(float(elapsed or 0.0), 2),
        "cost": round(cost, 6),
    }
    try:
        os.makedirs(os.path.dirname(path()), exist_ok=True)
        with open(path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass
    if _listener is not None:
        try:
            _listener(row)
        except Exception:
            pass
    return row


def load() -> list[dict]:
    rows: list[dict] = []
    try:
        with open(path(), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return rows


def _day(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def summary(days: int = 30) -> dict:
    rows = load()
    today = date.today().isoformat()
    today_rows = [r for r in rows if _day(int(r.get("t", 0))) == today]

    def agg(items: list[dict]) -> dict:
        return {
            "calls": len(items),
            "tokens": sum(int(r.get("tokens") or 0) for r in items),
            "cost": sum(float(r.get("cost") or 0) for r in items),
            "sec": sum(float(r.get("sec") or 0) for r in items),
        }

    by_model: dict[str, dict] = {}
    for r in rows:
        m = r.get("model") or "?"
        d = by_model.setdefault(m, {"calls": 0, "tokens": 0, "cost": 0.0})
        d["calls"] += 1
        d["tokens"] += int(r.get("tokens") or 0)
        d["cost"] += float(r.get("cost") or 0)

    by_day: list[tuple[str, float, int]] = []
    start = date.today() - timedelta(days=days - 1)
    buckets: dict[str, list[float]] = {}
    for r in rows:
        d = _day(int(r.get("t", 0)))
        b = buckets.setdefault(d, [0.0, 0])
        b[0] += float(r.get("cost") or 0)
        b[1] += int(r.get("tokens") or 0)
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        c, tk = buckets.get(d, [0.0, 0])
        by_day.append((d, c, tk))

    return {
        "total": agg(rows),
        "today": agg(today_rows),
        "by_model": sorted(by_model.items(), key=lambda kv: kv[1]["cost"], reverse=True),
        "by_day": by_day,
        "recent": rows[-12:][::-1],
    }


def export_csv(dest: str) -> int:
    rows = load()
    with open(dest, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["时间", "模型", "输入 tokens", "输出 tokens", "总 tokens", "耗时(秒)", "费用(元)"])
        for r in rows:
            w.writerow([
                datetime.fromtimestamp(int(r.get("t", 0))).strftime("%Y-%m-%d %H:%M:%S"),
                r.get("model", ""), r.get("prompt", 0), r.get("completion", 0),
                r.get("tokens", 0), r.get("sec", 0), r.get("cost", 0),
            ])
    return len(rows)


_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
)


def _load_font(size: int):
    """挑一个系统里存在的字体；都没有就退回 Pillow 内置位图字体，绝不抛异常。"""
    from PIL import ImageFont

    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def render_chart(by_day: list[tuple[str, float, int]], width: int = 860, height: int = 170) -> "object":
    """把近 N 天费用画成柱状图（PIL Image）。"""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, height), (26, 22, 44))
    d = ImageDraw.Draw(img)
    font = _load_font(11)
    n = max(1, len(by_day))
    max_cost = max((c for _, c, _ in by_day), default=0.0) or 1.0
    pad_l, pad_b, pad_t = 40, 26, 12
    plot_w = width - pad_l - 12
    plot_h = height - pad_b - pad_t
    bar_w = max(2, plot_w // n - 2)

    # 网格
    for i in range(4):
        y = pad_t + plot_h * i // 3
        d.line([(pad_l, y), (width - 12, y)], fill=(44, 38, 66))
        d.text((6, y - 7), f"¥{max_cost * (3 - i) / 3:.2f}", font=font, fill=(150, 140, 180))

    for i, (day, cost, _tok) in enumerate(by_day):
        x = pad_l + i * (plot_w / n) + 1
        h = int(plot_h * (cost / max_cost)) if max_cost else 0
        if h > 0:
            d.rectangle([x, pad_t + plot_h - h, x + bar_w, pad_t + plot_h],
                        fill=(232, 150, 70))
        if i % 5 == 0:
            d.text((x - 2, height - 20), day[5:], font=font, fill=(150, 140, 180))
    return img
