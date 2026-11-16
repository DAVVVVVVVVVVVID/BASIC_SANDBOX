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
    b = _human(client, name="阿蝉", agent_id=None, dnd=False)                         # join 参数可关（不带 agent_id，否则 v1.3.4 会接管上面那个）
    assert client.get(f"/player/{b}").json()["dnd"] is False


def test_human_identity_keys_follow_identity_not_legacy_rule(client, v12):
    """v1.3.3：带 agent_id 的人类按身份发钥匙；旧「任何人类一把合租房钥匙」只留给没认领身份的人类（C 冒烟发现人类小克拿到合租房钥匙）。"""
    hc = _human(client, name="克劳蒂娜", agent_id="claudine")
    assert [k["door_id"] for k in client.get(f"/player/{hc}").json()["keys"]] == ["door_claudine"]
    ha = _human(client)
    assert [k["door_id"] for k in client.get(f"/player/{ha}").json()["keys"]] == ["door_home"]
    anon = _human(client, name="路人", agent_id=None)
    assert "door_claudine" not in [k["door_id"] for k in client.get(f"/player/{anon}").json()["keys"]]


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
    p = world_state._players[a]; p["fullness"] = 40.0; p["social"] = 30.0
    _tick(fake_clock, 1)
    assert all(p[k] == 100.0 for k in ("fullness", "energy", "social", "fun"))   # v1.3.4 ①：勿扰 = 四项钉满值
    _tick(fake_clock, 3600)
    assert all(p[k] == 100.0 for k in ("fullness", "energy", "social", "fun"))
    r = client.post(f"/admin/player/{a}/dnd", json={"on": False}).json()
    assert r["ok"] and r["dnd"] is False and "dnd" not in r["tags"]
    _tick(fake_clock, 3600)
    assert p["fullness"] < 100.0                                                  # 关掉就照常衰减
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


def test_dnd_auto_park_takeover_and_persistent_leave(client, v12, fake_clock):
    """v1.3.4 ②③：主播离线（心跳超时 / leave）→ 开 dnd 并送回 achan_room；客户端第一个动作 → 关 dnd；同身份再 join = 接管同一玩家。"""
    _at(fake_clock, 15, 0)
    a = _human(client)
    r = client.post("/action", json={"entityId": a, "action": {"type": "turn", "payload": {"direction": "left"}}}).json()
    assert r["success"] and world_state._players[a]["dnd"] is False                # 第一个动作 = 接管
    place(a, 9, 13, "down")
    world_state._last_seen[a] = time.time() - 100
    world_state._cleanup_stale_players()
    p = world_state._players[a]
    assert p["dnd"] is True and p["online"] is False and world_state.get_zone_at(p["position"]["x"], p["position"]["y"])["arena"] == "achan_room"
    r = client.post("/player/join", json={"name": "阿蝉", "controller": "human", "profile": {"agent_id": "achan"}}).json()
    assert r["playerId"] == a and r.get("takeover") is True and world_state._players[a]["online"] is True and world_state._players[a]["dnd"] is True
    assert client.post(f"/player/{a}/heartbeat").json()["ok"] and world_state._players[a]["dnd"] is True   # 心跳不算接管
    client.post("/action", json={"entityId": a, "action": {"type": "move", "payload": {"direction": "right"}}})
    assert world_state._players[a]["dnd"] is False
    r = client.delete(f"/player/{a}/leave").json()
    assert r["parked"] is True and a in world_state._players and world_state._players[a]["dnd"] is True
    assert world_state.get_zone_at(r["position"]["x"], r["position"]["y"])["arena"] == "achan_room"
    anon = _human(client, name="路人", agent_id=None)
    assert client.delete(f"/player/{anon}/leave").json() == {"ok": True} and anon not in world_state._players


