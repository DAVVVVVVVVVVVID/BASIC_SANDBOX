"""上课系统 v1（world-v1.4.0）路由：课表、今日、评分回写。方案 docs/class-system-sandbox.md。"""
import os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from game import school, world_state

router = APIRouter(prefix="/school")


@router.get("/timetable")
def get_timetable():
    """课表配置（game/school.json）+ 本周第几周 / 类型。"""
    return school.timetable_view()


@router.get("/today")
def get_today(player: Optional[str] = None):
    """今天各节课：时段、状态 upcoming / ongoing / done、我的考勤、同学考勤（互相可见）；带 player 时多本周作业状态。player 收 player id 或 agent_id。"""
    with world_state.STATE_LOCK:
        p = None
        if player:
            p = world_state._players.get(player) or next((x for x in world_state._players.values() if x.get("agent_id") == player), None)
            if p is None:
                raise HTTPException(status_code=404, detail=f"player not found: {player}")
        return school.today_view(p)


class GradeBody(BaseModel):
    agent_id: str
    grade: str                         # A | B | C
    kind: str = "writing"              # writing | homework
    comment: Optional[str] = None      # ≤ 200 字
    lesson_id: Optional[str] = None
    qid: Optional[str] = None
    receipt_id: Optional[str] = None


@router.post("/grade")
def post_grade(body: GradeBody, authorization: Optional[str] = Header(default=None)):
    """A 的评分器回写：推本人 pendingMessage「写作课成绩：B，评语…」/「作业成绩：…」、写 school/grades.jsonl、ws lesson grade；作业成绩按配置影响心情。
    沙盒设了 SELF_TOKEN 时要求 Authorization: Bearer <SELF_TOKEN>。"""
    toks = [t for t in (os.environ.get("SANDBOX_ADMIN_TOKEN"), os.environ.get("SELF_TOKEN")) if t]
    if toks and (authorization or "") not in {f"Bearer {t}" for t in toks}:
        raise HTTPException(status_code=401, detail="bad token")
    with world_state.STATE_LOCK:
        res, reason = school.grade(world_state._players, body.model_dump())
    if reason:
        raise HTTPException(status_code=400, detail=reason)
    return res
