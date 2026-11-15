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
    assert set(accs) == {"achan", "claudine", "npc_rest_owner", "npc_grocer"} and all(x["id"] == x["account"] for x in c["contacts"])
    assert accs["achan"]["online"] is True and accs["achan"]["player_id"] == achan and accs["claudine"]["online"] is False
    assert c["groups"] == [{"id": "g_live", "name": "鲸仔直播组", "members": ["whale", "achan"], "member_names": ["鲸仔", "阿蝉"], "unread": 0}]


def test_group_message_per_member_read_state(client):
    whale = _agent(client, "whale"); achan = _agent(client, "achan"); xq = _agent(client, "claudine")
    assert client.post("/qq/send", json={"entity_id": xq, "group": "g_live", "text": "x"}).json()["reason"] == "not_member"
    r = client.post("/qq/send", json={"entity_id": whale, "group": "g_live", "text": "今晚八点开播"}).json()
    assert r["success"] and r["message"]["group"] == "g_live" and r["message"]["to"] is None
    assert client.get("/agent/perceive", params={"entity_id": achan}).json()["phone"]["unread"] == {"鲸仔直播组": 1}
    assert client.get("/agent/perceive", params={"entity_id": whale}).json()["phone"]["unread_total"] == 0   # 自己发的不算未读
    rd = client.post("/qq/read", json={"entity_id": achan, "peer": "g_live"}).json()
    assert rd["count"] == 1 and rd["messages"][0]["text"] == "今晚八点开播"
    assert client.get("/qq/contacts", params={"player": achan}).json()["groups"][0]["unread"] == 0


def test_file_only_transferable_items(client):
    """world-v1.1 Q-5：QQ 只发文字，任何 kind=file 都回 files_not_supported（歌 / 稿子是实体 cd / script，当面 give）。"""
    whale = _agent(client, "whale"); achan = _agent(client, "achan")
    for item in ("fish", "gift", "song", "cd"):
        bad = client.post("/qq/send", json={"entity_id": whale, "to": "achan", "kind": "file", "file_ref": {"item": item, "meta": {"title": "夜航"}}}).json()
        assert bad["success"] is False and bad["reason"] == "files_not_supported", item
    assert client.get(f"/player/{achan}").json().get("inventory") == []
    ok = client.post("/qq/send", json={"entity_id": whale, "to": "achan", "text": "新歌写好了，见面给你 CD"}).json()
    assert ok["success"] and ok["message"]["kind"] == "text"


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
            assert "text" not in got[0] and got[0]["chars"] == 6 and got[0]["from"] == "achan" and got[0]["participants"] == ["achan", "whale"] and got[1]["count"] == 1   # v1.3.16：ws 不带正文


def test_inbox_returns_latest_and_all_unread_v1314(client):
    """v1.3.14：历史 > limit 时返回最新 N 条（升序）并保证我的全部未读都在；不再把最新截掉。"""
    whale = _agent(client, "whale"); achan = _agent(client, "achan")
    for i in range(120):
        assert client.post("/qq/send", json={"entity_id": achan, "to": "whale", "text": f"m{i:03d}"}).json()["success"]
    r = client.get("/qq/inbox", params={"player": whale}).json()
    texts = [m["text"] for m in r["messages"]]
    assert len(texts) == 120 and texts[0] == "m000" and texts[-1] == "m119"            # 全部未读 → 全给
    assert r["total"] == 120 and r["truncated"] is False
    client.post("/qq/read", json={"entity_id": whale, "peer": "achan"})
    for i in range(5):
        client.post("/qq/send", json={"entity_id": achan, "to": "whale", "text": f"new{i}"})
    r = client.get("/qq/inbox", params={"player": whale, "limit": 10}).json()
    texts = [m["text"] for m in r["messages"]]
    assert texts[-5:] == ["new0", "new1", "new2", "new3", "new4"] and len(texts) == 10 and texts == sorted(texts, key=lambda t: (t.startswith("new"), t))   # 最新 10 条、升序
    assert r["truncated"] is True and r["total"] == 125