def test_restore_backfills_dnd_auto_and_legacy_id(client, v12):
    """v1.3.5：v1.3.2 检查点里的人类阿蝉没有 dnd_auto（主镇 8000 的 阿蝉_83f3f5）→ 回填后离线归位 / leave 保护 / 接管都生效；旧 agent_id 归新。"""
    old_achan = {"id": "阿蝉_old", "name": "阿蝉", "controller": "human", "agent_id": "achan", "position": {"x": 4, "y": 30}, "facing": "right",
                 "state": "idle", "fullness": 70.0, "energy": 90.0, "tags": [], "buffs": [], "dnd": True}
    old_xq = {"id": "xq_old", "name": "小千", "controller": "agent", "agent_id": "npc_xiaoqian", "position": {"x": 15, "y": 21}, "facing": "down",
              "state": "idle", "tags": [], "buffs": []}
    for p in (old_achan, old_xq):
        world_state._ensure_player_fields(p)
    assert old_achan["dnd_auto"] is True and old_achan["dnd"] is True
    assert old_xq["agent_id"] == "claudine" and old_xq["dnd_auto"] is False and old_xq["dnd"] is False


def test_anonymous_human_leaves_no_ledger_row_and_orphans_pruned(client, v12):
    """v1.3.6：匿名人类离开不留账户行；旧检查点里的孤儿 id 账户在回填时剪掉；有身份的账户照留。"""
    from game import economy
    anon = _human(client, name="路人", agent_id=None)
    client.delete(f"/player/{anon}/leave")
    assert anon not in client.get("/admin/metrics").json()["accounts"]
    economy._balances["阿蝉_22cbbe"] = 300; economy._balances["claudine"] = 2500
    gone = economy.prune_orphan_accounts(set())
    assert gone == ["阿蝉_22cbbe"] and economy._balances["claudine"] == 2500      # 配置里有名的账号不剪


def test_orphan_account_pruned_on_checkpoint_load(client, v12):
    """v1.3.11：孤儿 id 账户要在 economy 状态回填之后剪（v1.3.6 剪早了，主镇重启后「阿蝉_22cbbe: 300」仍在）。"""
    from game import economy, persistence
    _agent(client, "whale")
    economy._balances["阿蝉_zz9999"] = 300
    persistence.save_checkpoint()
    assert "阿蝉_zz9999" in economy._balances
    persistence.load_checkpoint()
    assert "阿蝉_zz9999" not in economy._balances and economy._balances.get("whale") is not None


def test_restart_closes_active_chat_rooms_and_clears_chat_active(client, v12, fake_clock):
    """v1.3.12：检查点里仍 active 的房间在回填时关掉（reason restart），两人 chat_active 摘掉、state 回 idle；pending 邀请过期。"""
    from game import chat_state, persistence
    _at(fake_clock, 15, 0)
    a = _agent(client, "npc_fisher"); b = _agent(client, "npc_rest_owner"); c = _agent(client, "claudine")
    place(a, 28, 14, "right"); place(b, 29, 14, "left"); place(c, 28, 13, "down")
    rid = client.post("/chat/request", json={"from_entity_id": a, "to_entity_ids": [b], "greeting": "嗨"}).json()["request_id"]
    client.post("/chat/respond", json={"request_id": rid, "entity_id": b, "accept": True, "message": "好"})
    for _ in range(3):
        chat_state.tick(time.time() + 100)                                             # 相邻 → 建房
    room_id = next(r["chat_room_id"] for r in chat_state._chat_rooms.values() if r["status"] == "active")
    assert all(any(x["key"] == "chat_active" for x in world_state._players[p]["buffs"]) for p in (a, b))
    rid2 = client.post("/chat/request", json={"from_entity_id": c, "to_entity_ids": [a], "greeting": "在吗"}).json()["request_id"]
    persistence.save_checkpoint()
    persistence.load_checkpoint()
    assert chat_state._chat_rooms[room_id]["status"] == "closed"
    assert not any(x["key"] == "chat_active" for p in (a, b) for x in world_state._players[p]["buffs"])
    assert world_state._players[a]["state"] == "idle" and world_state._players[a]["canMove"] is True
    assert chat_state._chat_requests[rid2]["status"] == "expired"


