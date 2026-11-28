"""试用标记：删掉 trial 记录后，重装/清理不能重新领试用。"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from sch_testenv import enable  # noqa: E402

CFG = enable(prefix="sch_trial_marker_")
from modules import license as lic, settings  # noqa: E402


def main() -> None:
    assert lic.trial_status() [0] == "fresh"
    lic.start_trial()
    assert os.path.isfile(os.path.join(CFG, "trial_used")), "trial_used marker missing"

    # 模拟卸载器清掉 trial.json / trial_seed：标记必须留下。
    for name in ("trial.json", "trial_seed"):
        try:
            os.remove(os.path.join(CFG, name))
        except FileNotFoundError:
            pass
    assert lic._trial_used_present() is True
    state, _days, msg = lic.trial_status()
    assert state == "expired", (state, msg)

    # 只有把标记也删掉，才会回到 fresh；这是离线方案无法阻止的极限。
    for name in ("trial_used",):
        try:
            os.remove(os.path.join(CFG, name))
        except FileNotFoundError:
            pass
    assert lic._trial_used_present() is False
    assert lic.trial_status()[0] == "fresh"
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
