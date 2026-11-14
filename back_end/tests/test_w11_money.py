"""world-v1.1 ③：账户独立于在线（日薪 / 销售入离线账户、上线接着用）、克劳蒂娜时薪从店主扣与欠薪、房租（到期扣两笔 / 欠租 / 心情 / 镇公所 QQ / 补齐 / due_soon）、委托过期。"""
from datetime import datetime

import pytest

from game import world_state, ticker, economy, rent, qq, commissions
from game.time_state import GAME_TZ
from tests.conftest import action, place
from tests.test_w9_map_v2 import v12  # noqa: F401


def _agent(client, aid, name=None):
    return client.post("/player/join", json={"name": name or aid, "controller": "agent", "profile": {"agent_id": aid}}).json()["playerId"]


def _at(fake_clock, y, mo, d, h, m=0):
    fake_clock.t = datetime(y, mo, d, h, m, tzinfo=GAME_TZ).timestamp()


def _tick(fake_clock, s=1.0):
    ticker.tick_once(checkpoint=False); fake_clock.advance(s); ticker.tick_once(checkpoint=False)


def test_offline_accounts_wages_and_sales(client, v12, fake_clock):
    _at(fake_clock, 2026, 11, 10, 10, 0)
    whale = _agent(client, "whale"); grocer = _agent(client, "npc_grocer"); fisher = _agent(client, "npc_fisher")
    assert economy.balance("npc_grocer") == 3000 and economy.accounts_view()["npc_fisher"] == 3000
    # 老板娘下线（被清理）→ 账户还在；鲸仔买面包的钱照进她账户；22:00 日薪照发
    world_state.remove_player(grocer)
    assert grocer not in world_state._players and economy.balance("npc_grocer") == 3000
    place(whale, 27, 22, "right")
    r = action(client, whale, "buy", {"item": "bread", "qty": 2})
    assert r["success"] and economy.balance("npc_grocer") == 3010
    rows = [x for x in economy_rows() if x["account"] == "npc_grocer"]
    assert rows[-1]["kind"] == "income" and rows[-1]["offline"] is True and rows[-1]["entity"] is None and rows[-1]["source"] == "shop_sale"
    _at(fake_clock, 2026, 11, 10, 22, 1); _tick(fake_clock, 1)
    assert economy.balance("npc_grocer") == 3030 and world_state._players[fisher]["gold"] == 3020          # 渔夫 17:00 日薪在线发
    # 她回来：接着用 3030
    g2 = _agent(client, "npc_grocer")
    assert world_state._players[g2]["gold"] == 3030 and client.get("/admin/metrics").json()["accounts"]["npc_grocer"] == 3030
    # 没来过的厨师：不发日薪、不算账户
    assert "npc_rest_owner" not in economy._opened and economy.accounts_view()["npc_rest_owner"] == 3000
    assert all(x["account"] != "npc_rest_owner" for x in economy_rows())


def test_claudine_wage_debt_when_grocer_broke(client, v12, fake_clock):
    _at(fake_clock, 2026, 11, 10, 12, 0)                           # 周二
    xq = _agent(client, "claudine"); grocer = _agent(client, "npc_grocer")
    world_state._players[grocer]["gold"] = 5; economy.on_leave(world_state._players[grocer])
    _at(fake_clock, 2026, 11, 10, 14, 1); _tick(fake_clock, 1)
    assert world_state._players[xq]["gold"] == 3012 and world_state._players[grocer]["gold"] == 5          # 克劳蒂娜照拿，店主不扣
    debt = [x for x in economy_rows() if x["kind"] == "wage_debt"]
    assert len(debt) == 1 and debt[0]["account"] == "npc_grocer" and debt[0]["owed"] == 12 and debt[0]["owed_total"] == 12 and economy._debts["npc_grocer"] == 12


def economy_rows():
    import json
    from datetime import date
    from game.paths import data_dir
    fp = data_dir() / "economy" / f"{date.today().isoformat()}.jsonl"
    return [json.loads(l) for l in fp.read_text(encoding="utf-8").splitlines()] if fp.exists() else []


