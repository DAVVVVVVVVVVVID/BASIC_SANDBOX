"""
七变量数值配置（world-v1.1，game/needs.json（模块名 needs_cfg，game/needs.py 是需求标签））。agent 只读 /state，所有加减都在沙盒：
- 衰减：醒 / 睡两套（睡 = tags 含 sleeping）；直播中（scene live）饱腹再扣；使用 work 类物品（tags 含 working）精力再扣。
- 来源：床 +10/h（object_types）；对话 +32/h（聊天房按在房计时）/ say 15 分钟窗口 +8；同桌 table_social；QQ 每条 +1 每小时 ≤ 12；下播 +10；娱乐按物品 *_regen。
"""
import json
from pathlib import Path

_PATH = Path(__file__).with_name("needs.json")
_CFG: dict = {}


def reload(path: Path | str | None = None) -> dict:
    global _PATH
    if path is not None:
        _PATH = Path(path)
    _CFG.clear(); _CFG.update(json.loads(_PATH.read_text(encoding="utf-8")))
    return dict(_CFG)


def cfg() -> dict:
    if not _CFG:
        reload()
    return _CFG


def per_hour(state: str, var: str) -> float:
    """state: awake | asleep。每小时点数（负为衰减）。"""
    return float(cfg().get("decay_per_hour", {}).get(state, {}).get(var, 0.0))


def extra_per_hour(kind: str, var: str) -> float:
    """kind: live | work。"""
    return float(cfg().get("extra_per_hour", {}).get(kind, {}).get(var, 0.0))


def conversation() -> dict:
    return dict(cfg().get("conversation", {}))


def qq() -> dict:
    return dict(cfg().get("qq", {}))


def live_session_social() -> float:
    return float(cfg().get("live_session_social", 0.0))


def night_energy_mult() -> float:
    return float(cfg().get("night_energy_mult", 1.0))
