"""
B17：GET /ws/world —— 只读 WebSocket 推送（给前端会话 E 的 E9 / 气泡）。

连接时发全量：
    {"type": "snapshot", "ts": <游戏时刻 ISO>, ...GET /world 的全部字段...}
之后 ≤ 10 Hz 推增量（字段与 GET /world 同名，只带变化的部分）：
    {"type": "patch", "ts": ...,
     "worldState": {<变化的字段>},                       # 可选
     "players": {"upsert": [<players[] 元素>], "remove": [id]},   # 可选
     "objects": [{"id", "currentUsers", "userList"}],     # 可选
     "chat": [{"chat_room_id", "participants", "kind": "message" | "event", "seq", "from_entity_id", "from_name",
               "content" | "type", "timestamp"}]}          # 可选：新的聊天消息 / 事件
空闲 5 s 发 {"type": "heartbeat", "ts": ...}。
客户端发来的任何消息都被忽略（不接受写）。
"""

import asyncio
import copy
import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from game import world_state, chat_state
from game.time_state import game_now_iso, get_time_state
from models.world import WorldData

log = logging.getLogger("sandbox.ws")
router = APIRouter()

PUSH_INTERVAL = 0.1        # 10 Hz
HEARTBEAT_S = 5.0
PLAYER_KEYS = ("id", "name", "position", "facing", "state", "controller", "online", "agent_id")


def _dynamic_state() -> dict:
    with world_state.STATE_LOCK:
        ws_ = get_time_state(); ws_["weather"] = world_state._WEATHER
        players = {p["id"]: p for p in world_state.get_all_players_snapshot()}
        objects = {o["id"]: {"id": o["id"], "currentUsers": o["currentUsers"], "userList": list(o["userList"])}
                   for o in world_state._OBJECTS}
    return {"worldState": ws_, "players": players, "objects": objects}


class Hub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._last: dict | None = None
        self._chat_seq: dict[str, int] = {}
        self._task: asyncio.Task | None = None
        self._last_send = 0.0
        self.sent_patches = 0
        self._actions: list[dict] = []          # E⑦：待推的动作事件（线程安全：list.append 原子）
        self._actions_max = 500

    def push_action(self, entity: str, action: str, success: bool, obj: str | None = None,
                    reason: str | None = None, extra: dict | None = None) -> None:
        """由 POST /action 分派后调用；与下一次 patch 一起推 {type:"action", ...}。没有订阅者时丢弃。"""
        if not self._clients:
            return
        ev = {"type": "action", "ts": game_now_iso(), "entity": entity, "action": action,
              "object": obj, "success": bool(success), "reason": reason}
        if extra:
            ev.update(extra)
        self._actions.append(ev)
        if len(self._actions) > self._actions_max:
            del self._actions[: len(self._actions) - self._actions_max]

    def client_count(self) -> int:
        return len(self._clients)

    # ── 连接管理 ──
    async def attach(self, ws: WebSocket) -> None:
        self._clients.add(ws)
        with world_state.STATE_LOCK:
            world = WorldData(**world_state.get_world()).model_dump()     # 与 GET /world 的响应模型逐字段一致
        if self._last is None:
            self._last = _dynamic_state()
            self._init_chat_seq()
        await ws.send_text(json.dumps({"type": "snapshot", "ts": game_now_iso(), **world}, ensure_ascii=False))

    def detach(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    def _init_chat_seq(self) -> None:
        for rid, room in chat_state._chat_rooms.items():
            self._chat_seq[rid] = max([m["seq"] for m in room["messages"]] + [e["seq"] for e in room["events"]] + [0])

    # ── 增量 ──
    def _chat_delta(self) -> list[dict]:
        out = []
        with world_state.STATE_LOCK:
            players = world_state._players
            for rid, room in chat_state._chat_rooms.items():
                last = self._chat_seq.get(rid, 0)
                items = []
                for m in room["messages"]:
                    if m["seq"] > last:
                        items.append({"kind": "message", "seq": m["seq"], "from_entity_id": m["from_entity_id"],
                                      "from_name": players.get(m["from_entity_id"], {}).get("name", m["from_entity_id"]),
                                      "content": m["content"], "timestamp": m["timestamp"]})
                for e in room["events"]:
                    if e["seq"] > last:
                        items.append({"kind": "event", "seq": e["seq"], "type": e["type"],
                                      "from_entity_id": e.get("entity_id"), "timestamp": e["timestamp"]})
                if items:
                    items.sort(key=lambda x: x["seq"])
                    self._chat_seq[rid] = items[-1]["seq"]
                    for it in items:
                        out.append({"chat_room_id": rid, "participants": list(room["participants"]), **it})
        return out

    def build_patch(self) -> dict | None:
        cur = _dynamic_state()
        prev = self._last or {"worldState": {}, "players": {}, "objects": {}}
        patch: dict = {}
        ws_diff = {k: v for k, v in cur["worldState"].items() if prev["worldState"].get(k) != v}
        if ws_diff:
            patch["worldState"] = ws_diff
        upsert = [p for pid, p in cur["players"].items() if prev["players"].get(pid) != p]
        remove = [pid for pid in prev["players"] if pid not in cur["players"]]
        if upsert or remove:
            patch["players"] = {"upsert": upsert, "remove": remove}
        objs = [o for oid, o in cur["objects"].items() if prev["objects"].get(oid) != o]
        if objs:
            patch["objects"] = objs
        chat = self._chat_delta()
        if chat:
            patch["chat"] = chat
        self._last = cur
        if not patch:
            return None
        return {"type": "patch", "ts": game_now_iso(), **patch}

    async def _broadcast(self, msg: dict) -> None:
        data = json.dumps(msg, ensure_ascii=False)
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.detach(ws)
        self._last_send = time.time()

    async def _loop(self) -> None:
        while True:
            try:
                if self._clients:
                    pending_actions, self._actions = self._actions, []
                    for ev in pending_actions:
                        await self._broadcast(ev)
                    patch = self.build_patch()
                    if patch:
                        await self._broadcast(patch)
                        self.sent_patches += 1
                    elif not pending_actions and time.time() - self._last_send >= HEARTBEAT_S:
                        await self._broadcast({"type": "heartbeat", "ts": game_now_iso()})
                else:
                    self._last = None            # 没人订阅时不积累 diff；下次连接重建基线
            except Exception:
                log.exception("ws push failed")
            await asyncio.sleep(PUSH_INTERVAL)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self._loop(), name="ws-hub")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        for ws in list(self._clients):
            try:
                await ws.close()
            except Exception:
                pass
        self._clients.clear()
        self._last = None
        self._actions.clear()


hub = Hub()


@router.websocket("/ws/world")
async def ws_world(ws: WebSocket):
    await ws.accept()
    await hub.attach(ws)
    try:
        while True:
            await ws.receive_text()           # 只读：客户端发来的任何内容都忽略
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        hub.detach(ws)
