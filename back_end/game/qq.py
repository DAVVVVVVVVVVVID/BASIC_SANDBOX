"""
QQ：沙盒内手机消息（W10 ③，world-bible/08-phone-messaging.md）。

账号：agent 玩家用 agent_id（whale / achan / npc_*），人类玩家用 player id；人不在线账号仍存在（消息等他上线来读）。
消息：{id, ts, game_time, from, from_name, to|null, group|null, kind text|file, text, file_ref|null, read_at|null}
  - 1:1：to = 账号；群：group = 群 id，群成员各自有自己的 read_at（read_by）。
  - file 只允许 items.json 里 class=file 的物品（歌 / 文稿 / 图片），实物拒绝 not_transferable；文件是复制，发送者保留。
读：POST /qq/read 一次占用 read_game_seconds（默认 60 游戏秒）：加 timed buff `reading`（canMove/canUse=false，tags 带 reading）。
约束：睡觉中 / 直播中不看手机（tags sleeping / streaming 或 scene=live → phone_unavailable）。
数据：每条 send / read 追加 data/qq/<date>.jsonl（进数据集 kinds=qq）；ws 推 {type:"qq", event:"message"|"read"}；检查点表 qq_messages / qq_groups。
"""
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

from game.paths import data_dir

_LOCK = threading.RLock()
_CFG: dict = json.load(open(Path(__file__).with_name("qq_config.json"), encoding="utf-8"))
READ_GAME_SECONDS = float(_CFG.get("read_game_seconds", 60))
SOCIAL_PER_MESSAGE = float(_CFG.get("social_per_message", 0.0))
NAMES: dict[str, str] = dict(_CFG.get("names", {}))

_messages: list[dict] = []                    # 时间序
_groups: dict[str, dict] = {}                 # id -> {id, name, members[]}
_contacts: dict[str, set[str]] = {}           # 账号 -> 账号集合（互相）
_MEM_MAX = 5000
_SEQ = 0


def _init_defaults() -> None:
    for g in _CFG.get("groups", []):
        _groups[g["id"]] = {"id": g["id"], "name": g["name"], "members": list(g["members"])}
    for a, lst in _CFG.get("contacts", {}).items():
        for b in lst:
            _contacts.setdefault(a, set()).add(b)
            _contacts.setdefault(b, set()).add(a)


_init_defaults()


# ── 账号 ──
def account_of(player: dict) -> str:
    return player.get("agent_id") if player.get("controller") == "agent" and player.get("agent_id") else player["id"]


def _players_by_account() -> dict[str, dict]:
    from game.world_state import _players
    return {account_of(p): p for p in _players.values()}


def display_name(account: str) -> str:
    if account in _groups:
        return _groups[account]["name"]
    p = _players_by_account().get(account)
    if p:
        return p.get("name") or account
    return NAMES.get(account, account)


def resolve_account(ref: str) -> str | None:
    """账号 / player id / agent_id / 显示名 → 账号；未知返回 None。"""
    if not ref:
        return None
    if ref in _groups:
        return None
    from game.world_state import _players
    if ref in _players:
        return account_of(_players[ref])
    by_acc = _players_by_account()
    if ref in by_acc or ref in NAMES or ref in _contacts:
        return ref
    for acc, nm in NAMES.items():
        if nm == ref:
            return acc
    for acc, p in by_acc.items():
        if p.get("name") == ref:
            return acc
    return None


def _busy_reason(player: dict) -> str | None:
    tags = set(player.get("tags", []))
    if "sleeping" in tags or "streaming" in tags or player.get("scene") == "live":
        return "phone_unavailable"
    return None


# ── 日志 / 推送 ──
def _dir() -> Path:
    p = data_dir() / "qq"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _base() -> dict:
    try:
        from game.world_state import TOWN, MAP_VERSION, SANDBOX_SEED
        from game.time_state import game_now_iso
        return {"town": TOWN, "map_version": MAP_VERSION, "seed": SANDBOX_SEED, "game_time": game_now_iso()}
    except Exception:
        return {"town": None, "map_version": None, "seed": None, "game_time": None}