def test_rent_cycle_due_overdue_qq_clear_and_notice(client, v12, fake_clock):
    _at(fake_clock, 2026, 11, 10, 10, 0)
    whale = _agent(client, "whale"); owner = _agent(client, "npc_rest_owner")
    p = world_state._players[whale]
    v = client.get(f"/player/{whale}").json()["rent"]
    assert v["amount"] == 300 and v["items"] == [{"kind": "home", "amount": 300}] and v["landlord"] == "town_hall" and v["overdue"] is False
    assert v["due_at"] == "2026-12-01T08:00:00+08:00" and v["due_in_days"] == 20
    assert client.get(f"/player/{whale}").json()["rent"] == next(x for x in client.get("/world", params={"fields": "players"}).json()["players"] if x["id"] == whale)["rent"]
    _tick(fake_clock, 1)
    assert p["gold"] == 3000                                                                   # 11-01 在开户前：本月不收
    # 11-28 08:01 起 due_in_days ≤ 3（感知给事实）
    _at(fake_clock, 2026, 11, 28, 8, 1); _tick(fake_clock, 1)
    assert client.get(f"/player/{whale}").json()["rent"]["due_in_days"] <= 3
    # 12-01 07:59 没扣；08:01 扣：鲸仔 300，厨师两笔 400 + 1000（厨师已下线 → 离线账户）
    world_state.remove_player(owner)
    _at(fake_clock, 2026, 12, 1, 7, 59); _tick(fake_clock, 1)
    assert p["gold"] == 3000
    _at(fake_clock, 2026, 12, 1, 8, 1); _tick(fake_clock, 1)
    assert p["gold"] == 2700 and economy.balance("npc_rest_owner") == 3000 - 1400
    rent_rows = [x for x in economy_rows() if x["kind"] == "rent"]
    assert [(x["account"], x["delta"], x["rent_kind"]) for x in rent_rows] == [("whale", -300, "home"), ("npc_rest_owner", -400, "home"), ("npc_rest_owner", -1000, "shop")]
    assert client.get(f"/player/{whale}").json()["pendingMessage"] == "交了这个月的房租 300 金币。"
    _tick(fake_clock, 1)
    assert p["gold"] == 2700                                                                   # 同月不重扣
    # 1 月：钱不够 → 欠租，不赶人；次日 08:00 心情 −3 + 镇公所 QQ；余额够了自动补齐
    p["gold"] = 100; economy.on_leave(p); economy.on_join(p)
    _at(fake_clock, 2027, 1, 1, 8, 1); _tick(fake_clock, 1)
    v = client.get(f"/player/{whale}").json()
    assert p["gold"] == 100 and v["rent"]["overdue"] is True and v["rent"]["owed"] == 300 and "欠着了" in v["pendingMessage"]
    first = [m for m in client.get("/qq/inbox", params={"player": whale}).json()["messages"] if m["from"] == "town_hall"]
    assert len(first) == 1 and "没交上" in first[0]["text"]                                   # 欠租当刻立即催一条（S12 阶段二 30 分钟内可见）
    mood0 = p["mood"]
    _at(fake_clock, 2027, 1, 2, 8, 1); _tick(fake_clock, 1)
    assert p["mood"] == pytest.approx(mood0 - 3, abs=0.5)
    inbox = client.get("/qq/inbox", params={"player": whale}).json()["messages"]
    assert inbox[-1]["from"] == "town_hall" and inbox[-1]["from_name"] == "镇公所" and "欠着房租 300" in inbox[-1]["text"]
    _at(fake_clock, 2027, 1, 2, 8, 5); _tick(fake_clock, 1)
    assert len([m for m in client.get("/qq/inbox", params={"player": whale}).json()["messages"] if m["from"] == "town_hall"]) == 2   # 之后一天一条
    client.post("/admin/income", json={"entity_id": whale, "amount": 500, "source": "song_fee"})
    _tick(fake_clock, 1)
    assert p["gold"] == 300 and client.get(f"/player/{whale}").json()["rent"]["overdue"] is False
    assert [x for x in economy_rows() if x.get("label") == "rent_cleared"][0]["delta"] == -300
    # rent.enabled=false：整段关闭，人类 rent 为 null
    economy.cfg()["rent"]["enabled"] = False
    try:
        assert client.get(f"/player/{whale}").json()["rent"] is None
    finally:
        economy.cfg()["rent"]["enabled"] = True
    h = client.post("/player/join", json={"name": "h"}).json()["playerId"]
    assert client.get(f"/player/{h}").json()["rent"] is None


def test_commission_expires_after_3_days(client, v12, fake_clock):
    _at(fake_clock, 2026, 11, 10, 10, 0)
    _agent(client, "whale")
    cm = client.post("/admin/commission", json={"client": "餐厅老板", "title": "店歌", "fee": 150}).json()["commission"]
    assert cm["expires_at"] == "2026-11-13T10:00:00+08:00" and 100 <= cm["fee"] <= 200
    _at(fake_clock, 2026, 11, 13, 9, 59); _tick(fake_clock, 1)
    assert client.get("/commissions").json()["count"] == 1
    _at(fake_clock, 2026, 11, 13, 10, 1); _tick(fake_clock, 1)
    assert client.get("/commissions").json()["count"] == 0
    allc = client.get("/commissions", params={"status": "all"}).json()["commissions"]
    assert allc[0]["status"] == "expired" and allc[0]["expired_at"]
    assert economy.cfg()["commissions"]["max_open"] == 2 and economy.cfg()["commissions"]["expire_days"] == 3