def test_player_views_carry_chat_room_id(client, v12, fake_clock):
    """v1.3.13：GET /player、/world.players[]、/state 带 chat_room_id（在房给 id，否则 null）。"""
    from game import chat_state
    _at(fake_clock, 15, 0)
    a = _agent(client, "npc_fisher"); b = _agent(client, "npc_rest_owner")
    place(a, 28, 14, "right"); place(b, 29, 14, "left")
    assert client.get(f"/player/{a}").json()["chat_room_id"] is None
    rid = client.post("/chat/request", json={"from_entity_id": a, "to_entity_ids": [b], "greeting": "嗨"}).json()["request_id"]
    client.post("/chat/respond", json={"request_id": rid, "entity_id": b, "accept": True, "message": "好"})
    for _ in range(3):
        chat_state.tick(time.time() + 100)
    room = client.get(f"/chat/request/{rid}").json()["chat_room_id"]
    assert room and client.get(f"/player/{a}").json()["chat_room_id"] == room and client.get(f"/player/{a}/state").json()["chat_room_id"] == room
    snap = {x["id"]: x for x in client.get("/world", params={"fields": "players"}).json()["players"]}
    assert snap[a]["chat_room_id"] == room and snap[b]["chat_room_id"] == room
    client.post("/chat/exit", json={"entity_id": a, "chat_room_id": room})
    assert client.get(f"/player/{a}").json()["chat_room_id"] is None and client.get(f"/player/{b}").json()["chat_room_id"] == room


