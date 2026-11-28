"""测试用的小门牌：让授权模块在源码模式下认 `SHINICHI_CONFIG_DIR`。

灵梦：授权那块现在只认「源码运行 + `--test-config`」，不然一跑测试就往
真赛钱箱（`%APPDATA%` 和注册表）里伸手。这个模块就是那张测试专用通行证。

用法：

    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from sch_testenv import enable

    cfg = enable(prefix="sch_first_")
"""
from __future__ import annotations

import os
import sys
import tempfile

TEST_FLAG = "--test-config"


def enable(config_dir: str | None = None, prefix: str = "sch_test_") -> str:
    """开启测试门，返回这次使用的配置目录。

    - 设好 `SHINICHI_CONFIG_DIR`
    - 往 `sys.argv` 里补一个 `--test-config`（子进程要自己再传一次）
    """
    cfg = config_dir or tempfile.mkdtemp(prefix=prefix)
    try:
        os.makedirs(cfg, exist_ok=True)
    except OSError:
        pass
    os.environ["SHINICHI_CONFIG_DIR"] = cfg
    try:
        if TEST_FLAG not in sys.argv:
            sys.argv.append(TEST_FLAG)
    except Exception:
        pass
    return cfg
