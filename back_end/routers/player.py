from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from game.world_state import (
    create_player, remove_player, get_player, touch_player, rejoin_player,
    get_player_buffs, clear_player_buffs, force_reset_player_state,
    apply_effects_to_player, get_recent_uses, get_recent_events, _players,
)

router = APIRouter()


class JoinRequest(BaseModel):
    name: str
    controller: str = "human"            # B6："human" | "agent"（与 AGENT_V2 join_player 同名）
    profile: Optional[dict] = None       # B6：{E, N, agent_id?}
    dnd: Optional[bool] = None           # world-v1.3：静态勿扰；缺省 = 人类且身份为 achan（或名叫阿蝉）时开


class DndRequest(BaseModel):
    on: bool


class RejoinRequest(BaseModel):
    playerId: str


class EffectsRequest(BaseModel):
    effects: list[dict]                  # 与 object_types.json 同格式
    scene: Optional[str] = None          # "sandbox" | "live"，非空时切换衰减场景
    source: str = "effects"
    event: Optional[str] = None          # §3.11 A2：事件名（如 viewer_praised），只记录供对账


@router.post("/player/join")
def join(body: JoinRequest):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="name cannot be empty")
    if body.controller not in ("human", "agent"):
        raise HTTPException(status_code=400, detail="controller must be 'human' or 'agent'")
    from game.world_state import view_tags, find_human_by_agent_id, rejoin_player as _rejoin
    if body.controller == "human":
        existing = find_human_by_agent_id((body.profile or {}).get("agent_id"))
        if existing is not None:                                          # v1.3.4 ③：同一身份的人类再 join = 接管已有玩家（主播的阿蝉常驻）
            player = _rejoin(existing["id"])
            player["tags"] = view_tags(player)
            return {"playerId": player["id"], "player": player, "takeover": True}
    player = create_player(body.name.strip(), controller=body.controller, profile=body.profile, dnd=body.dnd)
    player["tags"] = view_tags(player)                                   # world-v1.3：响应里的 tags 与 GET /player 一致（dnd / working）
    return {"playerId": player["id"], "player": player}


@router.post("/player/rejoin")
def rejoin(body: RejoinRequest):
    """B6：agent 进程重拉后用同一 playerId 续接（置 online=True、刷新心跳）。"""
    player = rejoin_player(body.playerId)
    if player is None:
        raise HTTPException(status_code=404, detail=f"player not found: {body.playerId}")
    return {"playerId": player["id"], "player": player}


@router.delete("/player/{player_id}/leave")
def leave(player_id: str):
    from game.world_state import park_dnd
    p = _players.get(player_id)
    if p is not None and p.get("dnd_auto"):                               # v1.3.4 ③：主播的阿蝉常驻——leave 只停（dnd + 回房待机），不删
        park_dnd(player_id, "leave")
        p["online"] = False
        return {"ok": True, "parked": True, "position": dict(p["position"])}
    remove_player(player_id)
    return {"ok": True}


@router.post("/player/{player_id}/heartbeat")
def heartbeat(player_id: str):
    """E②：显式心跳（任何 controller）。返回 online 与 last_tick_ts。agent 必须用它（或 rejoin）保持 online=true。"""
    if not touch_player(player_id):
        raise HTTPException(status_code=404, detail=f"player not found: {player_id}")
    p = _players[player_id]
    return {"ok": True, "online": p.get("online", True), "last_tick_ts": p.get("last_tick_ts")}


@router.get("/player/{player_id}")
def get_player_data(player_id: str):
    # E②：只对 controller=human 刷心跳（人类前端的老路径）；agent 的 GET 无在线副作用，心跳走 POST /player/{id}/heartbeat
    touch_player(player_id, human_only=True)
    player = get_player(player_id)
    if player is None:
        raise HTTPException(status_code=404, detail=f"player not found: {player_id}")
    return player


