"""本地 OCR：调用 Windows 自带的 Windows.Media.Ocr 引擎（离线、零安装）。

实现方式：把截图存成临时 PNG，交给 PowerShell 5.1 调用 WinRT OCR，
返回每行文字及其坐标，再在这里合并成阅读顺序正确的文本。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field

from PIL import Image

_HERE = os.path.dirname(os.path.abspath(__file__))
_PS_SCRIPT = os.path.normpath(os.path.join(_HERE, "..", "tools", "ocr_ps.ps1"))

_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LATIN = re.compile(r"[A-Za-z]")


def _powershell() -> str:
    windir = os.environ.get("WINDIR", r"C:\Windows")
    p = os.path.join(windir, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return p if os.path.exists(p) else "powershell.exe"


def _run(args: list[str], timeout: float = 40.0) -> dict:
    cmd = [
        _powershell(),
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        _PS_SCRIPT,
        *args,
    ]
    flags = 0
    if os.name == "nt":
        flags = 0x08000000  # CREATE_NO_WINDOW
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            creationflags=flags,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "本地 OCR 超时（图片可能过大）"}

    out = (proc.stdout or b"").decode("utf-8", "replace")
    err = (proc.stderr or b"").decode("utf-8", "replace")
    for line in reversed(out.splitlines()):
        line = line.strip().lstrip("\ufeff")
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    msg = (err or out).strip().splitlines()
    detail = msg[-1] if msg else "未知错误"
    return {"ok": False, "error": f"本地 OCR 失败：{detail[:200]}"}


@dataclass
class OcrOutcome:
    ok: bool
    text: str = ""
    lang: str = ""
    lines: list[dict] = field(default_factory=list)
    error: str = ""


def available_languages() -> list[dict]:
    data = _run(["-ListLanguages"])
    if data.get("ok"):
        return data.get("languages") or []
    return []


def _clean_cjk_spacing(text: str) -> str:
    """Windows 中文 OCR 会在每个汉字之间插空格，这里还原。"""
    if not _CJK.search(text):
        return text
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[，。！？；：、（）《》“”‘’…—])", "", text)
    text = re.sub(r"(?<=[，。！？；：、（）《》“”‘’…—])\s+(?=[\u4e00-\u9fff])", "", text)
    return text


def _pick(results: list[dict]) -> dict | None:
    """在多个语言引擎结果里挑最靠谱的一份。"""
    best, best_score = None, -1.0
    for r in results:
        text = r.get("text") or ""
        cjk = len(_CJK.findall(text))
        latin = len(_LATIN.findall(text))
        if cjk == 0 and latin == 0:
            continue
        # 中文比例高 → 中文结果更可信；纯英文 → 英文结果更可信
        ratio = cjk / (cjk + latin)
        lang = r.get("lang", "")
        want_zh = "zh" in lang.lower()
        score = len(text) / 100.0
        score += 5.0 * (ratio if want_zh else (1 - ratio))
        if score > best_score:
            best, best_score = r, score
    return best


def recognize(image: Image.Image, languages: tuple[str, ...] = ("zh-Hans-CN", "en-US")) -> OcrOutcome:
    """对 PIL 图片做本地 OCR。会自动在中英文引擎之间挑选更可靠的结果。"""
    if image is None or image.width < 8 or image.height < 8:
        return OcrOutcome(False, error="截图太小，无法识别")

    fd, path = tempfile.mkstemp(suffix=".png", prefix="aiquiz_ocr_")
    os.close(fd)
    try:
        img = image.convert("RGB")
        img.save(path, "PNG")
        data = _run(["-ImagePath", path, "-Languages", ",".join(languages)])
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    if not data.get("ok"):
        return OcrOutcome(False, error=str(data.get("error") or "本地 OCR 失败"))

    results = data.get("results") or []
    if not results:
        return OcrOutcome(False, error="没有可用的 Windows OCR 语言包（请在系统设置里安装简体中文/英语 OCR）")

    chosen = _pick(results) or results[0]
    text = _clean_cjk_spacing((chosen.get("text") or "").strip())
    if not text:
        return OcrOutcome(False, error="本地 OCR 未识别到文字")

    return OcrOutcome(
        True,
        text=text,
        lang=str(chosen.get("lang") or ""),
        lines=chosen.get("lines") or [],
    )


def looks_english(text: str) -> bool:
    """判断题目是不是英文（需要出中文翻译）。"""
    if not text:
        return False
    cjk = len(_CJK.findall(text))
    latin = len(_LATIN.findall(text))
    if latin < 15:
        return False
    return latin > cjk * 4 and cjk < latin * 0.35
