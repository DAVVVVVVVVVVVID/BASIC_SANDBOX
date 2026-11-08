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
from game import qq, economy, production, commissions, doors, speech  # noqa: E402


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
    qq._reset_for_tests(); economy._reset_for_tests(); production._reset_for_tests(); commissions._reset_for_tests(); doors._reset_for_tests(); speech._reset_for_tests()
    monkeypatch.setitem(economy.cfg()["commissions"], "daily_p", 0.0)     # W11：测试里默认不随机出委托（要的测试自己 setitem 1.0）
    time_state._reset_for_tests()
    time_state.set_clock(None)
    action_log._reset_for_tests()
    ticker._reset_for_tests()
    yield
    world_state._reset_for_tests()
    chat_state._reset_for_tests()
    qq._reset_for_tests(); economy._reset_for_tests(); production._reset_for_tests(); commissions._reset_for_tests(); doors._reset_for_tests(); speech._reset_for_tests()
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


# ── 地图上的已知位置（scripts/gen_map.py 生成的 map.json / objects.json）──────────
BED_ID   = "bed_whale"           # 占 (3,3)(3,4)；站 (3,5) 朝 up 或 (4,3) 朝 left 可用
DESK_ID  = "desk_whale"          # 占 (10,3)；站 (10,4) 朝 up 可用
PHONE_ID = "phone_whale"         # 占 (10,7)；站 (10,8) 朝 up
STREAM_ID = "stream_desk_whale"  # 占 (3,13)；站 (3,12) 朝 down
FRIDGE_ID = "fridge_kitchen"     # 占 (24,3)；站 (24,4) 朝 up
BED_STAND  = (3, 5, "up")
BED_STAND2 = (4, 3, "left")      # 同一张床的另一侧
DESK_STAND = (10, 4, "up")
PHONE_STAND = (10, 8, "up")
STREAM_STAND = (3, 12, "down")
FRIDGE_STAND = (24, 4, "up")


def place(player_id: str, x: int, y: int, facing: str) -> None:
    """测试用：直接把 player 放到某格并设朝向。"""
    from game.world_state import update_player_position
    update_player_position(player_id, x, y, facing)


def join(client, name="tester") -> str:
    r = client.post("/player/join", json={"name": name})
    assert r.status_code == 200
    return r.json()["playerId"]


def walk_done(pid: str, fake_clock, max_s: int = 3000) -> int:
    """§3.36 测试用：推 ticker + 拨游戏钟（1 s/步）直到该玩家走完（不在走路队列里）。返回用掉的游戏秒。"""
    from game import world_state, ticker
    ticker.tick_once(checkpoint=False)
    used = 0
    while pid in world_state._walks and used < max_s:
        fake_clock.advance(1.0); ticker.tick_once(checkpoint=False); used += 1
    assert pid not in world_state._walks, f"{pid} still walking after {max_s}s: {world_state.walk_view(pid)}"
    return used


def action(client, pid: str, type_: str, payload: dict | None = None, **kw):
    body = {"entityId": pid, "action": {"type": type_, "payload": payload or {}}, **kw}
    r = client.post("/action", json=body)
    assert r.status_code == 200, r.text
    return r.json()
