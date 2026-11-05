"""
测试公共夹具。

- 每个测试用独立的 SANDBOX_DATA_DIR（tmp_path），并清空全部模块级运行时状态。
- `client` 不带 lifespan（不启动后台 ticker），保证确定性；需要后台 ticker 的测试自己用
  `with TestClient(app) as c:`。
- `fake_clock` 提供可手动推进的墙钟，注入 time_state。
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402


class FakeClock:
    def __init__(self, start: float = 1_800_000_000.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> float:
        self.t += seconds
        return self.t


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("SANDBOX_DATA_DIR", str(tmp_path / "data"))
    from game import world_state, chat_state, time_state, action_log, ticker, self_sync
    self_sync._reset_for_tests()
    self_sync.configure(enabled=False)        # 默认不碰网络；需要的测试自己 configure(transport=...)
    world_state._reset_for_tests()
    chat_state._reset_for_tests()
    time_state._reset_for_tests()
    time_state.set_clock(None)
    action_log._reset_for_tests()
    ticker._reset_for_tests()
    yield
    world_state._reset_for_tests()
    chat_state._reset_for_tests()
    time_state._reset_for_tests()
    time_state.set_clock(None)
    action_log._reset_for_tests()
    ticker._reset_for_tests()
    self_sync._reset_for_tests()


@pytest.fixture
def fake_clock():
    from game import time_state
    clk = FakeClock()
    time_state.set_clock(clk)
    time_state.reset_time()
    time_state.set_running(True)
    yield clk
    time_state.set_clock(None)


@pytest.fixture
def client():
    from main import app
    return TestClient(app)


# ── 地图上的已知位置（map.json / objects.json）────────────────────────────────
BED_ID   = "bed_1780400782091"   # 占 (11,0)(11,1)；站 (11,2) 朝 up 可用
DESK_ID  = "desk_1780400974312"  # 占 (46,0)；站 (46,1) 朝 up 可用
BED_STAND  = (11, 2, "up")
DESK_STAND = (46, 1, "up")


def place(player_id: str, x: int, y: int, facing: str) -> None:
    """测试用：直接把 player 放到某格并设朝向。"""
    from game.world_state import update_player_position
    update_player_position(player_id, x, y, facing)


def join(client, name="tester") -> str:
    r = client.post("/player/join", json={"name": name})
    assert r.status_code == 200
    return r.json()["playerId"]


def action(client, pid: str, type_: str, payload: dict | None = None, **kw):
    body = {"entityId": pid, "action": {"type": type_, "payload": payload or {}}, **kw}
    r = client.post("/action", json=body)
    assert r.status_code == 200, r.text
    return r.json()
