"""首次安装判定与新手引导状态。

这里刻意不使用“版本号是否变化”来判断是否重弹：
- 全新安装：授权状态为 fresh 且激活前没有 config.json；
- 老用户：已有配置，或激活前不是 fresh；
- 中途关闭：onboarding_state 为 pending / in_progress，下次从断点继续；
- 完成/跳过：done / legacy，以后升级不再自动弹出。
"""
from __future__ import annotations

import datetime as _dt
import os

STATE_PENDING = "pending"
STATE_IN_PROGRESS = "in_progress"
STATE_DONE = "done"
STATE_LEGACY = "legacy"

SETUP_STEPS = 3
ONBOARD_STEPS = 6

# 这些字段一旦出现，说明用户已经真正配置过模型接口，属于老用户。
_SETUP_KEYS = ("api_key_enc", "api_key", "vision_api_key_enc", "vision_api_key")
_DEFAULT_BASE = "https://api.deepseek.com/v1"
_DEFAULT_MODEL = "deepseek-flash"


def has_setup(cfg: dict) -> bool:
    """用户是否已经配置过可用的模型接口（用于判断老用户）。"""
    for key in _SETUP_KEYS:
        if str(cfg.get(key) or "").strip():
            return True
    base = str(cfg.get("base_url") or "").strip()
    model = str(cfg.get("model") or "").strip()
    # 只有默认 base/model 不算配置过；本地 Ollama / 自定义接口会留下非默认值。
    return bool(base and base != _DEFAULT_BASE) or bool(
        model and model != _DEFAULT_MODEL)


def should_show(cfg: dict, pre_access: str, config_existed: bool,
                manual: bool = False) -> bool:
    """返回本次启动是否应进入首次安装流程。"""
    if manual:
        return True
    state = str(cfg.get("onboarding_state") or "").strip().lower()
    if state == STATE_DONE:
        return False
    # legacy 只应属于真正配置过接口的老用户。旧版曾把“有 config”误标成
    # legacy；如果配置里其实没有 API Key/自定义接口，就在这里修复，补上
    # 首次契约，而不是永远跳过。
    if state == STATE_LEGACY:
        return not has_setup(cfg)
    if state in (STATE_PENDING, STATE_IN_PROGRESS):
        return True
    # 激活前是 fresh 说明本机原本没有有效授权；这时即使目录里残留了
    # 旧 config.json（例如先装过旧版、再在同一个 Windows 用户下重装），
    # 也应该走首次安装契约，否则新用户会直接跳过 API/模型配置。
    if pre_access == "fresh":
        return True
    # 旧版/重装可能留下“有 config 但没有真正配置模型”的空壳；授权状态
    # 也可能因为旧试用/机器码变化显示 expired/tampered，甚至已经恢复成
    # licensed。只要从未配置过 API Key 或自定义接口，就补上契约与新手引导。
    # 真正配置过的老用户会命中 has_setup，不会被打扰。
    if not has_setup(cfg):
        return True
    return False


def is_resume(cfg: dict) -> bool:
    return str(cfg.get("onboarding_state") or "").strip().lower() in (
        STATE_PENDING, STATE_IN_PROGRESS)


def mark_pending(cfg: dict) -> None:
    cfg["onboarding_state"] = STATE_PENDING
    cfg["onboarding_resume_step"] = 1


def mark_in_progress(cfg: dict, step: int = 1) -> None:
    cfg["onboarding_state"] = STATE_IN_PROGRESS
    try:
        cfg["onboarding_resume_step"] = max(1, min(SETUP_STEPS + ONBOARD_STEPS, int(step)))
    except Exception:
        cfg["onboarding_resume_step"] = 1


def mark_done(cfg: dict, version: str, api_skipped: bool = False) -> None:
    cfg["onboarding_state"] = STATE_DONE
    cfg["onboarding_version"] = version
    cfg["onboarding_done_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cfg["onboarding_api_skipped"] = bool(api_skipped)
    cfg["onboarding_resume_step"] = SETUP_STEPS + ONBOARD_STEPS


def mark_legacy(cfg: dict) -> None:
    cfg["onboarding_state"] = STATE_LEGACY
    cfg["onboarding_resume_step"] = SETUP_STEPS + ONBOARD_STEPS


def config_exists(path: str) -> bool:
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False
