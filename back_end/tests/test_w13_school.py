"""上课系统 v1（world-v1.4.0）：一节完整课（分段推送 / 打瞌睡 / 提问作答 / 考勤 / 下课笔记 / 借笔记）、作业提交箱、评分回写。"""
import json
from datetime import datetime

import pytest

from game import world_state, ticker, school, inventory
from game.time_state import GAME_TZ
from tests.conftest import action, place
from tests.test_w9_map_v2 import _agent, v12  # noqa: F401


def _set(fake_clock, y, mo, d, h, m=0):
    fake_clock.t = datetime(y, mo, d, h, m, tzinfo=GAME_TZ).timestamp()


def _tick(fake_clock, s=60.0):
    fake_clock.advance(s); ticker.tick_once(checkpoint=False)


def _run_until(fake_clock, h, m, step=60.0):
    target = datetime.fromtimestamp(fake_clock.t, GAME_TZ).replace(hour=h, minute=m, second=0).timestamp()
    while fake_clock.t < target:
        _tick(fake_clock, min(step, target - fake_clock.t))


LESSON = {
    "schema": 1, "date": "2026-11-23", "town": "main", "generated_at": "2026-11-22T23:30:00+08:00", "syllabus_ref": {"week": 1, "genre": "游戏 BGM"},
    "lessons": [{
        "lesson_id": "2026-11-23-0900-genre", "start": "09:00", "course": "genre", "title": "游戏 BGM：战斗音乐",
        "segments": [{"i": i, "text": f"第{i}段讲授"} for i in range(1, 10)],
        "questions": [{"qid": "q1", "phase": "mid", "after_segment": 5, "text": "战斗音乐常用什么速度？", "answer": "快板 140 BPM 上下", "explanation": "紧张感"},
                      {"qid": "q2", "phase": "end", "after_segment": 9, "text": "Boss 战和普通战斗差在哪？", "answer": "层次与动机变奏", "explanation": "…"}],
        "homework_note": "本周作业：三首游戏 BGM，周五 10:45 前交。"}]}


@pytest.fixture
def school_env(tmp_path, monkeypatch):
    d = tmp_path / "school"; d.mkdir()
    monkeypatch.setenv("SANDBOX_SCHOOL_DIR", str(d))
    (d / "2026-11-23.json").write_text(json.dumps(LESSON, ensure_ascii=False), encoding="utf-8")
    return d


