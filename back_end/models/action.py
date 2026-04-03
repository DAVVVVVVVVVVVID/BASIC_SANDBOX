from pydantic import BaseModel
from typing import Any, Optional


class Action(BaseModel):
    type: str
    payload: dict[str, Any] = {}


class ActionRequest(BaseModel):
    entityId: str
    action: Action
    skipLog: bool = False           # True 时不写日志（用于 BFS 中间步）
    logLabel: Optional[str] = None  # 自定义日志显示文字，None 时不写 label


class ActionResponse(BaseModel):
    success: bool
    type: str
    result: Optional[dict[str, Any]] = None
    reason: Optional[str] = None
