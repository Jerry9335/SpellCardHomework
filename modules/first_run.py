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
# 必须和 settings.DEFAULTS["model"] 一致，否则默认值会被当成「用户自己配过」，
# 于是一个只激活了授权、还没填通行密钥的用户会直接跳过首次契约。
# （灵梦：默认的那张符卡不算你自己画的，别拿它冒充。）
_DEFAULT_MODEL = "deepseek-chat"


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
    """返回本次启动是否应自动进入首次安装流程。

    自动全屏只在“真正的新安装 / 重装”出现一次：
    - 中断、手动取消后的 pending/in_progress 不再自动弹；
    - 契约没配好或引路没看完，用户去设置中心补，或点“重看引路”；
    - 这样不会每次启动都被半截引导拦住。
    """
    if manual:
        return True
    state = str(cfg.get("onboarding_state") or "").strip().lower()
    if state == STATE_DONE:
        return False
    # 重装由 _apply_install_anchor 写入一次性标记；消费后不会反复弹。
    if cfg.get("onboarding_reinstall"):
        return True
    # pending / in_progress 是“上次中断”，按新方案不再自动续。
    if state in (STATE_PENDING, STATE_IN_PROGRESS):
        return False
    # legacy 是已升级用户，不自动打扰；需要时从设置里重看。
    if state == STATE_LEGACY:
        return False
    # 真正的首次安装：激活前没有有效授权。
    return pre_access == "fresh"


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


def mark_done(cfg: dict, version: str, api_skipped: bool = False,
              tour_skipped: bool = False) -> None:
    cfg["onboarding_state"] = STATE_DONE
    cfg["onboarding_version"] = version
    cfg["onboarding_done_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cfg["onboarding_api_skipped"] = bool(api_skipped)
    cfg["onboarding_tour_skipped"] = bool(tour_skipped)
    cfg["onboarding_reinstall"] = False
    cfg["onboarding_resume_step"] = SETUP_STEPS + ONBOARD_STEPS


def mark_legacy(cfg: dict) -> None:
    cfg["onboarding_state"] = STATE_LEGACY
    cfg["onboarding_resume_step"] = SETUP_STEPS + ONBOARD_STEPS


def install_anchor(install_dir: str) -> str:
    """安装目录的创建时间锚点。

    Windows 上目录 ctime 是创建时间；Inno 卸载会删除安装目录，重装后目录
    重建，锚点变化；普通覆盖升级不会改变这个目录的创建时间。
    """
    try:
        return str(int(os.path.getctime(install_dir)))
    except OSError:
        return ""


def reinstall_detected(cfg: dict, config_path: str, install_dir: str) -> bool:
    """判断当前启动是否是“卸载后重装”（而不是覆盖升级）。"""
    current = install_anchor(install_dir)
    if not current:
        return False
    old = str(cfg.get("install_anchor") or "").strip()
    if old:
        return old != current
    # 从没有锚点的旧版本迁移：如果安装目录比 config.json 新，说明配置是上一次
    # 安装留下的，当前目录是重装后新建的。已有老用户覆盖升级时目录更旧。
    try:
        if not config_exists(config_path):
            return False
        return os.path.getctime(install_dir) > os.path.getmtime(config_path) + 2
    except OSError:
        return False


def mark_install_anchor(cfg: dict, install_dir: str) -> None:
    current = install_anchor(install_dir)
    if current:
        cfg["install_anchor"] = current


def reset_for_reinstall(cfg: dict) -> None:
    """卸载重装时只重置首启/引导状态，保留 API Key、模型、账本等用户数据。"""
    cfg["onboarding_state"] = STATE_PENDING
    cfg["onboarding_version"] = ""
    cfg["onboarding_done_at"] = ""
    cfg["onboarding_api_skipped"] = False
    cfg["onboarding_tour_skipped"] = False
    cfg["onboarding_resume_step"] = 1
    # 一次性消费：确保重装后仍会自动开一次契约，但取消后不会无限重弹。
    cfg["onboarding_reinstall"] = True
    # 重装用户也应该看到“当前版本”的更新说明；如果沿用上次安装的已读版本，
    # 引导结束后会误判成已看过，直接跳过。
    cfg["whats_new_seen_version"] = ""


def config_exists(path: str) -> bool:
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False
