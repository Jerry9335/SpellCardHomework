"""首次安装判定与新手引导状态。

这里刻意不使用“版本号是否变化”来判断是否重弹：
- 全新安装：授权状态为 fresh 且激活前没有 config.json；
- 老用户：已有配置，或激活前不是 fresh；
- 升级：不重弹，保留 done / legacy / pending；
- 卸载重装：只认安装器写的一次性 onboarding_request.json；
- 中途关闭：onboarding_state 为 pending / in_progress，下次不自动重弹；
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
    # 重装由安装器写一次性请求；消费后不会反复弹。
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


def onboarding_request_path() -> str:
    """安装器写入的一次性“新装/重装”请求。"""
    from modules import settings

    return os.path.join(settings.config_dir(), "onboarding_request.json")


def consume_onboarding_request() -> bool:
    """读取并删除安装器标记；只能真正消费一次。

    标记存在时返回 True，调用方再 reset_for_reinstall()。
    不读取安装目录 ctime —— 覆盖升级时 Inno 也可能重建目录，那会把升级误判成重装。
    """
    path = onboarding_request_path()
    if not os.path.isfile(path):
        return False
    try:
        os.remove(path)
    except OSError:
        # 删不掉就宁可继续保留，下一次启动还能再处理；不要静默吞掉重装请求。
        return False
    return True


def clear_stale_reinstall(cfg: dict) -> bool:
    """升级路径清理旧版本残留的 onboarding_reinstall。

    只清一次性标记，不动 done / legacy / pending 状态；pending 仍按现有规则
    不自动重弹，交给设置中心处理。
    """
    if cfg.get("onboarding_reinstall"):
        cfg["onboarding_reinstall"] = False
        return True
    return False


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
