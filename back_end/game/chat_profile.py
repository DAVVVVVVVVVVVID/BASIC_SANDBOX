"""
对话协议常量组（X4，`SANDBOX_CHAT_PROFILE = b9 | ait | nolimit`，默认 b9）。

| 键 | b9（现状） | ait（AI Town 原参数） | nolimit（C0+） |
|---|---|---|---|
| invite_timeout        | 60   | 60  | 60  |  邀请超时（秒，墙钟）
| walking_over_timeout  | 30   | 60  | 30  |  走近超时，到时直接建房
| max_messages          | 16   | 8   | 0   |  房间消息上限（含招呼与接受回复），0 = 无上限
| max_duration          | 0    | 600 | 0   |  房间最长存活秒数（墙钟），0 = 不限
| awkward_timeout       | 0    | 60  | 0   |  多久没人说话就散（秒），0 = 不限；ait 下也是「被邀请者等多久才可先开口」
| cooldown_self         | 60   | 15  | 60  |  退出后本人多久不能再发起 / 接受
| cooldown_pair         | 15   | 60  | 15  |  同一对人多久不能再聊
| creator_first         | no   | yes | no  |  发起者先开口：其他人在发起者说话前（或 awkward_timeout 过后）不能发言
注意：AI Town 是「任意人 15 s、同一人 60 s」；我们的 B9 现值是「本人 60 s、同一对 15 s」——两个数是反的，b9 档保留现状以免改变主镇行为，ait 档按 AI Town。
环境变量 SANDBOX_CHAT_OVERRIDES='{"max_messages": 12}' 可在任一档上覆盖单项（bench 调参用）。
"""
import json
import os

PROFILES: dict[str, dict] = {
    "b9":      {"invite_timeout": 60.0, "walking_over_timeout": 30.0, "max_messages": 16, "max_duration": 0.0, "awkward_timeout": 0.0,
                "cooldown_self": 60.0, "cooldown_pair": 15.0, "creator_first": False},
    "ait":     {"invite_timeout": 60.0, "walking_over_timeout": 60.0, "max_messages": 8, "max_duration": 600.0, "awkward_timeout": 60.0,
                "cooldown_self": 15.0, "cooldown_pair": 60.0, "creator_first": True},
    "nolimit": {"invite_timeout": 60.0, "walking_over_timeout": 30.0, "max_messages": 0, "max_duration": 0.0, "awkward_timeout": 0.0,
                "cooldown_self": 60.0, "cooldown_pair": 15.0, "creator_first": False},
}
_state = {"name": None, "values": {}}


def _load() -> None:
    name = (os.environ.get("SANDBOX_CHAT_PROFILE") or "b9").strip().lower()
    if name not in PROFILES:
        raise ValueError(f"SANDBOX_CHAT_PROFILE must be one of {sorted(PROFILES)}, got {name!r}")
    vals = dict(PROFILES[name])
    raw = os.environ.get("SANDBOX_CHAT_OVERRIDES", "").strip()
    if raw:
        for k, v in json.loads(raw).items():
            if k not in vals:
                raise ValueError(f"unknown chat profile key {k!r}")
            vals[k] = type(vals[k])(v)
    _state["name"] = name; _state["values"] = vals


def set_profile(name: str, **overrides) -> dict:
    """测试 / 夹具用：切档（不动环境变量）。"""
    if name not in PROFILES:
        raise ValueError(name)
    vals = dict(PROFILES[name]); vals.update(overrides)
    _state["name"] = name; _state["values"] = vals
    return current()


def current() -> dict:
    if _state["name"] is None:
        _load()
    return {"name": _state["name"], **_state["values"]}


def get(key: str):
    if _state["name"] is None:
        _load()
    return _state["values"][key]


def _reset_for_tests() -> None:
    _state["name"] = None; _state["values"] = {}