def test_admin_qq_purge_and_export_filter(client, tmp_path, monkeypatch):
    """v1.3.14：/admin/qq/purge 缺省预览；真清后内存消失、进检查点、export 过滤、本机 jsonl 保留。"""
    from game import qq, persistence
    whale = _agent(client, "whale"); achan = _agent(client, "achan")
    for i in range(3):
        client.post("/qq/send", json={"entity_id": achan, "group": "g_live", "text": f"有人问你喜欢什么颜色 {i}"})
    client.post("/qq/send", json={"entity_id": achan, "to": "whale", "text": "正常私聊"})
    pre = client.post("/admin/qq/purge", json={"sender": "achan", "group": "g_live"}).json()
    assert pre["dry_run"] is True and pre["matched"] == 3 and pre["removed"] == 0 and len(qq._messages) == 4
    assert client.post("/admin/qq/purge", json={}).status_code == 400
    r = client.post("/admin/qq/purge", json={"sender": "achan", "group": "g_live", "dry_run": False, "actor": "controller", "reason": "测试污染"}).json()
    assert r["removed"] == 3 and len(qq._messages) == 1 and qq._messages[0]["text"] == "正常私聊"
    assert client.get("/qq/inbox", params={"player": whale, "peer": "g_live"}).json()["messages"] == []
    persistence.save_checkpoint(); qq._reset_for_tests(); persistence.load_checkpoint()
    assert len(qq._messages) == 1 and len(qq._purged_ids) == 3
    from datetime import date
    ex = client.get("/admin/export", params={"date": date.today().isoformat(), "kinds": "qq"}).json()
    assert all("有人问" not in (row.get("text") or "") for row in ex["qq"]) and ex["manifest"]["purged"]["qq"] >= 3
    assert any(row.get("entity") == achan for row in ex["qq"] if row.get("kind") == "message")        # 日志行带发送者 player id


def test_human_read_qq_takes_no_time_v1315(client):
    """v1.3.15（主播定）：人类读 QQ 不占时间——busy_game_seconds 0、不加 reading buff / tag、能立刻动；agent 仍 60 s。"""
    whale = _agent(client, "whale")
    human = client.post("/player/join", json={"name": "阿蝉", "controller": "human", "profile": {"agent_id": "achan"}}).json()["playerId"]
    client.post("/qq/send", json={"entity_id": whale, "to": "achan", "text": "在吗"})
    r = client.post("/qq/read", json={"entity_id": human, "peer": "whale"}).json()
    p = world_state._players[human]
    assert r["success"] and r["count"] == 1 and r["busy_game_seconds"] == 0
    assert not any(b["key"] == "reading" for b in p["buffs"]) and "reading" not in p["tags"] and p["canMove"] is True
    client.post("/qq/send", json={"entity_id": human, "to": "whale", "text": "在"})
    r = client.post("/qq/read", json={"entity_id": whale, "peer": "achan"}).json()
    assert r["busy_game_seconds"] == 60 and any(b["key"] == "reading" for b in world_state._players[whale]["buffs"])


def test_admin_delete_single_buff_key(client):
    """v1.3.15：DELETE /admin/player/{id}/buffs?key=reading 只摘一类（decay 不摘），路径与 spec 对齐。"""
    whale = _agent(client, "whale"); achan = _agent(client, "achan")
    client.post("/qq/send", json={"entity_id": achan, "to": "whale", "text": "x"})
    client.post("/qq/read", json={"entity_id": whale, "peer": "achan"})
    p = world_state._players[whale]
    assert any(b["key"] == "reading" for b in p["buffs"]) and p["canMove"] is False
    r = client.delete(f"/admin/player/{whale}/buffs", params={"key": "reading"}).json()
    assert r == {"ok": True, "cleared": 1, "key": "reading", "source": None}
    assert not any(b["key"] == "reading" for b in p["buffs"]) and "reading" not in p["tags"] and p["canMove"] is True and any(b["key"] == "decay" for b in p["buffs"])
    assert client.delete("/admin/player/nobody/buffs", params={"key": "reading"}).status_code == 404
