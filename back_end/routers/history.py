from typing import Optional
from fastapi import APIRouter, Query
from game.action_log import get_log, read_log
from game import chat_log

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


@router.get("/history/chat")
def history_chat(
    since: Optional[str] = Query(default=None, description="ISO 时间，只返回不早于此刻的记录"),
    room: Optional[str] = Query(default=None, description="只返回该 room_id"),
    kind: Optional[str] = Query(default=None, description="message | event"),
    limit: Optional[int] = Query(default=None, ge=0),
):
    """聊天 append-only JSONL 回放（W5 任务 1，数据集优先）。只读。"""
    return chat_log.read_log(since=since, room=room, kind=kind, limit=limit)
