"""审核 11-10（总控）两处 bug：① 合租房餐桌是家用 dining_table（免费、全天、不收餐费）；② 柜台 / 鱼摊 use 无即时需求效果，只承载 buy / sell。"""
from datetime import datetime

from game import world_state
from game.object_types import OBJECT_TYPES
from game.time_state import GAME_TZ
from tests.conftest import action, place, walk_done
from tests.test_w9_map_v2 import v12  # noqa: F401


def _agent(client, aid, name=None):
    return client.post("/player/join", json={"name": name or aid, "controller": "agent", "profile": {"agent_id": aid}}).json()["playerId"]


def _at(fake_clock, h, m=0):
    fake_clock.t = datetime(2026, 11, 10, h, m, tzinfo=GAME_TZ).timestamp()


def test_home_table_is_free_all_day_and_not_a_restaurant(client, v12, fake_clock):
    _at(fake_clock, 15, 30)                                                              # 餐厅午休关门时段
    whale = _agent(client, "whale")
    t = world_state.get_object_by_id("table_home")
    assert t["type"] == "dining_table" and t.get("openHours") is None and t.get("shop") is None
    place(whale, 7, 12, "up")
    gold0 = world_state._players[whale]["gold"]
    r = action(client, whale, "use")
    assert r["success"], r
    assert world_state._players[whale]["gold"] == gold0                                   # 不收 20 金币
    assert "dining" in world_state._players[whale]["tags"]
    assert action(client, whale, "leave")["success"]
    # 餐厅桌仍收费、仍看营业时间
    rt = world_state.get_object_by_id("table_rest_1")
    assert rt["type"] == "restaurant_table" and rt["openHours"]


def test_shop_counter_and_fish_stall_have_no_instant_effects(client, v12, fake_clock):
    _at(fake_clock, 12, 0)
    whale = _agent(client, "whale")
    for typ in ("shop_counter", "fish_stall"):
        assert OBJECT_TYPES[typ]["effects"] == [] and OBJECT_TYPES[typ]["prototype"] == "instant"
    p = world_state._players[whale]
    p["fullness"] = 40.0; p["social"] = 40.0
    place(whale, 27, 22, "right")                                                           # 杂货店柜台
    r = action(client, whale, "use")
    assert r["success"] and "buy" in r["result"]["message"]
    assert p["fullness"] == 40.0 and p["social"] == 40.0                                 # 不买不白吃
    assert action(client, whale, "buy", {"item": "bread"})["success"]                     # 买卖照常
    # 其他「商店类」：bar 是 continuous 休息（有效果，收费问题待主播）；notice_board fun +3 是设定里有的
    assert OBJECT_TYPES["bar"]["prototype"] == "continuous" and OBJECT_TYPES["notice_board"]["effects"] == [{"type": "instant_effect", "key": "fun", "value": 3}]
