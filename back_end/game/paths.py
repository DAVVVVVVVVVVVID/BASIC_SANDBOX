"""数据目录（SQLite 检查点、JSONL 行动日志）。

默认 back_end/data/，可用环境变量 SANDBOX_DATA_DIR 覆盖（测试与多实例用）。
每次调用都读环境变量，保证测试里切换目录即时生效。
"""
import os
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parent.parent / "data"


def data_dir() -> Path:
    p = Path(os.environ.get("SANDBOX_DATA_DIR", str(_DEFAULT)))
    p.mkdir(parents=True, exist_ok=True)
    return p
