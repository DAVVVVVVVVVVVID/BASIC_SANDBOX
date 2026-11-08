"""Q6「靠近即可说」：say → 2 格内同 sector 玩家下一次 perceive 的 nearby_speech；不开房间；聊天 JSONL kind=say；ws say。"""
import json
from datetime import date

from game import chat_state
from game.paths import data_dir
from tests.conftest import join, action, place


def test_say_reaches_nearby_only_once_and_logs(client):
    a = join(client, "阿蝉"); b = join(client, "鲸仔"); far = join(client, "远人")
    place(a, 10, 10, "right"); place(b, 12, 10, "left"); place(far, 14, 10, "left")                   # b 距 2、far 距 4
    r = action(client, a, "say", {"text": "晚饭吃什么？"})
    assert r["success"] and r["result"]["heard_by"] == [b] and r["result"]["heard_count"] == 1 and r["result"]["range"] == 2
    per = client.get("/agent/perceive", params={"entity_id": b}).json()
    assert per["nearby_speech"] == [{"from": a, "from_name": "阿蝉", "text": "晚饭吃什么？", "ts": per["nearby_speech"][0]["ts"]}]
    assert client.get("/agent/perceive", params={"entity_id": b}).json()["nearby_speech"] == []        # 读过即清
    assert client.get("/agent/perceive", params={"entity_id": far}).json()["nearby_speech"] == []
    assert client.get("/agent/perceive", params={"entity_id": a}).json()["nearby_speech"] == []        # 自己不听自己
    assert chat_state._chat_rooms == {} and chat_state._chat_requests == {}                             # 不开房、不走邀请
    # 多句排队、顺序保留
    action(client, a, "say", {"text": "一"}); action(client, a, "say", {"text": "二"})
    assert [m["text"] for m in client.get("/agent/perceive", params={"entity_id": b}).json()["nearby_speech"]] == ["一", "二"]
    # 参数
    assert action(client, a, "say", {"text": "  "})["reason"] == "empty_text"
    assert action(client, a, "say", {"text": "x" * 201})["reason"] == "text_too_long"
    # 聊天 JSONL kind=say
    rows = [json.loads(l) for l in (data_dir() / "chat" / f"{date.today().isoformat()}.jsonl").read_text(encoding="utf-8").splitlines()]
    says = [x for x in rows if x["kind"] == "say"]
    assert len(says) == 3 and says[0]["from"] == a and says[0]["to"] == [b] and says[0]["text"] == "晚饭吃什么？" and says[0]["room_id"] is None
    # 动作日志有 say 行
    acts = [x for x in client.get("/history/log").json() if x["entityId"] == a and x["type"] == "say"]
    assert len(acts) == 5 and acts[0]["success"] and acts[0]["payload"]["text"] == "晚饭吃什么？"


def test_say_does_not_cross_sector_walls(client):
    a = join(client, "a"); b = join(client, "b")
    place(a, 10, 9, "down"); place(b, 10, 11, "up")                                                     # 距 2 但隔墙 / 不同 sector 时听不到
    from game import world_state
    sa = world_state.get_zone_at(10, 9)["sector"]; sb = world_state.get_zone_at(10, 11)["sector"]
    r = action(client, a, "say", {"text": "喂"})
    assert (r["result"]["heard_by"] == [b]) == (sa == sb)