def _state_view(p: dict) -> dict:
    return {
        "id":           p["id"],
        "vars":         {k: p[k] for k in ("fullness", "energy", "social", "fun", "mood")},
        "mood_base":    p.get("mood_base"),
        "emotion_tags": p.get("emotion_tags", []),
        "closeness":    p.get("closeness", {}),
        "scene":        p.get("scene", "sandbox"),
        "controller":   p.get("controller", "human"),
        "online":       p.get("online", True),
        "dnd":          bool(p.get("dnd", False)),       # world-v1.3
        "agent_id":     p.get("agent_id"),
        "last_tick_ts": p.get("last_tick_ts"),
        "recent_uses":  get_recent_uses(p["id"]),
        "recent_events": get_recent_events(p["id"]),     # §3.11 A2：最近 /effects 推送的 event 记录
        "game":          p.get("game"),                   # B18
    }


@router.get("/player/{player_id}/state")
def get_player_state(player_id: str):
    """B13 ②：七变量原始数值 + last_tick_ts（给自我层同步与评测）。不刷新心跳、不清 pendingMessage。"""
    p = _players.get(player_id)
    if p is None:
        raise HTTPException(status_code=404, detail=f"player not found: {player_id}")
    return _state_view(p)


@router.post("/player/{player_id}/effects")
def post_player_effects(player_id: str, body: EffectsRequest):
    """B13 ③：推送与 object_types.json 同格式的 effect 列表（直播服务经自我层推「观众进入 +12 social」等）。"""
    if body.scene is not None and body.scene not in ("sandbox", "live"):
        raise HTTPException(status_code=400, detail="scene must be 'sandbox' or 'live'")
    res = apply_effects_to_player(player_id, body.effects, body.scene, source=body.source, event=body.event)
    if res is None:
        raise HTTPException(status_code=404, detail=f"player not found: {player_id}")
    return {"ok": True, **res["summary"], "event": body.event, "state": _state_view(res["player"])}


# ── 管理接口 ──────────────────────────────────────────────────────────────────

@router.post("/admin/player/{player_id}/dnd")
def set_player_dnd(player_id: str, body: DndRequest):
    """world-v1.3：静态勿扰开关（主播接管阿蝉时关，离开时开）。开 = 七变量不衰减、敲门即 busy、QQ 未读不扣发件人亲密度、
    tags 带 dnd（在自家房间再带 working）、心跳超时不删人（位置留在原地，不自动传送）。"""
    from game.world_state import set_dnd
    p = set_dnd(player_id, body.on)
    if p is None:
        raise HTTPException(status_code=404, detail=f"player not found: {player_id}")
    return {"ok": True, "playerId": player_id, "dnd": bool(p["dnd"]), "tags": __import__("game.world_state", fromlist=["x"]).view_tags(p)}


@router.get("/admin/player/{player_id}/buffs")
def admin_get_buffs(player_id: str):
    return {"buffs": get_player_buffs(player_id)}


@router.delete("/admin/player/{player_id}/buffs")
def admin_clear_buffs(player_id: str):
    count = clear_player_buffs(player_id)
    return {"ok": True, "cleared": count}


@router.post("/admin/player/force-reset")
def admin_force_reset(body: dict = {}):
    entity_id = body.get("entity_id")
    if not entity_id:
        raise HTTPException(status_code=400, detail="entity_id required")
    summary = force_reset_player_state(entity_id)
    return {"ok": True, **summary}


@router.post("/admin/checkpoint")
def admin_checkpoint():
    """立即写一份 SQLite 检查点（B2），返回摘要。"""
    from game.persistence import save_checkpoint
    return {"ok": True, **save_checkpoint()}


@router.get("/admin/metrics")
def admin_metrics():
    """运行指标：tick 耗时 / 间隔分位、玩家数、WebSocket 订阅数、进程 RSS（负载测试用）。"""
    import resource
    from game import ticker
    from game.world_state import _players
    try:
        from routers.ws import hub
        ws_clients = hub.client_count()
    except Exception:
        ws_clients = 0
    from game.world_state import SANDBOX_SEED, MAP_VERSION
    from game import chat_profile
    return {
        **ticker.metrics(),
        "seed": SANDBOX_SEED,
        "mapVersion": MAP_VERSION,
        "chat_profile": chat_profile.current(),            # X4：SANDBOX_CHAT_PROFILE 常量组回显
        "economy": __import__("game.economy", fromlist=["x"]).info(),   # X5：economy.json 路径与 sha256（按镇覆盖，manifest 记）
        "accounts": __import__("game.economy", fromlist=["x"]).accounts_view(),   # v1.1 §3：所有已知账号余额（含离线）
        "rent_enabled": bool((__import__("game.economy", fromlist=["x"]).cfg().get("rent") or {}).get("enabled", False)),
        "solo": __import__("game.world_state", fromlist=["x"]).SOLO,   # X7 A1「只有她」模式（SANDBOX_SOLO=1）
        "players": len(_players),
        "ws_clients": ws_clients,
        "rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1),
    }


