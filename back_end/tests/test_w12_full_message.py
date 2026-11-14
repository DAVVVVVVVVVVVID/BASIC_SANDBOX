"""world-v1.2.6：满员（object_full）提示按物品名 + 人数给，不再借用类型通用失败语。"""
from tests.conftest import action, place
from tests.test_w9_map_v2 import _agent, v12  # noqa: F401  (fixture)
from game import world_state


def test_bench_full_message_names_object_and_count(client, v12):
    a, b, c = (_agent(client, x) for x in ("whale", "achan", "claudine"))
    for pid, x in ((a, 23), (b, 24)):
        place(pid, x, 12, "up")
        assert action(client, pid, "use")["success"]
    place(c, 23, 12, "up")
    r = action(client, c, "use")
    assert r["success"] is False and r["reason"] == "object_full"
    assert r["result"]["message"] == "长椅有人在用（已满 2/2）。" and r["result"]["currentUsers"] == 2 and r["result"]["maxUsers"] == 2


def test_legacy_english_type_name_gets_chinese_in_full_message(client, v12):
    a, b = _agent(client, "whale"), _agent(client, "achan")
    obj = world_state.get_object_by_id("bed_whale")
    place(a, 3, 13, "up"); assert action(client, a, "use")["success"]
    place(b, 3, 13, "up")
    r = action(client, b, "use")
    assert r["reason"] == "object_full" and r["result"]["message"] == "床有人在用（已满 1/1）。" and obj["name"] == "bed"   # /world 的 name 不动