def _rows(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.exists() else []


def test_full_lesson_flow(client, v12, fake_clock, school_env, monkeypatch):
    monkeypatch.setattr(school, "_doze_roll", lambda lid, aid, i: aid == "whale" and i in (3, 5))   # 第 3 / 5 段睡着（第 5 段后有课中题）
    _set(fake_clock, 2026, 11, 23, 8, 55)
    whale = _agent(client, "whale"); cl = _agent(client, "claudine")
    place(whale, 4, 3, "up"); assert action(client, whale, "use")["success"]           # 课前入座
    tt = client.get("/school/timetable").json()
    assert tt["week"] == 1 and tt["week_genre"] == "游戏 BGM" and tt["courses"]["genre"]["name"] == "类型创作" and tt["timetable"]["mon"][0] == ["09:00", "genre"]
    _run_until(fake_clock, 9, 1)
    p = client.get(f"/player/{whale}").json()
    assert "【类型创作】第1段讲授" in (p["pendingMessage"] or "")
    assert p["lesson"]["lesson_id"] == "2026-11-23-0900-genre" and p["lesson"]["segment"] == {"i": 1, "text": "第1段讲授"} and p["lesson"]["attendance"] == "present"
    assert "in_class" in world_state._players[whale]["tags"]
    assert client.get("/agent/perceive", params={"entity_id": whale}).json()["lesson"]["title"] == "游戏 BGM：战斗音乐"
    # 小克 09:15 才到 → 迟到
    _run_until(fake_clock, 9, 15)
    place(cl, 6, 3, "up"); assert action(client, cl, "use")["success"]
    _run_until(fake_clock, 9, 21)                                                         # 第 3 段（09:20）睡着
    snap = {x["id"]: x for x in client.get("/world", params={"fields": "players"}).json()["players"]}
    assert snap[whale]["lesson"]["dozing"] is True and snap[cl]["lesson"]["dozing"] is False
    client.get(f"/player/{whale}")                                                         # 清 pendingMessage
    _run_until(fake_clock, 9, 31)                                                         # 第 4 段（09:30）醒来前缀
    p = client.get(f"/player/{whale}").json()
    assert p["pendingMessage"].startswith("（刚才走神睡着了）【类型创作】第4段讲授") and p["lesson"]["dozed_prev"] is True
    _run_until(fake_clock, 9, 41)                                                         # 第 5 段睡着，但课中题照推并叫醒
    p = client.get(f"/player/{whale}").json()
    assert "第5段讲授" not in (p["pendingMessage"] or "") and "（刚才走神睡着了）【提问】战斗音乐常用什么速度？" in p["pendingMessage"]
    assert p["lesson"]["question"]["qid"] == "q1" and p["lesson"]["dozing"] is False
    r = action(client, whale, "answer", {"qid": "q1", "text": "大概 140"})                 # 坐着上课也能答
    assert r["success"] and r["result"]["correct_answer"] == "快板 140 BPM 上下" and r["result"]["explanation"] == "紧张感"
    assert action(client, whale, "answer", {"qid": "q1", "text": "再答"})["reason"] == "already_answered"
    assert action(client, whale, "answer", {"qid": "nope", "text": "x"})["reason"] == "unknown_question"
    _run_until(fake_clock, 9, 51)
    assert action(client, cl, "answer", {"qid": "q1", "text": "迟了"})["reason"] == "question_closed"
    today = client.get("/school/today", params={"player": "whale"}).json()
    les = today["lessons"][0]
    assert les["status"] == "ongoing" and les["attendance"] == {"whale": "present", "claudine": "late"} and today["week"] == 1 and today["week_genre"] == "游戏 BGM"
    _run_until(fake_clock, 10, 21)                                                        # 第 9 段 + 课末题 + 作业提醒
    p = client.get(f"/player/{whale}").json()
    assert "第9段讲授" in p["pendingMessage"] and "【作业提醒】本周作业" in p["pendingMessage"] and "【提问】Boss 战" in p["pendingMessage"]
    _run_until(fake_clock, 10, 31)                                                        # 下课
    pw = world_state._players[whale]
    assert pw.get("usingObjectId") is None and "in_class" not in pw["tags"]
    notes = [e for e in inventory.ensure(pw) if e["type"] == "class_notes"]
    assert len(notes) == 1
    segs = notes[0]["meta"]["segments"]
    assert [s["status"] for s in segs] == ["heard", "heard", "slept", "heard", "slept", "heard", "heard", "heard", "heard"] and segs[2]["text"] is None
    ncl = next(e for e in inventory.ensure(world_state._players[cl]) if e["type"] == "class_notes")
    assert [s["status"] for s in ncl["meta"]["segments"]][:2] == ["absent", "absent"]
    assert client.get(f"/player/{whale}").json()["lesson"] is None
    # 课末题下课后 10 分钟内仍可答（出勤者）
    assert action(client, whale, "answer", {"qid": "q2", "text": "层次"})["success"]
    # 读笔记、借笔记（meta 随行）
    r = action(client, whale, "read_item", {"item": "class_notes", "match": {"lesson_id": "2026-11-23-0900-genre"}})
    assert r["success"] and "3. ……（这段睡着了）" in r["result"]["message"] and "1. 第1段讲授" in r["result"]["message"]
    place(whale, 3, 19, "up"); place(cl, 4, 19, "left")
    r = action(client, cl, "give", {"target": whale, "item": "class_notes", "lesson_id": "2026-11-23-0900-genre"})
    assert r["success"]
    got = [e for e in inventory.ensure(pw) if e["type"] == "class_notes"]
    assert len(got) == 2 and {e["meta"]["owner"] for e in got} == {"whale", "claudine"}
    assert not [e for e in inventory.ensure(world_state._players[cl]) if e["type"] == "class_notes"]
    # 数据落盘
    att = _rows(school_env / "attendance.jsonl")
    assert {(r["agent_id"], r["status"]) for r in att} == {("whale", "present"), ("claudine", "late")}
    ans = _rows(school_env / "answers.jsonl")
    assert [(r["qid"], r["agent_id"], r["late"]) for r in ans] == [("q1", "whale", False), ("q2", "whale", True)]
    today = client.get("/school/today", params={"player": whale}).json()
    assert today["lessons"][0]["status"] == "done" and today["lessons"][0]["my_attendance"] == "present"


def test_missing_lesson_plan_still_runs(client, v12, fake_clock, school_env):
    """课案里没有 10:45 歌词课 → 照常开课、占位讲授、考勤照记，不报错。"""
    _set(fake_clock, 2026, 11, 23, 10, 40)
    whale = _agent(client, "whale")
    place(whale, 4, 3, "up"); assert action(client, whale, "use")["success"]
    _run_until(fake_clock, 10, 46)
    p = client.get(f"/player/{whale}").json()
    assert p["lesson"]["course"] == "lyrics" and "老师今天讲得比较散" in p["pendingMessage"]
    _run_until(fake_clock, 12, 16)
    att = {r["agent_id"]: r["status"] for r in _rows(school_env / "attendance.jsonl")}
    assert att == {"whale": "present", "claudine": "absent"}


def test_elective_only_whale_and_no_class_on_weekend(client, v12, fake_clock, school_env):
    _set(fake_clock, 2026, 11, 24, 13, 58)                                               # 周二 14:00 写作选修：只鲸仔
    whale = _agent(client, "whale"); cl = _agent(client, "claudine")
    place(whale, 4, 3, "up"); action(client, whale, "use")
    place(cl, 6, 3, "up"); action(client, cl, "use")
    _run_until(fake_clock, 14, 2)
    assert client.get(f"/player/{whale}").json()["lesson"]["course"] == "writing"
    assert client.get(f"/player/{cl}").json()["lesson"] is None and "in_class" not in world_state._players[cl]["tags"]
    assert school.lessons_for_date("2026-11-28") == [] and school.lessons_for_date("2026-11-20") == []   # 周六 / 开学前


def _cd(p, rid, status="pending", **kw):
    meta = {"title": f"曲 {rid}", "request_id": rid, "status": status, "redo_count": 0, "genre": "游戏 BGM", "scene": "战斗", "mood": "紧张",
            "form": "A-B-A", "chords": "Am-F-C-G", "arrangement": "弦乐 + 鼓", **kw}
    inventory.add(p, "cd", 1, meta=meta, expires_at=None)


def test_homework_box_submit_update_and_rules(client, v12, fake_clock, school_env):
    _set(fake_clock, 2026, 11, 25, 15, 0)                                                # 第 1 周周三
    whale = _agent(client, "whale"); p = world_state._players[whale]
    box = next(o for o in client.get("/world", params={"fields": "objects"}).json()["objects"] if o["id"] == "homework_box")
    assert box["hint"] == "带着 CD 使用 = 交作业，截止周五 10:45（之后算迟交）"
    place(whale, 8, 3, "down")
    assert action(client, whale, "use")["reason"] == "no_item"
    _cd(p, "mr-1"); _cd(p, "mr-2", proxy=True); _cd(p, "mr-3", status="redo")
    r = action(client, whale, "use", {"request_id": "mr-1"})
    assert r["success"] and r["result"]["receipt_id"].startswith("hw-") and r["result"]["late"] is False and r["result"]["audio"] == "none" and r["result"]["updated"] is False
    r2 = action(client, whale, "use", {"request_id": "mr-2"})
    assert r2["result"]["audio"] == "pending"
    assert action(client, whale, "use", {"request_id": "mr-3"})["reason"] == "cd_redo"
    rec = [e for e in inventory.ensure(p) if e["type"] == "homework_receipt"]
    assert len(rec) == 2 and inventory.count(p, "cd") == 3                                # CD 不没收
    # 代做那首她验收 → edit_item final → 同周提交自动更新为 final
    assert action(client, whale, "edit_item", {"match": {"request_id": "mr-2"}, "set": {"status": "final", "satisfaction": 4}})["success"]
    hw = client.get("/school/today", params={"player": whale}).json()["homework"]
    assert hw["week"] == 1 and hw["count"] == 2 and {s["request_id"]: s["audio"] for s in hw["submitted"]} == {"mr-1": "none", "mr-2": "final"}
    assert next(e for e in inventory.ensure(p) if e["type"] == "homework_receipt" and e["meta"]["request_id"] == "mr-2")["meta"]["audio"] == "final"
    # 同 request_id 同周再交 = 更新，沿用 receipt_id
    r3 = action(client, whale, "use", {"request_id": "mr-1"})
    assert r3["success"] and r3["result"]["updated"] is True and r3["result"]["receipt_id"] == r["result"]["receipt_id"]
    subs = _rows(school_env / "submissions.jsonl")
    assert [s["action"] for s in subs] == ["submit", "submit", "update", "update"] and subs[0]["creation_sheet_complete"] is True
    # 周五 10:45 后首次提交 = 迟交；下周再交上周的 → already_submitted
    _set(fake_clock, 2026, 11, 27, 11, 0)
    _cd(p, "mr-4")
    assert action(client, whale, "use", {"request_id": "mr-4"})["result"]["late"] is True
    _set(fake_clock, 2026, 12, 2, 15, 0)
    assert action(client, whale, "use", {"request_id": "mr-1"})["reason"] == "already_submitted"


def test_grade_writeback(client, v12, fake_clock, school_env, monkeypatch):
    _set(fake_clock, 2026, 11, 24, 15, 40)
    whale = _agent(client, "whale"); p = world_state._players[whale]
    r = client.post("/school/grade", json={"agent_id": "whale", "grade": "b", "kind": "writing", "comment": "意象不错", "lesson_id": "2026-11-24-1400-writing", "qid": "w1"})
    assert r.status_code == 200 and r.json()["delivered"] is True
    assert client.get(f"/player/{whale}").json()["pendingMessage"] == "写作课成绩：B，评语：意象不错"
    m0 = p["mood"]
    client.post("/school/grade", json={"agent_id": "whale", "grade": "A", "kind": "homework", "receipt_id": "hw-x"})
    assert p["mood"] > m0
    assert client.post("/school/grade", json={"agent_id": "whale", "grade": "S"}).status_code == 400
    monkeypatch.setenv("SELF_TOKEN", "tok")
    assert client.post("/school/grade", json={"agent_id": "whale", "grade": "A"}).status_code == 401
    assert client.post("/school/grade", json={"agent_id": "whale", "grade": "A"}, headers={"Authorization": "Bearer tok"}).status_code == 200
    assert len(_rows(school_env / "grades.jsonl")) == 3


def test_doze_roll_reproducible():
    a = [school._doze_roll("2026-11-23-0900-genre", "whale", i) for i in range(1, 10)]
    assert a == [school._doze_roll("2026-11-23-0900-genre", "whale", i) for i in range(1, 10)]
    assert not any(school._doze_roll("2026-11-23-0900-genre", "claudine", i) for i in range(1, 200))   # 小克不打瞌睡
    hits = sum(school._doze_roll(f"L{k}", "whale", i) for k in range(200) for i in range(1, 10))
    assert 40 <= hits <= 140                                                              # 1800 次 × 5% ≈ 90


def test_checkpoint_midlesson_roundtrip(client, v12, fake_clock, school_env, monkeypatch):
    """课上到一半重启：进度 / 在座 / 已推段 / 作答都接着来，下课照发笔记。"""
    from game import persistence
    monkeypatch.setattr(school, "_doze_roll", lambda *a: False)
    _set(fake_clock, 2026, 11, 23, 8, 58)
    whale = _agent(client, "whale")
    place(whale, 4, 3, "up"); action(client, whale, "use")
    _run_until(fake_clock, 9, 41)
    assert action(client, whale, "answer", {"qid": "q1", "text": "快"})["success"]
    persistence.save_checkpoint()
    school._reset_for_tests()
    persistence.load_checkpoint()
    L = school._active["2026-11-23-0900-genre"]
    assert L["pushed"] == 5 and "whale" in L["seat"] and "2026-11-23-0900-genre|q1|whale" in school._answers
    assert action(client, whale, "answer", {"qid": "q1", "text": "再"})["reason"] == "already_answered"
    _run_until(fake_clock, 10, 31)
    assert len([e for e in inventory.ensure(world_state._players[whale]) if e["type"] == "class_notes"]) == 1


def test_term_start_env_override(monkeypatch):
    monkeypatch.setenv("SANDBOX_SCHOOL_TERM_START", "2026-11-16")
    school.reload_cfg()
    assert [l["course"] for l in school.lessons_for_date("2026-11-19")] == ["genre", "lyrics", "writing"]   # 周四
    monkeypatch.delenv("SANDBOX_SCHOOL_TERM_START")
    school.reload_cfg()
    assert school.lessons_for_date("2026-11-19") == []


def test_plan_reloaded_midlesson_only_unpushed(client, v12, fake_clock, school_env, monkeypatch):
    """A 课中重写课案（讲评课截止后重写第 2–9 段）：沙盒推段前按 mtime 重载，只换没推的段 / 题。"""
    import os, time
    monkeypatch.setattr(school, "_doze_roll", lambda *a: False)
    _set(fake_clock, 2026, 11, 23, 8, 58)
    whale = _agent(client, "whale")
    place(whale, 4, 3, "up"); action(client, whale, "use")
    _run_until(fake_clock, 9, 11)                                                         # 推了 1、2 段
    doc = json.loads((school_env / "2026-11-23.json").read_text(encoding="utf-8"))
    doc["lessons"][0]["segments"] = [{"i": i, "text": f"重写第{i}段"} for i in range(1, 10)]
    doc["lessons"][0]["questions"][0]["text"] = "重写后的课中题"
    f = school_env / "2026-11-23.json"
    f.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    os.utime(f, (time.time() + 5, time.time() + 5))
    _run_until(fake_clock, 10, 31)
    segs = next(e for e in inventory.ensure(world_state._players[whale]) if e["type"] == "class_notes")["meta"]["segments"]
    assert [s["text"] for s in segs] == ["第1段讲授", "第2段讲授"] + [f"重写第{i}段" for i in range(3, 10)]