def _log(row: dict) -> dict:
    now = datetime.now()
    entry = {"ts": now.isoformat(timespec="milliseconds"), **_base(), **row}
    with _LOCK:
        with open(_dir() / f"{now.date().isoformat()}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def _push(ev: dict) -> None:
    try:
        from routers.ws import hub
        hub.push_event({"type": "qq", **ev})
    except Exception:
        pass


# ── 发送 ──
def send(entity_id: str, *, to: str | None, group: str | None, kind: str, text: str | None,
         file_ref: dict | None) -> tuple[dict | None, str | None]:
    """返回 (message, None) 或 (None, reason)。"""
    from game import world_state, inventory
    from game.buff_tick import add_var
    from game.time_state import game_now_iso
    global _SEQ
    with world_state.STATE_LOCK, _LOCK:
        p = world_state._players.get(entity_id)
        if p is None:
            return None, "entity_not_found"
        busy = _busy_reason(p)
        if busy:
            return None, busy
        if kind not in ("text", "file"):
            return None, "bad_kind"
        if kind == "text" and not (text or "").strip():
            return None, "empty_text"
        if kind == "file":
            item = (file_ref or {}).get("item")
            if not item or not inventory.is_file_item(item):
                return None, "not_transferable"
        if bool(to) == bool(group):
            return None, "need_to_or_group"
        me = account_of(p)
        to_acc = None
        if group:
            g = _groups.get(group)
            if g is None:
                return None, "unknown_group"
            if me not in g["members"]:
                return None, "not_member"
        else:
            to_acc = resolve_account(to)
            if to_acc is None:
                return None, "unknown_recipient"
            if to_acc == me:
                return None, "self_message"
        _SEQ += 1
        msg = {"id": f"q{_SEQ:06d}_{uuid.uuid4().hex[:6]}", "ts": datetime.now().isoformat(timespec="milliseconds"),
               "game_time": game_now_iso(), "from": me, "from_name": p.get("name") or display_name(me),
               "to": to_acc, "group": group, "kind": kind, "text": (text or "") if kind == "text" else (text or ""),
               "file_ref": dict(file_ref) if kind == "file" else None, "read_at": None, "read_by": {}}
        _messages.append(msg)
        if len(_messages) > _MEM_MAX:
            del _messages[: len(_messages) - _MEM_MAX]
        if to_acc:
            _contacts.setdefault(me, set()).add(to_acc)
            _contacts.setdefault(to_acc, set()).add(me)
        # 文件：复制给在线的收件人（群发给每个在线成员）
        delivered: list[str] = []
        if kind == "file":
            by_acc = _players_by_account()
            targets = [to_acc] if to_acc else [m for m in _groups[group]["members"] if m != me]
            for t in targets:
                rp = by_acc.get(t)
                if rp is not None and inventory.add(rp, file_ref["item"], 1, meta=file_ref.get("meta")) is None:
                    delivered.append(t)
            msg["item_delivered_to"] = delivered
        if SOCIAL_PER_MESSAGE:
            add_var(p, "social", SOCIAL_PER_MESSAGE)
        world_state.mark_input(entity_id)
        _log({**{k: v for k, v in msg.items() if k not in ("read_by", "kind")}, "msg_kind": msg["kind"], "kind": "message"})
        _push({"event": "message", **{k: v for k, v in msg.items() if k not in ("read_by",)}})
        return _public(msg, me), None


def _public(msg: dict, me: str | None = None) -> dict:
    d = {k: v for k, v in msg.items() if k != "read_by"}
    if me is not None:
        d["direction"] = "out" if msg["from"] == me else "in"
        if msg.get("group"):
            d["read_at"] = msg["read_by"].get(me) if msg["from"] != me else msg["ts"]
    return d


def _is_mine(msg: dict, me: str) -> bool:
    if msg.get("group"):
        return me in _groups.get(msg["group"], {}).get("members", [])
    return msg["from"] == me or msg["to"] == me


def _unread_of(msg: dict, me: str) -> bool:
    if msg["from"] == me:
        return False
    if msg.get("group"):
        return me in _groups.get(msg["group"], {}).get("members", []) and me not in msg["read_by"]
    return msg["to"] == me and msg["read_at"] is None


def _peer_of(msg: dict, me: str) -> str:
    return msg["group"] or (msg["to"] if msg["from"] == me else msg["from"])


# ── 收件箱 / 未读 ──
def inbox(entity_id: str, *, since: str | None = None, peer: str | None = None, limit: int = 100,
          unread_only: bool = False) -> dict | None:
    from game.world_state import _players
    with _LOCK:
        p = _players.get(entity_id)
        if p is None:
            return None
        me = account_of(p)
        peer_acc = (peer if peer in _groups else resolve_account(peer)) if peer else None
        rows = []
        for m in _messages:
            if not _is_mine(m, me):
                continue
            if since and (m["ts"] <= since or m["id"] == since):      # since：ISO 时间戳（不含）
                continue
            if peer_acc and _peer_of(m, me) != peer_acc:
                continue
            if unread_only and not _unread_of(m, me):
                continue
            rows.append(_public(m, me))
        rows = rows[-limit:]
        return {"account": me, "messages": rows, "unread": unread_summary(me), "unread_total": sum(unread_summary(me).values())}


def unread_summary(account: str) -> dict[str, int]:
    """{发件人 / 群显示名: 条数}（perceive 只给这个，不给正文）。"""
    out: dict[str, int] = {}
    with _LOCK:
        for m in _messages:
            if _unread_of(m, account):
                key = display_name(m["group"] or m["from"])
                out[key] = out.get(key, 0) + 1
    return out


def phone_view(entity_id: str) -> dict | None:
    from game.world_state import _players
    p = _players.get(entity_id)
    if p is None:
        return None
    s = unread_summary(account_of(p))
    return {"unread": s, "unread_total": sum(s.values())}


# ── 读 ──
def read(entity_id: str, *, peer: str | None = None) -> tuple[dict | None, str | None]:
    from game import world_state
    from game.buff_tick import add_var, apply_control_flags
    with world_state.STATE_LOCK, _LOCK:
        p = world_state._players.get(entity_id)
        if p is None:
            return None, "entity_not_found"
        busy = _busy_reason(p)
        if busy:
            return None, busy
        me = account_of(p)
        peer_acc = (peer if peer in _groups else resolve_account(peer)) if peer else None
        now = datetime.now().isoformat(timespec="milliseconds")
        got = []
        for m in _messages:
            if not _unread_of(m, me):
                continue
            if peer_acc and _peer_of(m, me) != peer_acc:
                continue
            if m.get("group"):
                m["read_by"][me] = now
            else:
                m["read_at"] = now
            got.append(_public(m, me))
        # 占用 1 游戏分钟：reading buff（控制类）+ tag
        dur_ms = READ_GAME_SECONDS * 1000.0
        p["buffs"] = [b for b in p["buffs"] if not (b["key"] == "reading" and b["source"] == "qq")]
        p["buffs"].append({"key": "reading", "value": 1.0, "mode": "timed", "remaining": dur_ms, "source": "qq"})
        if "reading" not in p["tags"]:
            p["tags"].append("reading")
        apply_control_flags(p)
        if got and SOCIAL_PER_MESSAGE:
            add_var(p, "social", SOCIAL_PER_MESSAGE * len(got))
        world_state.mark_input(entity_id)
        _log({"kind": "read", "account": me, "peer": peer_acc, "ids": [m["id"] for m in got], "count": len(got),
              "busy_game_seconds": READ_GAME_SECONDS})
        _push({"event": "read", "account": me, "entity": entity_id, "peer": peer_acc, "count": len(got), "ids": [m["id"] for m in got]})
        return {"account": me, "messages": got, "count": len(got), "busy_game_seconds": READ_GAME_SECONDS,
                "unread": unread_summary(me)}, None


# ── 通讯录 ──
def contacts(entity_id: str) -> dict | None:
    from game.world_state import _players, is_present
    with _LOCK:
        p = _players.get(entity_id)
        if p is None:
            return None
        me = account_of(p)
        by_acc = _players_by_account()
        unread = {}
        for m in _messages:
            if _unread_of(m, me):
                k = m["group"] or m["from"]
                unread[k] = unread.get(k, 0) + 1
        accs = set(_contacts.get(me, set()))
        if p.get("controller") != "agent":                      # 人类玩家：通讯录 = 所有已知账号
            accs |= set(NAMES) | set(by_acc)
        accs.discard(me)
        rows = []
        for a in sorted(accs):
            rp = by_acc.get(a)
            rows.append({"id": a, "account": a, "name": display_name(a), "online": rp is not None and is_present(rp),
                         "player_id": rp["id"] if rp else None, "unread": unread.get(a, 0)})
        groups = [{"id": g["id"], "name": g["name"], "members": list(g["members"]),
                   "member_names": [display_name(x) for x in g["members"]], "unread": unread.get(g["id"], 0)}
                  for g in _groups.values() if me in g["members"]]
        return {"account": me, "name": p.get("name") or display_name(me), "contacts": rows, "groups": groups}


# ── 持久化 ──
def export_state() -> dict:
    with _LOCK:
        return {"messages": [dict(m) for m in _messages], "groups": {k: dict(v) for k, v in _groups.items()},
                "contacts": {k: sorted(v) for k, v in _contacts.items()}, "seq": _SEQ}


def import_state(data: dict) -> None:
    global _SEQ
    with _LOCK:
        _messages.clear(); _groups.clear(); _contacts.clear()
        _init_defaults()
        for m in data.get("messages") or []:
            m.setdefault("read_by", {}); _messages.append(m)
        _messages.sort(key=lambda m: m["ts"])
        for gid, g in (data.get("groups") or {}).items():
            _groups[gid] = g
        for a, lst in (data.get("contacts") or {}).items():
            _contacts.setdefault(a, set()).update(lst)
        _SEQ = max(int(data.get("seq") or 0), len(_messages))


def _reset_for_tests() -> None:
    global _SEQ
    with _LOCK:
        _messages.clear(); _groups.clear(); _contacts.clear(); _SEQ = 0
        _init_defaults()
