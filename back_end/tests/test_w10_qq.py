"""W10 ③ QQ：send / inbox / read（1 游戏分钟 reading）/ contacts；perceive phone.unread；文件类限制；JSONL；ws；检查点。"""
import json
from datetime import date

from game import world_state, ticker, qq, persistence
from game.paths import data_dir
from tests.conftest import join, action, place


def _agent(client, aid, name=None):
    return client.post("/player/join", json={"name": name or aid, "controller": "agent", "profile": {"agent_id": aid}}).json()["playerId"]


def _tick(fake_clock, s=1.0):
    ticker.tick_once(checkpoint=False); fake_clock.advance(s); ticker.tick_once(checkpoint=False)


def test_send_inbox_read_contacts_roundtrip(client, fake_clock):
    whale = _agent(client, "whale", "鲸仔"); achan = _agent(client, "achan", "阿蝉")
    place(whale, 3, 5, "up"); place(achan, 40, 30, "up")                                   # 不在一处也能联系
    r = client.post("/qq/send", json={"entity_id": achan, "to": "whale", "kind": "text", "text": "今晚吃什么"}).json()
    assert r["success"] and r["message"]["from"] == "achan" and r["message"]["to"] == "whale" and r["message"]["read_at"] is None
    r2 = client.post("/qq/send", json={"entity_id": achan, "to": whale, "text": "回我"}).json()        # to 也可用 player id
    assert r2["success"] and r2["message"]["to"] == "whale"
    # 感知：只给条数，不给正文
    per = client.get("/agent/perceive", params={"entity_id": whale}).json()
    assert per["phone"]["unread"] == {"阿蝉": 2} and per["phone"]["unread_total"] == 2
    assert "今晚吃什么" not in json.dumps(per, ensure_ascii=False)
    # inbox
    ib = client.get("/qq/inbox", params={"player": whale}).json()
    assert ib["account"] == "whale" and [m["text"] for m in ib["messages"]] == ["今晚吃什么", "回我"]
    assert all(m["direction"] == "in" and m["read_at"] is None for m in ib["messages"]) and ib["unread_total"] == 2
    assert client.get("/qq/inbox", params={"player": whale, "unread_only": "true", "peer": "阿蝉"}).json()["unread_total"] == 2
    # 读：拿到正文、标已读、占 1 游戏分钟（reading：不能走不能用）
    rd = client.post("/qq/read", json={"entity_id": whale}).json()
    assert rd["success"] and rd["count"] == 2 and [m["text"] for m in rd["messages"]] == ["今晚吃什么", "回我"]
    assert rd["busy_game_seconds"] == 60 and rd["unread"] == {}
    p = world_state._players[whale]
    assert "reading" in p["tags"] and p["canMove"] is False and p["canUse"] is False
    assert action(client, whale, "move", {"direction": "down"})["success"] is False
    assert client.get("/qq/inbox", params={"player": whale}).json()["messages"][0]["read_at"] is not None
    assert client.get("/agent/perceive", params={"entity_id": whale}).json()["phone"]["unread_total"] == 0
    _tick(fake_clock, 30); assert "reading" in world_state._players[whale]["tags"]                      # 30 s 还在读
    _tick(fake_clock, 40)                                                                                # 过 1 游戏分钟
    p = world_state._players[whale]
    assert "reading" not in p["tags"] and p["canMove"] is True
    assert action(client, whale, "move", {"direction": "down"})["success"]
    # 发件人的 inbox 看到 direction=out，且对方已读
    out = client.get("/qq/inbox", params={"player": achan}).json()["messages"]
    assert all(m["direction"] == "out" and m["read_at"] for m in out)
    # contacts：初始通讯录 + 在线状态 + 群
    c = client.get("/qq/contacts", params={"player": whale}).json()
    accs = {x["account"]: x for x in c["contacts"]}
    assert set(accs) == {"achan", "npc_xiaoqian", "npc_rest_owner", "npc_grocer"} and all(x["id"] == x["account"] for x in c["contacts"])
    assert accs["achan"]["online"] is True and accs["achan"]["player_id"] == achan and accs["npc_xiaoqian"]["online"] is False
    assert c["groups"] == [{"id": "g_live", "name": "鲸仔直播组", "members": ["whale", "achan"], "member_names": ["鲸仔", "阿蝉"], "unread": 0}]


def test_group_message_per_member_read_state(client):
    whale = _agent(client, "whale"); achan = _agent(client, "achan"); xq = _agent(client, "npc_xiaoqian")
    assert client.post("/qq/send", json={"entity_id": xq, "group": "g_live", "text": "x"}).json()["reason"] == "not_member"
    r = client.post("/qq/send", json={"entity_id": whale, "group": "g_live", "text": "今晚八点开播"}).json()
    assert r["success"] and r["message"]["group"] == "g_live" and r["message"]["to"] is None
    assert client.get("/agent/perceive", params={"entity_id": achan}).json()["phone"]["unread"] == {"鲸仔直播组": 1}
    assert client.get("/agent/perceive", params={"entity_id": whale}).json()["phone"]["unread_total"] == 0   # 自己发的不算未读
    rd = client.post("/qq/read", json={"entity_id": achan, "peer": "g_live"}).json()
    assert rd["count"] == 1 and rd["messages"][0]["text"] == "今晚八点开播"
    assert client.get("/qq/contacts", params={"player": achan}).json()["groups"][0]["unread"] == 0


