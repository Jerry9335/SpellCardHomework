"""首次安装判定 / 状态标记回归。"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules import first_run  # noqa: E402


def main() -> None:
    # 全新安装：fresh + 没有配置
    cfg = {}
    assert first_run.should_show(cfg, "fresh", False) is True

    # 同机重装/目录残留旧 config，但激活前仍是 fresh：也要走首次安装契约
    assert first_run.should_show({}, "fresh", True) is True

    # 已授权/试用但从未配置接口：仍然补首次契约，否则主界面无法答题
    assert first_run.should_show({}, "licensed", True) is True
    assert first_run.should_show({}, "trial", False) is True
    assert first_run.should_show({}, "expired", True) is True
    assert first_run.should_show({}, "tampered", True) is True

    # 已配置过 API Key 的老用户即使授权 expired 也不弹
    assert first_run.has_setup({"api_key": "sk-test"}) is True
    assert first_run.should_show({"api_key": "sk-test"}, "expired", True) is False
    assert first_run.should_show({"api_key": "sk-test"}, "licensed", True) is False
    assert first_run.has_setup({"model": "qwen2.5:7b",
                                "base_url": "http://localhost:11434/v1"}) is True

    # done 永不自动弹；legacy 只有在确实配置过接口时才算老用户
    assert first_run.should_show({"onboarding_state": "done"}, "fresh", False) is False
    assert first_run.should_show({"onboarding_state": "legacy"}, "fresh", False) is True
    assert first_run.should_show({"onboarding_state": "legacy",
                                  "api_key": "sk-test"}, "fresh", False) is False

    # 中断可续
    assert first_run.should_show({"onboarding_state": "pending"}, "licensed", True) is True
    assert first_run.is_resume({"onboarding_state": "in_progress"}) is True

    # 状态标记
    first_run.mark_pending(cfg)
    assert cfg["onboarding_state"] == "pending"
    assert cfg["onboarding_resume_step"] == 1
    first_run.mark_in_progress(cfg, 4)
    assert cfg["onboarding_state"] == "in_progress"
    assert cfg["onboarding_resume_step"] == 4
    first_run.mark_done(cfg, "1.0.6-rc.03", True)
    assert cfg["onboarding_state"] == "done"
    assert cfg["onboarding_version"] == "1.0.6-rc.03"
    assert cfg["onboarding_api_skipped"] is True
    assert cfg["onboarding_done_at"]
    assert first_run.is_resume(cfg) is False

    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
        f.write("{}")
        path = f.name
    try:
        assert first_run.config_exists(path) is True
        assert first_run.config_exists(path + ".missing") is False
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    print("first_run OK")


if __name__ == "__main__":
    main()
