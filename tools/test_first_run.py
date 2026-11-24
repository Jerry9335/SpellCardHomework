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

    # 卸载重装识别：安装目录重建后 ctime 变化；覆盖升级锚点不变。
    with tempfile.TemporaryDirectory() as d:
        install = os.path.join(d, "app")
        os.mkdir(install)
        cfg_path = os.path.join(d, "config.json")
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write("{}")
        old = time.time() - 3600
        os.utime(cfg_path, (old, old))
        # 旧版本没有锚点：安装目录比 config 新 => 视为重装。
        assert first_run.reinstall_detected({}, cfg_path, install) is True
        anchor = first_run.install_anchor(install)
        assert anchor
        # 已有锚点且一致 => 普通启动/覆盖升级。
        assert first_run.reinstall_detected({"install_anchor": anchor},
                                            cfg_path, install) is False
        # 锚点变化 => 重装。
        assert first_run.reinstall_detected({"install_anchor": "1"},
                                            cfg_path, install) is True
        done = {"onboarding_state": "done", "onboarding_version": "1.0.6-rc.03",
                "onboarding_resume_step": 9, "onboarding_api_skipped": True,
                "api_key": "sk-keep-me"}
        first_run.reset_for_reinstall(done)
        assert done["onboarding_state"] == "pending"
        assert done["onboarding_resume_step"] == 1
        assert done["api_key"] == "sk-keep-me"
    print("first_run OK")


if __name__ == "__main__":
    main()
