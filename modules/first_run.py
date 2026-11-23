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


def should_show(cfg: dict, pre_access: str, config_existed: bool,
                manual: bool = False) -> bool:
    """返回本次启动是否应进入首次安装流程。"""
    if manual:
        return True
    state = str(cfg.get("onboarding_state") or "").strip().lower()
    if state in (STATE_DONE, STATE_LEGACY):
        return False
    if state in (STATE_PENDING, STATE_IN_PROGRESS):
        return True
    # 没有状态字段的 1.0.6 老用户：看激活前的事实，而不是版本号。
    if pre_access == "fresh" and not config_existed:
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
