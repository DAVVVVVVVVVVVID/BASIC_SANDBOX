from typing import Optional
from fastapi import APIRouter, Query
from game.action_log import get_log, read_log

router = APIRouter()


@router.get("/history")
def history():
    """最近 N 条（内存），形状不变，字段只增（game_time / controller）。"""
    return get_log()


@router.get("/history/log")
def history_log(
    since: Optional[str] = Query(default=None, description="ISO 时间，只返回不早于此刻的记录"),
    entity: Optional[str] = Query(default=None, description="只返回该 entityId 的记录"),
    limit: Optional[int] = Query(default=None, ge=0, description="最多返回最新 N 条"),
):
    """从 append-only JSONL 文件读取完整行动日志（B1），供评测与自我层拉取。"""
    return read_log(since=since, entity=entity, limit=limit)
