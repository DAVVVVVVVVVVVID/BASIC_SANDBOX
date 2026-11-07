"""
QQ 接口（W10 ③）。见 game/qq.py 模块说明与 docs/api-spec.md「QQ」节。
  POST /qq/send      {entity_id, to? | group?, kind: text|file, text?, file_ref?{item, name?, ref?, meta?}}
  GET  /qq/inbox     ?player=&since=&peer=&limit=&unread_only=
  POST /qq/read      {entity_id, peer?}        占用 1 游戏分钟（reading）
  GET  /qq/contacts  ?player=
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from game import qq

router = APIRouter(prefix="/qq", tags=["qq"])


class SendBody(BaseModel):
    entity_id: Optional[str] = None
    from_: Optional[str] = Field(default=None, alias="from")     # E 的写法：from = 发送者 player id
    to: Optional[str] = None
    group: Optional[str] = None
    kind: Optional[str] = None                                   # 缺省：有 file_ref / item 则 file，否则 text
    text: Optional[str] = None
    file_ref: Optional[dict] = None
    item: Optional[str] = None                                   # E 的写法：file_ref 的 item 平铺
    model_config = {"populate_by_name": True}

    def sender(self) -> str:
        return self.entity_id or self.from_ or ""


class ReadBody(BaseModel):
    entity_id: Optional[str] = None
    player: Optional[str] = None                                 # E 的写法
    peer: Optional[str] = None
    from_: Optional[str] = Field(default=None, alias="from")     # E 的写法：from | group = peer
    group: Optional[str] = None
    model_config = {"populate_by_name": True}


@router.post("/send")
def qq_send(body: SendBody):
    file_ref = body.file_ref
    if body.item and not file_ref:
        file_ref = {"item": body.item}
    kind = body.kind or ("file" if file_ref else "text")
    msg, reason = qq.send(body.sender(), to=body.to, group=body.group, kind=kind, text=body.text, file_ref=file_ref)
    if reason == "entity_not_found":
        raise HTTPException(status_code=404, detail=f"entity not found: {body.sender()}")
    if reason:
        return {"success": False, "reason": reason, "message": None}
    return {"success": True, "reason": None, "message": msg}


@router.get("/inbox")
def qq_inbox(player: str, since: Optional[str] = None, peer: Optional[str] = None,
             limit: int = Query(100, ge=1, le=500), unread_only: bool = False):
    r = qq.inbox(player, since=since, peer=peer, limit=limit, unread_only=unread_only)
    if r is None:
        raise HTTPException(status_code=404, detail=f"entity not found: {player}")
    return r


@router.post("/read")
def qq_read(body: ReadBody):
    ent = body.entity_id or body.player or ""
    r, reason = qq.read(ent, peer=body.peer or body.from_ or body.group)
    if reason == "entity_not_found":
        raise HTTPException(status_code=404, detail=f"entity not found: {ent}")
    if reason:
        return {"success": False, "reason": reason}
    return {"success": True, "reason": None, **r}


@router.get("/contacts")
def qq_contacts(player: str):
    r = qq.contacts(player)
    if r is None:
        raise HTTPException(status_code=404, detail=f"entity not found: {player}")
    return r