# 沙盒数据集三类（+external）的规范字段集（docs/dataset-schema.md sandbox_* 行；api-spec §6 /admin/export）。
# 导出时缺字段按默认值回填并标 backfilled，保证每行字段齐全。字段只增不删。
EXPORT_FIELDS = {
    "actions":  ("timestamp", "entityId", "type", "payload", "success", "reason", "label", "objectId", "game_time", "controller",
                 "town", "map_version", "seed"),
    "chat":     ("kind", "ts", "game_time", "town", "map_version", "seed"),            # message 行另有 room_id/seq/from/from_name/to/text/controller；event 行另有 event/room_id/request_id/participants
    "state":    ("kind", "ts", "game_time", "town", "map_version", "seed", "player_id", "agent_id", "controller", "scene",
                 "mood_base", "vars", "emotion_tags", "closeness", "online", "position", "facing", "using", "tags", "gold"),
    "external": ("kind", "ts", "town", "map_version", "seed", "game_time", "entity"),
    "qq":       ("kind", "ts", "game_time", "town", "map_version", "seed"),            # message 行另有 id/from/from_name/to/group/msg_kind/text/file_ref/read_at；read 行另有 account/peer/ids/count
    "economy":  ("kind", "ts", "game_time", "town", "map_version", "seed", "account", "delta", "balance"),   # W10 ④ 金币流水
}
EXPORT_DEFAULTS = {"objectId": None, "label": None, "mood_base": None, "facing": None, "tags": [], "gold": None, "emotion_tags": [], "closeness": {},
                   "online": True, "using": None, "agent_id": None, "controller": "human", "scene": "sandbox", "entity": None,
                   "game_time": None, "reason": None, "kind": "sample"}


@router.get("/admin/export")
def admin_export(date: str, kinds: str = "actions,chat,state,external,qq,economy"):
    """
    W6 任务 1：一次性给出当日沙盒数据集（供 A 的 dataset_export.py 拉）。
    返回 {schema, date, town, map_version, seed, generated_at, actions[], chat[], state[], manifest{counts, files}}。
    actions / chat / state 分别来自 data/actions|chat|state/<date>.jsonl（只读，行序即文件序）。
    """
    import re
    from game import chat_log, state_log
    from game.action_log import read_log as read_actions, _actions_dir
    from game.world_state import TOWN, MAP_VERSION, SANDBOX_SEED
    from game.time_state import game_now_iso
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    want = {k.strip() for k in kinds.split(",") if k.strip()}
    out: dict = {"schema": "sandbox-0.1", "date": date, "town": TOWN, "map_version": MAP_VERSION, "seed": SANDBOX_SEED,
                 "generated_at": game_now_iso(), "manifest": {"counts": {}, "files": {}}}
    def _read_day(dirpath, parse):
        fp = dirpath / f"{date}.jsonl"
        rows = []
        if fp.exists():
            for raw in fp.read_text(encoding="utf-8").splitlines():
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rows.append(parse(raw))
                except Exception:
                    continue
        return rows, fp
    import json as _json
    from game.paths import data_dir
    sources = {"actions": _actions_dir(), "chat": data_dir() / "chat", "state": data_dir() / "state", "external": data_dir() / "external",
               "qq": data_dir() / "qq", "economy": data_dir() / "economy"}
    backfilled = 0
    for kind in ("actions", "chat", "state", "external", "qq", "economy"):
        if kind not in want:
            continue
        rows, fp = _read_day(sources[kind], _json.loads)
        for r in rows:                         # 旧版本写的行缺字段：按规范字段集回填（默认值）并标记（W6 / W9 第 0 项）
            missing = [k for k in EXPORT_FIELDS[kind] if k not in r]
            if missing:
                for k in missing:
                    r[k] = {"town": TOWN, "map_version": MAP_VERSION, "seed": SANDBOX_SEED}.get(k, EXPORT_DEFAULTS.get(k))
                r["backfilled"] = True; backfilled += 1
        out[kind] = rows
        out["manifest"]["counts"][kind] = len(rows)
        out["manifest"]["files"][kind] = {"path": str(fp), "exists": fp.exists(),
                                          "bytes": fp.stat().st_size if fp.exists() else 0}
    out["manifest"]["backfilled_rows"] = backfilled
    out["manifest"]["fields"] = {k: list(v) for k, v in EXPORT_FIELDS.items() if k in want}
    return out