def test_file_only_transferable_items(client):
    whale = _agent(client, "whale"); achan = _agent(client, "achan")
    bad = client.post("/qq/send", json={"entity_id": whale, "to": "achan", "kind": "file", "file_ref": {"item": "fish"}}).json()
    assert bad["success"] is False and bad["reason"] == "not_transferable"                 # 实物不走 QQ
    bad2 = client.post("/qq/send", json={"entity_id": whale, "to": "achan", "kind": "file", "file_ref": {"item": "gift"}}).json()
    assert bad2["reason"] == "not_transferable"
    ok = client.post("/qq/send", json={"entity_id": whale, "to": "achan", "kind": "file", "text": "新歌 demo",
                                       "file_ref": {"item": "song", "name": "夜航", "meta": {"title": "夜航"}}}).json()
    assert ok["success"] and ok["message"]["kind"] == "file" and ok["message"]["file_ref"]["item"] == "song"
    assert ok["message"]["item_delivered_to"] == ["achan"]
    inv = client.get(f"/player/{achan}").json().get("inventory")
    assert inv == [{"type": "song", "name": "歌（文件）", "class": "file", "count": 1, "meta": {"title": "夜航"}}]
    assert world_state._players[whale]["inventory"] == []                                  # 文件是复制，发送者不扣（本来也没有）


def test_send_rules_and_busy(client):
    whale = _agent(client, "whale"); achan = _agent(client, "achan")
    assert client.post("/qq/send", json={"entity_id": whale, "to": "nobody_x", "text": "hi"}).json()["reason"] == "unknown_recipient"
    assert client.post("/qq/send", json={"entity_id": whale, "to": "whale", "text": "hi"}).json()["reason"] == "self_message"
    assert client.post("/qq/send", json={"entity_id": whale, "text": "hi"}).json()["reason"] == "need_to_or_group"
    assert client.post("/qq/send", json={"entity_id": whale, "to": "achan", "text": "  "}).json()["reason"] == "empty_text"
    assert client.post("/qq/send", json={"entity_id": "ghost", "to": "achan", "text": "hi"}).status_code == 404
    # 睡觉 / 直播中不看手机
    world_state._players[achan]["tags"].append("sleeping")
    assert client.post("/qq/read", json={"entity_id": achan}).json()["reason"] == "phone_unavailable"
    assert client.post("/qq/send", json={"entity_id": achan, "to": "whale", "text": "zzz"}).json()["reason"] == "phone_unavailable"
    world_state._players[achan]["tags"].remove("sleeping"); world_state._players[achan]["scene"] = "live"
    assert client.post("/qq/read", json={"entity_id": achan}).json()["reason"] == "phone_unavailable"


def test_human_player_contacts_and_offline_recipient(client):
    h = join(client, "主播"); whale = _agent(client, "whale")
    c = client.get("/qq/contacts", params={"player": h}).json()
    assert "whale" in {x["account"] for x in c["contacts"]} and "achan" in {x["account"] for x in c["contacts"]}
    # 给不在线的阿蝉发：存着，等他上线来读
    r = client.post("/qq/send", json={"entity_id": h, "to": "阿蝉", "text": "明天见"}).json()
    assert r["success"] and r["message"]["to"] == "achan"
    achan = _agent(client, "achan")
    assert client.get("/agent/perceive", params={"entity_id": achan}).json()["phone"]["unread"] == {"主播": 1}
    assert client.post("/qq/read", json={"entity_id": achan}).json()["messages"][0]["text"] == "明天见"


def test_jsonl_export_and_checkpoint(client, fake_clock):
    whale = _agent(client, "whale"); achan = _agent(client, "achan")
    client.post("/qq/send", json={"entity_id": achan, "to": "whale", "text": "一"})
    client.post("/qq/read", json={"entity_id": whale})
    today = date.today().isoformat()
    rows = [json.loads(l) for l in (data_dir() / "qq" / f"{today}.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["kind"] for r in rows] == ["message", "read"]
    assert rows[0]["text"] == "一" and rows[0]["from"] == "achan" and rows[0]["to"] == "whale" and rows[0]["town"] == "main"
    assert rows[1]["account"] == "whale" and rows[1]["count"] == 1 and rows[1]["ids"] == [rows[0]["id"]]
    d = client.get("/admin/export", params={"date": today, "kinds": "qq"}).json()
    assert d["manifest"]["counts"] == {"qq": 2} and d["qq"][0]["text"] == "一"
    # 检查点往返：消息、已读、群、seq
    persistence.save_checkpoint()
    qq._reset_for_tests(); world_state._reset_for_tests()
    persistence.load_checkpoint()
    ib = client.get("/qq/inbox", params={"player": whale}).json()
    assert len(ib["messages"]) == 1 and ib["messages"][0]["text"] == "一" and ib["messages"][0]["read_at"] is not None
    r = client.post("/qq/send", json={"entity_id": achan, "to": "whale", "text": "二"}).json()
    assert r["message"]["id"] > rows[0]["id"]                                              # seq 续号


def test_ws_pushes_qq_events(client):
    from fastapi.testclient import TestClient
    from main import app
    import time
    with TestClient(app) as live:
        whale = _agent(live, "whale"); achan = _agent(live, "achan")
        with live.websocket_connect("/ws/world") as ws:
            assert json.loads(ws.receive_text())["type"] == "snapshot"
            live.post("/qq/send", json={"entity_id": achan, "to": "whale", "text": "ws 来一条"})
            live.post("/qq/read", json={"entity_id": whale})
            got = []
            t0 = time.time()
            while time.time() - t0 < 3 and len(got) < 2:
                m = json.loads(ws.receive_text())
                if m["type"] == "qq":
                    got.append(m)
            assert [g["event"] for g in got] == ["message", "read"]
            assert got[0]["text"] == "ws 来一条" and got[0]["from"] == "achan" and got[1]["count"] == 1
