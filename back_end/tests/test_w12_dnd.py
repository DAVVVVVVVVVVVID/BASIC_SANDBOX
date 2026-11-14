"""world-v1.3：① 小千 → 克劳蒂娜（claudine）改名与旧 id 别名；② 阿蝉静态勿扰（主播本人操控的人类玩家）。"""
import time

from game import world_state, ticker, qq
from tests.conftest import action, place
from tests.test_w9_map_v2 import _agent, v12  # noqa: F401
from tests.test_w11_knock import _at, _tick


def _human(client, name="阿蝉", agent_id="achan", **kw):
    body = {"name": name, "controller": "human", "profile": {"agent_id": agent_id} if agent_id else None, **kw}
    return client.post("/player/join", json=body).json()["playerId"]


def test_rename_claudine_ids_and_legacy_alias(client, v12):
    m = client.get("/world", params={"fields": "map,objects"}).json()
    assert "claudine_house" in {b["id"] for b in m["map"]["buildings"]} and "door_claudine" in {e["id"] for e in m["map"]["edges"]}
    assert {"bed_claudine", "stove_claudine", "fridge_claudine", "table_claudine", "bush_claudine"} <= {o["id"] for o in m["objects"]}
    assert world_state._HOMES["claudine"] == "claudine_room" and "npc_xiaoqian" not in world_state._HOMES
    assert qq.display_name("claudine") == "克劳蒂娜"                         # 没人在线：配置名
    old = _agent(client, "npc_xiaoqian", name="克劳蒂娜")                   # 过渡期 C 还发旧 id → 自动归到新 id
    assert world_state._players[old]["agent_id"] == "claudine" and qq.account_of(world_state._players[old]) == "claudine"
    assert qq.resolve_account("小克") == "claudine" and qq.resolve_account("小千") == "claudine" and qq.resolve_account("npc_xiaoqian") == "claudine"
    c = client.get("/qq/contacts", params={"player": _agent(client, "whale")}).json()
    assert "claudine" in {x["account"] for x in c["contacts"]}


def test_human_achan_defaults_dnd_and_claims_identity(client, v12):
    a = _human(client)
    p = client.get(f"/player/{a}").json()
    assert p["dnd"] is True and p["agent_id"] == "achan" and "dnd" in p["tags"] and p["controller"] == "human"
    assert client.get(f"/player/{a}/state").json()["dnd"] is True
    assert {k["door_id"] for k in p["keys"]} == {"door_home"}                        # 身份认领：合租房钥匙照发
    assert _human(client, name="路人", agent_id=None) and client.get("/world", params={"fields": "players"}).json()["players"]
    others = {x["name"]: x for x in client.get("/world", params={"fields": "players"}).json()["players"]}
    assert others["路人"]["dnd"] is False and "dnd" not in others["路人"]["tags"]
    b = _human(client, name="阿蝉", dnd=False)                                        # join 参数可关
    assert client.get(f"/player/{b}").json()["dnd"] is False


def test_human_identity_uses_identity_gold_and_ledger(client, v12):
    a = _human(client)
    assert world_state._players[a]["gold"] == 3000                                 # achan 的初始金币，不是人类默认 300
    assert client.get("/admin/metrics").json()["accounts"]["achan"] == 3000
    world_state._players[a]["gold"] = 2900
    client.delete(f"/player/{a}/leave")
    b = _human(client)
    assert world_state._players[b]["gold"] == 2900                                 # 余额留在账户上，再来接着用
    from game import economy
    assert economy.opened_at("achan") is None                                      # 不开经济户：无日薪 / 房租


def test_dnd_static_vars_and_admin_toggle(client, v12, fake_clock):
    a = _human(client)
    _at(fake_clock, 12, 0); _tick(fake_clock, 1)
    before = {k: world_state._players[a][k] for k in ("fullness", "energy", "social", "fun", "mood")}
    _tick(fake_clock, 3600)
    assert {k: world_state._players[a][k] for k in before} == before            # 静态：一小时一点不掉
    r = client.post(f"/admin/player/{a}/dnd", json={"on": False}).json()
    assert r["ok"] and r["dnd"] is False and "dnd" not in r["tags"]
    _tick(fake_clock, 3600)
    assert world_state._players[a]["fullness"] < before["fullness"]              # 关掉就照常衰减
    assert client.post(f"/admin/player/{a}/dnd", json={"on": True}).json()["dnd"] is True
    assert client.post("/admin/player/nobody/dnd", json={"on": True}).status_code == 404


def test_dnd_knock_is_busy_unless_someone_else_home(client, v12, fake_clock):
    _at(fake_clock, 15, 0)
    a = _human(client); cl = _agent(client, "claudine")
    place(a, 4, 31, "down")                                                         # 阿蝉在 2F 自己房间
    place(cl, 9, 18, "up")
    r = action(client, cl, "knock", {"door_id": "door_home"})
    assert r["success"] is False and r["reason"] == "busy" and r["result"]["dnd"] == [a] and "在忙" in r["result"]["message"]
    assert client.get(f"/player/{cl}").json()["door_request"] is None             # 没挂请求，不用等 90 s
    whale = _agent(client, "whale"); place(whale, 9, 13, "down")                   # 鲸仔也在家且清醒 → 照常敲，只通知鲸仔
    r = action(client, cl, "knock", {"door_id": "door_home"})
    assert r["success"] and r["result"]["notified"] == [whale]


def test_dnd_tags_working_at_home_and_qq_penalty_exempt(client, v12, fake_clock):
    _at(fake_clock, 10, 0)
    a = _human(client); whale = _agent(client, "whale"); cl = _agent(client, "claudine")
    place(a, 4, 31, "down")
    snap = {x["id"]: x for x in client.get("/world", params={"fields": "players"}).json()["players"]}
    assert snap[a]["dnd"] is True and {"dnd", "working"} <= set(snap[a]["tags"])
    place(a, 9, 13, "down")
    snap = {x["id"]: x for x in client.get("/world", params={"fields": "players"}).json()["players"]}
    assert "working" not in snap[a]["tags"] and "dnd" in snap[a]["tags"]
    assert client.post("/qq/send", json={"entity_id": whale, "to": "achan", "text": "在吗"}).json()["success"]
    assert client.post("/qq/send", json={"entity_id": whale, "to": "claudine", "text": "在吗"}).json()["success"]
    ck_a, ck_c = qq._closeness_key("achan"), qq._closeness_key("claudine")
    w = world_state._players[whale]
    w["closeness"][ck_a] = 10.0; w["closeness"][ck_c] = 10.0                    # 先给点亲密度，不然 0 封底看不出扣
    before_a, before_c = 10.0, 10.0
    for _ in range(5):
        _tick(fake_clock, 3600)                                                     # 5 游戏小时未读
    assert w["closeness"][ck_a] > before_a - 0.5                                    # 收件人勿扰：不扣（只有每日自然衰减的零点几）
    assert w["closeness"][ck_c] < before_c - 2.5                                    # 对照：克劳蒂娜未读照扣（2 h 后每小时 −1）


def test_dnd_human_survives_heartbeat_timeout(client, v12):
    a = _human(client); b = _human(client, name="路人", agent_id=None)
    world_state._last_seen[a] = time.time() - 100; world_state._last_seen[b] = time.time() - 100
    world_state._cleanup_stale_players()
    assert a in world_state._players and world_state._players[a]["online"] is False and b not in world_state._players
    assert client.post(f"/player/{a}/heartbeat").json()["online"] is True       # 主播回来心跳即在线，位置没动