class IncomeBody(BaseModel):
    entity_id: Optional[str] = None       # player id
    account: Optional[str] = None         # 或账号（agent_id；人类 = player id）
    amount: Optional[int] = None          # source=stream 时可省（按 viewers_avg / gifts 折算）
    source: str = "external"              # stream / song_fee / tip / adjust …
    label: Optional[str] = None
    meta: Optional[dict] = None
    viewers_avg: Optional[float] = None   # W11 ②：source=stream（旧名，同公式）
    gifts: Optional[float] = None
    viewers_total: Optional[float] = None # v1.1 M-2：当场累计观看人次（0.005 / 人）
    gifts_rmb: Optional[float] = None     # v1.1 M-2：礼物元 1:1


@router.post("/admin/income")
def admin_income(body: IncomeBody):
    """W10 ④：外部入账（写歌酬金 / 直播收入由自我层或直播侧调；日薪时薪由 tick 自己结）。amount 可负（扣款）。"""
    from game import economy
    from game.qq import account_of
    from game.world_state import STATE_LOCK, _players as _pl
    with STATE_LOCK:
        p = _pl.get(body.entity_id or "")
        if p is None and body.account:
            p = next((q for q in _pl.values() if account_of(q) == body.account), None)
        if p is None:
            raise HTTPException(status_code=404, detail="player not found")
        extra = {}
        amount = body.amount
        if body.source == "stream":                                   # W11 ② / v1.1 M-2：直播收入折算
            vt = body.viewers_total if body.viewers_total is not None else body.viewers_avg
            gf = body.gifts_rmb if body.gifts_rmb is not None else body.gifts
            if vt is not None or gf is not None:
                amount = economy.stream_income_amount(vt, gf)
            extra = {"viewers_total": vt, "gifts_rmb": gf, "viewers_avg": body.viewers_avg, "gifts": body.gifts, "synthetic": False}
        if amount is None:
            raise HTTPException(status_code=400, detail="amount required (or source=stream with viewers_avg / gifts)")
        row = economy.ledger("income" if amount >= 0 else "expense", p, int(amount), source=body.source,
                             label=body.label, meta=body.meta, **extra)
    return {"ok": True, "entity_id": p["id"], "account": row["account"], "delta": row["delta"], "balance": row["balance"], **extra}


class CommissionBody(BaseModel):
    client: str                           # 委托人账号 / player id / 显示名
    kind: str = "song"
    fee: Optional[int] = None             # 缺省在 economy.json song_fee 区间随机
    title: Optional[str] = None


@router.post("/admin/commission")
def admin_commission(body: CommissionBody):
    """W11 ①：手动下一单写歌委托（C / 直播侧 / A 的夹具用）。每日自动出单见 economy.json commissions。"""
    from game import commissions
    from game.world_state import STATE_LOCK
    with STATE_LOCK:
        cm = commissions.create(body.client, kind=body.kind, fee=body.fee, title=body.title, source="admin")
    return {"ok": True, "commission": cm}


@router.get("/commissions")
def list_commissions(player: Optional[str] = None, status: str = "open"):
    """W11 ①：委托列表（open | all）。player 只用于校验存在。"""
    from game import commissions
    if player is not None and player not in _players:
        raise HTTPException(status_code=404, detail=f"player not found: {player}")
    items = commissions.open_items() if status == "open" else commissions.all_items()
    return {"commissions": items, "count": len(items)}


@router.get("/admin/self-sync")
def admin_self_sync():
    """自我层同步状态：发送 / 失败计数、最近 drift、待发 delta（联调用）。"""
    from game.self_sync import snapshot_stats
    return snapshot_stats()
