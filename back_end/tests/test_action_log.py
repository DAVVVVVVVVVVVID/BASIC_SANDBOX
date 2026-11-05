"""B1：append-only JSONL 行动日志。"""
import json
from datetime import date

from game import action_log
from game.paths import data_dir
from tests.conftest import join, action


def _lines():
    files = sorted((data_dir() / "actions").glob("*.jsonl"))
    out = []
    for f in files:
        out += [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    return out


def test_jsonl_line_count_equals_action_count(client):
    pid = join(client)
    n = 25   # 超过内存上限 20
    for i in range(n):
        action(client, pid, "turn", {"direction": "up"})
    lines = _lines()
    assert len(lines) == n
    f = data_dir() / "actions" / f"{date.today().isoformat()}.jsonl"
    assert f.exists()
    # 内存只留最近 20 条，GET /history 形状不变（旧字段齐全，新增 game_time / controller）
    hist = client.get("/history").json()
    assert len(hist) == action_log._MAX_LOG_SIZE
    for key in ("timestamp", "entityId", "type", "payload", "success", "reason", "label"):
        assert key in hist[-1]
    assert hist[-1]["game_time"] is not None
    assert hist[-1]["controller"] == "human"
    assert hist[-1] == lines[-1]


def test_skip_log_not_written(client):
    pid = join(client)
    action(client, pid, "turn", {"direction": "left"}, skipLog=True)
    assert _lines() == []
    assert client.get("/history").json() == []


def test_failed_action_is_logged_with_reason(client):
    pid = join(client)
    res = action(client, pid, "interact")
    assert not res["success"]
    line = _lines()[-1]
    assert line["success"] is False and line["reason"] == "no_object_in_front"


def test_read_log_filters(client):
    import time
    a = join(client, "a"); b = join(client, "b")
    action(client, a, "turn", {"direction": "up"})
    time.sleep(0.002)     # 保证 timestamp（毫秒）严格递增
    action(client, b, "turn", {"direction": "down"})
    time.sleep(0.002)
    action(client, a, "turn", {"direction": "left"})
    assert len(action_log.read_log()) == 3
    assert [r["payload"]["direction"] for r in action_log.read_log(entity=a)] == ["up", "left"]
    assert len(action_log.read_log(limit=1)) == 1
    since = action_log.read_log()[1]["timestamp"]
    assert len(action_log.read_log(since=since)) == 2
    assert action_log.read_log(since="2999-01-01T00:00:00") == []


def test_history_log_endpoint(client):
    pid = join(client)
    action(client, pid, "turn", {"direction": "up"})
    r = client.get("/history/log", params={"entity": pid})
    assert r.status_code == 200 and len(r.json()) == 1
    assert client.get("/history/log", params={"entity": "nobody"}).json() == []


def test_truncated_tail_line_is_skipped(client):
    pid = join(client)
    action(client, pid, "turn", {"direction": "up"})
    f = next((data_dir() / "actions").glob("*.jsonl"))
    with open(f, "a", encoding="utf-8") as fh:
        fh.write('{"timestamp": "2026-11-05T00:00:00.000", "entityId": "x"')   # kill -9 截断
    assert len(action_log.read_log()) == 1
