"""检查更新：GitHub + Gitee 双渠道。

返回统一结构：
    {
        "version": "1.0.6-rc.03",  # 去掉 v 的版本号
        "tag": "v1.0.6-rc.03",
        "notes": "...",           # Release 说明（纯文本）
        "url": "https://...",     # Release 页面
        "download": "https://...",# 安装包地址（没有则同 url）
        "source": "gitee" | "github",
        "date": "2026-11-30",
    }
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

USER_AGENT = "SpellCardHomework/1.0"

GITHUB_REPO = "Jerry9335/SpellCardHomework"
GITEE_REPO = "jerry6663/SpellCardHomework"

GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITEE_API = f"https://gitee.com/api/v5/repos/{GITEE_REPO}/releases/latest"


class UpdateError(RuntimeError):
    pass


def parse_version(tag: str) -> tuple[int, ...]:
    """'v1.0.6' -> (1, 0, 6)；解析失败返回空元组。只用于界面展示。"""
    m = re.search(r"(\d+(?:\.\d+)*)", str(tag or ""))
    if not m:
        return ()
    return tuple(int(x) for x in m.group(1).split("."))


_PRERELEASE_RANK = {"dev": 0, "alpha": 1, "a": 1, "beta": 2, "b": 2,
                    "pre": 3, "preview": 3, "rc": 4}


def version_key(tag: str) -> tuple[int, ...]:
    """比较用的版本键：预发布版排在同号正式版之前。

    '1.0.6-beta1' -> (1, 0, 6, 0, 2, 1)，'1.0.6' -> (1, 0, 6, 1)。
    这样 beta1 既小于 1.0.6 正式版，也小于 beta2。
    """
    s = str(tag or "").strip().lower()
    m = re.search(r"(\d+(?:\.\d+)*)(?:[-._ ]?(dev|alpha|a|beta|b|pre|preview|rc)\.?\s*(\d+)?)?", s)
    if not m:
        return ()
    nums = [int(x) for x in m.group(1).split(".")]
    pre = m.group(2)
    if pre:
        return tuple(nums + [0, _PRERELEASE_RANK.get(pre, 1), int(m.group(3) or 0)])
    return tuple(nums + [1])


def is_newer(latest: str, current: str) -> bool:
    a, b = version_key(latest), version_key(current)
    if not a or not b:
        return False
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def _get_json(url: str, timeout: float) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "SpellCardHomework/1.0",
            "Accept": "application/vnd.github+json, application/json",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise UpdateError("返回的不是 JSON") from None
    if not isinstance(data, dict):
        raise UpdateError("返回格式不对")
    return data


def _download_asset(assets: list, fallback: str) -> dict:
    for a in assets or []:
        if not isinstance(a, dict):
            continue
        name = str(a.get("name") or "")
        if name.lower().endswith((".exe", ".msi")):
            url = a.get("browser_download_url") or a.get("download_url") or fallback
            return {
                "url": str(url or fallback),
                "name": name,
                "size": int(a.get("size") or 0),
                "digest": str(a.get("digest") or ""),
            }
    return {"url": str(fallback or ""), "name": "", "size": 0, "digest": ""}


def _get_text(url: str, timeout: float, limit: int = 131072) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(limit)
    return raw.decode("utf-8", "replace").strip()


def _parse_sha_text(text: str, filename: str = "") -> str:
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.search(r"\b([A-Fa-f0-9]{64})\b", line)
        if not m:
            continue
        if not filename or filename.lower() in line.lower() or line.startswith(m.group(1)):
            return m.group(1).lower()
    m = re.search(r"\b([A-Fa-f0-9]{64})\b", str(text or ""))
    return m.group(1).lower() if m else ""


def _find_sha256(assets: list, exe_asset: dict, notes: str,
                 timeout: float) -> str:
    digest = str(exe_asset.get("digest") or "")
    if digest.lower().startswith("sha256:"):
        return digest.split(":", 1)[1].strip().lower()
    for a in assets or []:
        if not isinstance(a, dict):
            continue
        name = str(a.get("name") or "")
        low = name.lower()
        if low.endswith((".sha256", ".sha256sum", ".sha256.txt")) or \
                low in ("sha256sums.txt", "sha256sums", "checksums.txt"):
            url = a.get("browser_download_url") or a.get("download_url") or ""
            if not url:
                continue
            try:
                text = _get_text(url, timeout)
                sha = _parse_sha_text(text, str(exe_asset.get("name") or ""))
                if sha:
                    return sha
            except Exception:
                continue
    return _parse_sha_text(notes, str(exe_asset.get("name") or ""))


def _from_github(data: dict) -> dict:
    tag = str(data.get("tag_name") or data.get("name") or "")
    if not tag:
        raise UpdateError("GitHub 没有版本号")
    url = str(data.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases/tag/{tag}")
    assets = data.get("assets") or []
    notes = str(data.get("body") or "").strip()
    asset = _download_asset(assets, url)
    return {
        "version": ".".join(str(x) for x in parse_version(tag)) or tag.lstrip("v"),
        "tag": tag,
        "notes": notes,
        "url": url,
        "download": asset["url"],
        "asset_name": asset["name"],
        "size": asset["size"],
        "sha256": _find_sha256(assets, asset, notes, 6.0),
        "source": "github",
        "date": str(data.get("published_at") or data.get("created_at") or "")[:10],
    }


def _from_gitee(data: dict) -> dict:
    tag = str(data.get("tag_name") or data.get("name") or "")
    if not tag:
        raise UpdateError("Gitee 没有版本号")
    url = str(data.get("html_url") or
              f"https://gitee.com/{GITEE_REPO}/releases/tag/{tag}")
    assets = data.get("assets") or []
    notes = str(data.get("body") or "").strip()
    asset = _download_asset(assets, url)
    return {
        "version": ".".join(str(x) for x in parse_version(tag)) or tag.lstrip("v"),
        "tag": tag,
        "notes": notes,
        "url": url,
        "download": asset["url"],
        "asset_name": asset["name"],
        "size": asset["size"],
        "sha256": _find_sha256(assets, asset, notes, 6.0),
        "source": "gitee",
        "date": str(data.get("created_at") or data.get("published_at") or "")[:10],
    }


def _fetch(source: str, timeout: float) -> dict:
    url = GITEE_API if source == "gitee" else GITHUB_API
    data = _get_json(url, timeout)
    return _from_gitee(data) if source == "gitee" else _from_github(data)


def check(channel: str = "auto", timeout: float = 6.0) -> dict:
    """按渠道查询最新 Release；都失败时抛 UpdateError。"""
    channel = channel if channel in ("auto", "gitee", "github") else "auto"
    errors: list[str] = []

    if channel in ("auto", "gitee"):
        try:
            gitee = _fetch("gitee", timeout)
        except Exception as e:
            gitee = None
            errors.append(f"Gitee: {e}")
    else:
        gitee = None

    if channel == "gitee" and gitee is None:
        raise UpdateError("; ".join(errors) or "Gitee 查询失败")

    if channel in ("auto", "github"):
        try:
            github = _fetch("github", timeout)
        except Exception as e:
            github = None
            errors.append(f"GitHub: {e}")
    else:
        github = None

    if channel == "github" and github is None:
        raise UpdateError("; ".join(errors) or "GitHub 查询失败")

    if channel == "auto":
        if gitee and github:
            return gitee if version_key(gitee["tag"]) >= version_key(github["tag"]) else github
        if gitee:
            return gitee
        if github:
            return github
        raise UpdateError("; ".join(errors) or "两边都没查到")

    return gitee or github  # type: ignore[return-value]


def due(cfg: dict, now: float | None = None) -> bool:
    """现在该不该自动检查。"""
    if not cfg.get("update_enabled", True):
        return False
    now = time.time() if now is None else now
    try:
        snooze = float(cfg.get("update_snooze_until") or 0)
    except Exception:
        snooze = 0
    if snooze and now < snooze:
        return False
    try:
        interval = float(cfg.get("update_interval_hours") or 5)
        last = float(cfg.get("update_last_check") or 0)
    except Exception:
        interval, last = 5, 0
    if interval <= 0:
        return True
    return now - last >= interval * 3600


def snooze_until(day) -> int:
    """把日历选的日期转成当天 23:59:59 的时间戳。"""
    import datetime as _dt
    d = day if isinstance(day, _dt.date) else _dt.date.fromisoformat(str(day))
    end = _dt.datetime.combine(d, _dt.time(23, 59, 59))
    return int(end.timestamp())