def test_live_window_gate_v1317(client, v12, fake_clock, monkeypatch):
    """v1.3.17：直播只在 live_window（缺省 18:30–22:30）内成立；窗外 use pc = 做稿（不切 scene、无 streaming、不打 /self/live）；purpose 覆盖；result.live。"""
    import httpx
    from game import self_sync, external_effects
    monkeypatch.delenv("SANDBOX_LIVE_WINDOW", raising=False)
    calls = []

    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(200, json={"ok": True, "vars": {}, "closeness": {}, "emotion_tags": [], "ocean": {}, "scene": "sandbox", "last_tick_ts": "x", "items": []})
    self_sync.configure(url="http://self.test", enabled=True, snap=False, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(external_effects, "SYNC_STOP", True)
    whale = _agent(client, "whale")
    _at(fake_clock, 14, 0); place(whale, 5, 12, "up")
    r = action(client, whale, "use"); p = world_state._players[whale]
    assert r["success"] and r["result"]["live"] is False and r["result"]["live_gate"] == "outside_window"
    assert p["scene"] == "sandbox" and "streaming" not in p["tags"] and "working" in p["tags"] and "/self/live/start" not in calls
    action(client, whale, "leave"); assert "/self/live/stop" not in calls
    r = action(client, whale, "use", {"purpose": "live"})                       # 窗外强制开播
    assert r["result"]["live"] is True and r["result"]["live_gate"] == "purpose_live" and p["scene"] == "live" and "streaming" in p["tags"] and "/self/live/start" in calls
    action(client, whale, "leave"); assert "/self/live/stop" in calls and p["scene"] == "sandbox"
    _at(fake_clock, 18, 30); r = action(client, whale, "use"); assert r["success"], r; assert r["result"]["live"] is True; action(client, whale, "leave")   # 边界 18:30 含（时钟只往前走，避免冷却）
    _at(fake_clock, 19, 0); calls.clear()
    r = action(client, whale, "use")                                            # 窗内缺省开播
    assert r["result"]["live"] is True and r["result"]["live_gate"] == "in_window" and p["scene"] == "live"
    action(client, whale, "leave")
    _at(fake_clock, 20, 0)
    r = action(client, whale, "use", {"purpose": "work"})                       # 窗内强制做稿
    assert r["result"]["live"] is False and p["scene"] == "sandbox" and "streaming" not in p["tags"]
    action(client, whale, "leave")
    _at(fake_clock, 22, 31); r = action(client, whale, "use"); assert r["success"] and r["result"]["live"] is False; action(client, whale, "leave")
    monkeypatch.setenv("SANDBOX_LIVE_WINDOW", "23:00-23:30")
    _at(fake_clock, 23, 10); r = action(client, whale, "use"); assert r["success"] and r["result"]["live"] is True and external_effects.live_window()["source"] == "env"


def test_v1318_economy_fixes(client, v12, fake_clock, monkeypatch):
    """v1.3.18：① 合成直播收入按时长（不足 5 分钟不记；窗外做稿不记）；② 店主自家消费免费；④ 冰箱 empty；⑤ 卖家 today_sales + ws sale。"""
    import httpx
    from game import self_sync, external_effects, economy, inventory
    monkeypatch.delenv("SANDBOX_LIVE_WINDOW", raising=False)
    self_sync.configure(url="http://self.test", enabled=True, snap=False,
                        transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"ok": True, "vars": {}, "closeness": {}, "emotion_tags": [], "ocean": {}, "scene": "sandbox", "last_tick_ts": "x", "items": []})))
    monkeypatch.setattr(external_effects, "SYNC_STOP", True)
    whale = _agent(client, "whale"); owner = _agent(client, "npc_rest_owner"); grocer = _agent(client, "npc_grocer")
    # ① 窗外做稿 2 小时：无 stream 收入
    _at(fake_clock, 13, 0); place(whale, 5, 12, "up"); g0 = world_state._players[whale]["gold"]
    assert action(client, whale, "use")["result"]["live"] is False
    fake_clock.advance(2 * 3600); _tick(fake_clock, 1); action(client, whale, "leave")
    assert world_state._players[whale]["gold"] == g0
    # 窗内直播 3 分钟：不足 5 分钟不记；2 小时：按时长记
    _at(fake_clock, 19, 0); assert action(client, whale, "use")["result"]["live"] is True
    fake_clock.advance(180); _tick(fake_clock, 1); action(client, whale, "leave"); assert world_state._players[whale]["gold"] == g0
    _at(fake_clock, 19, 10); assert action(client, whale, "use")["result"]["live"] is True
    fake_clock.advance(2 * 3600); _tick(fake_clock, 1); action(client, whale, "leave")
    gain = world_state._players[whale]["gold"] - g0
    assert 2 * 600 * 0.005 <= gain <= 2 * 1500 * 0.005 + 2 * 8 + 1, gain                 # 1200–3000 人次 × 0.005 + 0–16 礼物
    # ② 餐厅老板在自家桌点餐免费；顾客点餐进账 + today_sales
    _at(fake_clock, 12, 0); fake_clock.t += 86400
    place(owner, 34, 12, "up"); assert action(client, owner, "use")["success"]
    og = world_state._players[owner]["gold"]
    r = action(client, owner, "eat", {"item": "meal"}); assert r["success"] and r["result"]["price"] == 0 and world_state._players[owner]["gold"] == og
    action(client, owner, "leave")
    place(whale, 34, 15, "up"); assert action(client, whale, "use")["success"]
    r = action(client, whale, "eat", {"item": "meal"}); assert r["success"] and r["result"]["price"] == 20
    assert world_state._players[owner]["gold"] == og + 20
    ts = client.get(f"/player/{owner}").json()["today_sales"]
    assert ts["count"] == 1 and ts["gold"] == 20 and ts["last"][0]["item"] == "meal" and ts["last"][0]["buyer"] == whale and ts["last"][0]["buyer_name"] == "whale"
    assert client.get(f"/player/{whale}").json()["today_sales"] == {"count": 0, "gold": 0, "last": []}
    # 杂货店老板自家柜台拿货免费（库存照扣）
    place(grocer, 27, 22, "right"); gg = world_state._players[grocer]["gold"]
    r = action(client, grocer, "buy", {"item": "bread", "qty": 1}); assert r["success"] and world_state._players[grocer]["gold"] == gg and inventory.count(world_state._players[grocer], "bread") == 1
    # ④ 冰箱 empty
    objs = {o["id"]: o for o in client.get("/world", params={"fields": "objects"}).json()["objects"]}
    assert objs["fridge_home"]["empty"] is False and objs["counter"].get("empty") is None
    client.post("/admin/scenario", json={"steps": []})


