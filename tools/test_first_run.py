"""首次安装判定 / 状态标记回归。"""
from __future__ import annotations

import os
import sys
import tempfile
import time

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

    # 已授权/试用但从未配置接口：不再自动弹全屏契约，用户去设置中心补。
    assert first_run.should_show({}, "licensed", True) is False
    assert first_run.should_show({}, "trial", False) is False
    assert first_run.should_show({}, "expired", True) is False
    assert first_run.should_show({}, "tampered", True) is False
    # 重装由一次性标记触发，消费后不再自动弹。
    assert first_run.should_show({"onboarding_reinstall": True},
                                 "licensed", True) is True

    # 已配置过 API Key 的老用户即使授权 expired 也不弹
    assert first_run.has_setup({"api_key": "sk-test"}) is True
    assert first_run.should_show({"api_key": "sk-test"}, "expired", True) is False
    assert first_run.should_show({"api_key": "sk-test"}, "licensed", True) is False
    assert first_run.has_setup({"model": "qwen2.5:7b",
                                "base_url": "http://localhost:11434/v1"}) is True

    # done / legacy / 中断状态都不自动弹；设置中心负责补契约和重看引路。
    assert first_run.should_show({"onboarding_state": "done"}, "fresh", False) is False
    assert first_run.should_show({"onboarding_state": "legacy"}, "fresh", False) is False
    assert first_run.should_show({"onboarding_state": "legacy",
                                  "api_key": "sk-test"}, "fresh", False) is False
    assert first_run.should_show({"onboarding_state": "pending"}, "licensed", True) is False
    assert first_run.should_show({"onboarding_state": "in_progress"}, "fresh", True) is False
    assert first_run.is_resume({"onboarding_state": "in_progress"}) is True

    # 状态标记
    first_run.mark_pending(cfg)
    assert cfg["onboarding_state"] == "pending"
    assert cfg["onboarding_resume_step"] == 1
    first_run.mark_in_progress(cfg, 4)
    assert cfg["onboarding_state"] == "in_progress"
    assert cfg["onboarding_resume_step"] == 4
    first_run.mark_done(cfg, "1.1.7", True)
    assert cfg["onboarding_state"] == "done"
    assert cfg["onboarding_version"] == "1.1.7"
    assert cfg["onboarding_api_skipped"] is True
    assert cfg["onboarding_tour_skipped"] is False
    assert cfg["onboarding_done_at"]
    assert first_run.is_resume(cfg) is False
    first_run.mark_done(cfg, "1.1.7", True, tour_skipped=True)
    assert cfg["onboarding_tour_skipped"] is True

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

    # 重装必须由安装器一次性标记触发，不能再从目录 ctime 猜。
    with tempfile.TemporaryDirectory() as d:
        old_env = os.environ.get("SHINICHI_CONFIG_DIR")
        os.environ["SHINICHI_CONFIG_DIR"] = d
        try:
            marker = first_run.onboarding_request_path()
            assert marker == os.path.join(d, "onboarding_request.json")
            assert first_run.consume_onboarding_request() is False
            with open(marker, "w", encoding="utf-8") as f:
                f.write('{"reason":"fresh_or_reinstall"}')
            assert first_run.consume_onboarding_request() is True
            assert not os.path.exists(marker)
            assert first_run.consume_onboarding_request() is False

            # 覆盖升级：即使配置里有旧残留，也只清一次性标记，不改 done。
            upgrade = {"onboarding_state": "done",
                       "onboarding_reinstall": True,
                       "onboarding_version": "1.1.7",
                       "api_key": "sk-keep-me"}
            assert first_run.clear_stale_reinstall(upgrade) is True
            assert upgrade["onboarding_reinstall"] is False
            assert upgrade["onboarding_state"] == "done"
            assert first_run.should_show(upgrade, "licensed", True) is False
            assert first_run.clear_stale_reinstall(upgrade) is False

            done = {"onboarding_state": "done", "onboarding_version": "1.1.7",
                    "onboarding_resume_step": 9, "onboarding_api_skipped": True,
                    "api_key": "sk-keep-me"}
            first_run.reset_for_reinstall(done)
            assert done["onboarding_state"] == "pending"
            assert done["onboarding_resume_step"] == 1
            assert done["onboarding_reinstall"] is True
            assert done["api_key"] == "sk-keep-me"
        finally:
            if old_env is None:
                os.environ.pop("SHINICHI_CONFIG_DIR", None)
            else:
                os.environ["SHINICHI_CONFIG_DIR"] = old_env
    print("first_run OK")


if __name__ == "__main__":
    main()