def test_thought_bubble_v1319(client, v12, monkeypatch):
    """v1.3.19：POST /player/{id}/thought → last_thought；只在 /world?view=admin 带出；GET /player 缺省不带；ws 事件缺省不带正文；超长截断；actions 日志 type thought。"""
    import json as _json
    monkeypatch.delenv("SANDBOX_THOUGHT_VISIBLE_TO", raising=False)
    whale = _agent(client, "whale")
    r = client.post(f"/player/{whale}/thought", json={"text": "该去餐厅了吧，有点饿", "kind": "plan"}).json()
    assert r["ok"] and r["last_thought"] == {"text": "该去餐厅了吧，有点饿", "kind": "plan", "game_time": r["last_thought"]["game_time"]} and r["last_thought"]["game_time"]
    assert client.post(f"/player/{whale}/thought", json={"text": "   "}).status_code == 400
    assert client.post("/player/nobody/thought", json={"text": "x"}).status_code == 404
    long = "想" * 80
    assert len(client.post(f"/player/{whale}/thought", json={"text": long}).json()["last_thought"]["text"]) == 60
    pub = {p["id"]: p for p in client.get("/world", params={"fields": "players"}).json()["players"]}
    assert pub[whale]["last_thought"] is None                                                    # 旁观 / 直播布局看不到
    adm = {p["id"]: p for p in client.get("/world", params={"fields": "players", "view": "admin"}).json()["players"]}
    assert adm[whale]["last_thought"]["kind"] == "think" and adm[whale]["last_thought"]["text"].endswith("…")
    assert "last_thought" not in client.get(f"/player/{whale}").json()
    monkeypatch.setenv("SANDBOX_THOUGHT_VISIBLE_TO", "all")
    assert client.get(f"/player/{whale}").json()["last_thought"]["kind"] == "think"
    assert {p["id"]: p for p in client.get("/world", params={"fields": "players"}).json()["players"]}[whale]["last_thought"] is not None
    from game.action_log import read_log
    rows = read_log(entity=whale)
    th = [x for x in rows if x["type"] == "thought" and x["entityId"] == whale]
    assert len(th) == 2 and th[0]["payload"]["kind"] == "plan" and th[0]["payload"]["text"] == "该去餐厅了吧，有点饿"



def test_thought_ws_event_carries_text(client, v12):
    import json as _json, time as _time
    from fastapi.testclient import TestClient
    from main import app
    with TestClient(app) as live:
        whale = live.post("/player/join", json={"name": "whale", "controller": "agent", "profile": {"agent_id": "whale"}}).json()["playerId"]
        with live.websocket_connect("/ws/world") as ws:
            _json.loads(ws.receive_text())                                          # 首帧快照
            live.post(f"/player/{whale}/thought", json={"text": "去钓鱼", "kind": "wait", "ts": "2026-11-16T10:00:00+08:00"})
            got = None; t0 = _time.time()
            while _time.time() - t0 < 3 and got is None:
                m = _json.loads(ws.receive_text())
                if m.get("type") == "thought":
                    got = m
            assert {k: got[k] for k in ("type", "entity", "text", "kind", "game_time")} == {"type": "thought", "entity": whale, "text": "去钓鱼", "kind": "wait", "game_time": "2026-11-16T10:00:00+08:00"}


def test_seed_from_self_never_inherits_live_scene(client, v12, monkeypatch):
    """v1.3.20：自我层还记着上一场 live 时，新 spawn / join 的玩家 scene 仍 sandbox（直播只能由 use 直播物品进入），并补发一条 live.stop 对齐（C：bench S07b 第一帧 scene=live）。"""
    import httpx
    from game import self_sync, external_effects
    calls = []

    def handler(req):
        calls.append(req.url.path)
        if req.url.path == "/self/state":
            return httpx.Response(200, json={"vars": {"fullness": 70, "energy": 70, "social": 70, "fun": 70, "mood": 65}, "closeness": {}, "emotion_tags": [], "ocean": {}, "scene": "live", "last_tick_ts": "x"})
        return httpx.Response(200, json={"ok": True})
    self_sync.configure(url="http://self.test", enabled=True, snap=False, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(external_effects, "SYNC_STOP", True)
    whale = _agent(client, "whale")
    p = world_state._players[whale]
    assert p["scene"] == "sandbox" and "streaming" not in p["tags"] and p.get("usingObjectId") is None
    assert "/self/live/stop" in calls                                                  # 补发下播对齐自我层
