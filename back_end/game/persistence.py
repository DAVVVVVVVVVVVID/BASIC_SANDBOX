"""
SQLite 检查点（B2）

表：
  players        id, player(JSON), pending_message, use_start_time, last_seen
  object_runtime id, current_users, user_list(JSON)
  time_state     key='singleton', anchor_real, anchor_game, speed, running
  chat_requests  request_id, data(JSON)
  chat_rooms     chat_room_id, data(JSON), seq
  meta           key, value         （last_tick_ts, saved_at, schema_version）

save_checkpoint()：整份状态在一个事务里覆盖写入（状态很小，全量重写比增量简单且不会漂）。
load_checkpoint()：启动时回填 world_state / chat_state / time_state 的模块级字典。
文件：<data_dir>/sandbox.db，SANDBOX_DATA_DIR 可覆盖。
"""

import json
import logging
import sqlite3
from pathlib import Path
log = logging.getLogger(__name__)

from game.paths import data_dir
from game import world_state, chat_state, time_state

SCHEMA_VERSION = 1
CHECKPOINT_INTERVAL = 5.0          # 秒（墙钟）
CATCH_UP_MAX_GAME_MS = 8 * 3600 * 1000.0   # catch_up dt ≤ 8 游戏小时

_SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    id TEXT PRIMARY KEY, player TEXT NOT NULL,
    pending_message TEXT, use_start_time REAL, last_seen REAL
);
CREATE TABLE IF NOT EXISTS object_runtime (
    id TEXT PRIMARY KEY, current_users INTEGER NOT NULL, user_list TEXT NOT NULL, stock TEXT
);
CREATE TABLE IF NOT EXISTS time_state (
    key TEXT PRIMARY KEY, anchor_real REAL, anchor_game REAL, speed REAL, running INTEGER
);
CREATE TABLE IF NOT EXISTS chat_requests (request_id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS chat_rooms (chat_room_id TEXT PRIMARY KEY, data TEXT NOT NULL, seq INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS qq_messages (id TEXT PRIMARY KEY, ts TEXT, from_id TEXT, to_id TEXT, group_id TEXT, kind TEXT, text TEXT, file_ref TEXT, read_at TEXT, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS qq_groups (id TEXT PRIMARY KEY, data TEXT NOT NULL);
"""


def db_path() -> Path:
    return data_dir() / "sandbox.db"


def _connect(path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or db_path()), timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")       # kill -9 时保证已提交事务不丢
    conn.execute("PRAGMA synchronous=FULL")
    conn.executescript(_SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(players)")}
    if "extra" not in cols:                       # W2 迁移：last_used / use_history
        conn.execute("ALTER TABLE players ADD COLUMN extra TEXT")
    ocols = {r[1] for r in conn.execute("PRAGMA table_info(object_runtime)")}
    if "stock" not in ocols:                      # W11 迁移：库存
        conn.execute("ALTER TABLE object_runtime ADD COLUMN stock TEXT")
    return conn


def save_checkpoint(path: Path | None = None) -> dict:
    """写一份完整检查点。返回摘要 {players, rooms, requests, saved_at}。"""
    rt    = world_state.export_runtime()
    chat  = chat_state.export_state()
    from game import qq
    qqs   = qq.export_state()
    ts    = time_state.export_state()
    now   = time_state.now_real()
    conn  = _connect(path)
    try:
        with conn:
            conn.execute("DELETE FROM players")
            conn.executemany(
                "INSERT INTO players (id, player, pending_message, use_start_time, last_seen, extra) VALUES (?,?,?,?,?,?)",
                [(pid, json.dumps(r["player"], ensure_ascii=False), r["pending_message"],
                  r["use_start_time"], r["last_seen"],
                  json.dumps({"last_used": r.get("last_used", {}), "use_history": r.get("use_history", []),
                              "pre_use_pos": r.get("pre_use_pos")}))
                 for pid, r in rt["players"].items()],
            )
            conn.execute("DELETE FROM object_runtime")
            conn.executemany(
                "INSERT INTO object_runtime (id, current_users, user_list, stock) VALUES (?,?,?,?)",
                [(oid, o["currentUsers"], json.dumps(o["userList"]), json.dumps(o.get("stock")) if o.get("stock") is not None else None)
                 for oid, o in rt["objects"].items()],
            )
            conn.execute("DELETE FROM time_state")
            conn.execute(
                "INSERT INTO time_state VALUES ('singleton',?,?,?,?)",
                (ts["anchor_real"], ts["anchor_game"], ts["speed"], 1 if ts["running"] else 0),
            )
            conn.execute("DELETE FROM chat_requests")
            conn.executemany(
                "INSERT INTO chat_requests VALUES (?,?)",
                [(rid, json.dumps(r, ensure_ascii=False)) for rid, r in chat["requests"].items()],
            )
            conn.execute("DELETE FROM chat_rooms")
            conn.executemany(
                "INSERT INTO chat_rooms VALUES (?,?,?)",
                [(rid, json.dumps(r, ensure_ascii=False), chat["seq"].get(rid, 0))
                 for rid, r in chat["rooms"].items()],
            )
            conn.execute("DELETE FROM qq_messages")
            conn.executemany(
                "INSERT INTO qq_messages VALUES (?,?,?,?,?,?,?,?,?,?)",
                [(m["id"], m["ts"], m["from"], m.get("to"), m.get("group"), m["kind"], m.get("text"),
                  json.dumps(m.get("file_ref"), ensure_ascii=False) if m.get("file_ref") else None, m.get("read_at"),
                  json.dumps(m, ensure_ascii=False)) for m in qqs["messages"]],
            )
            conn.execute("DELETE FROM qq_groups")
            conn.executemany("INSERT INTO qq_groups VALUES (?,?)",
                             [(gid, json.dumps(g, ensure_ascii=False)) for gid, g in qqs["groups"].items()])
            conn.executemany(
                "INSERT OR REPLACE INTO meta VALUES (?,?)",
                [("last_tick_ts", repr(now)), ("saved_at", repr(now)),
                 ("qq_contacts", json.dumps({"contacts": qqs["contacts"], "seq": qqs["seq"]})),
                 ("economy", json.dumps(__import__("game.economy", fromlist=["x"]).export_state())),
                 ("production", json.dumps(__import__("game.production", fromlist=["x"]).export_state())),
                 ("commissions", json.dumps(__import__("game.commissions", fromlist=["x"]).export_state(), ensure_ascii=False)),
                 ("doors", json.dumps(__import__("game.doors", fromlist=["x"]).export_state(), ensure_ascii=False)),
                 ("schema_version", str(SCHEMA_VERSION)),
                 ("chat_cooldowns", json.dumps({"last_chat_end": chat["last_chat_end"],
                                                "last_pair_end": chat["last_pair_end"]}))],   # B9 ③
            )
    finally:
        conn.close()
    return {
        "players": len(rt["players"]), "rooms": len(chat["rooms"]),
        "requests": len(chat["requests"]), "saved_at": now, "path": str(path or db_path()),
    }


def load_checkpoint(path: Path | None = None) -> dict | None:
    """
    读取检查点并回填四个模块。没有检查点返回 None，否则返回
    {players, downtime_s, catch_up_game_ms, last_tick_ts}。
    """
    p = path or db_path()
    if not p.exists():
        return None
    conn = _connect(p)
    try:
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
        if "last_tick_ts" not in meta:
            return None   # 空库

        row = conn.execute(
            "SELECT anchor_real, anchor_game, speed, running FROM time_state WHERE key='singleton'"
        ).fetchone()
        if row:
            time_state.import_state({
                "anchor_real": row[0], "anchor_game": row[1],
                "speed": row[2], "running": bool(row[3]),
            })

        players = {}
        for pid, pj, pm, ust, ls, extra in conn.execute(
            "SELECT id, player, pending_message, use_start_time, last_seen, extra FROM players"
        ):
            ex = json.loads(extra) if extra else {}
            players[pid] = {
                "player": json.loads(pj), "pending_message": pm,
                "use_start_time": ust, "last_seen": ls,
                "last_used": ex.get("last_used", {}), "use_history": ex.get("use_history", []),
                "pre_use_pos": ex.get("pre_use_pos"),
            }
        objects = {
            oid: {"currentUsers": cu, "userList": json.loads(ul), "stock": json.loads(st) if st else None}
            for oid, cu, ul, st in conn.execute("SELECT id, current_users, user_list, stock FROM object_runtime")
        }
        n = world_state.import_runtime({"players": players, "objects": objects})

        cooldowns = json.loads(meta.get("chat_cooldowns") or "{}")
        chat_state.import_state({
            "requests": {rid: json.loads(d) for rid, d in conn.execute("SELECT request_id, data FROM chat_requests")},
            "rooms":    {rid: json.loads(d) for rid, d, _ in conn.execute("SELECT chat_room_id, data, seq FROM chat_rooms")},
            "seq":      {rid: s for rid, _, s in conn.execute("SELECT chat_room_id, data, seq FROM chat_rooms")},
            **cooldowns,
        })
        from game import qq, economy, production, commissions
        economy.import_state(json.loads(meta.get("economy") or "{}"))
        production.import_state(json.loads(meta.get("production") or "{}"))
        commissions.import_state(json.loads(meta.get("commissions") or "{}"))
        from game import doors
        doors.import_state(json.loads(meta.get("doors") or "{}"))
        with world_state.STATE_LOCK:
            migrated = doors.migrate_keys(world_state._players)        # §3.41 补：旧检查点的玩家没经过 join，补发自家钥匙（幂等）
        if migrated:
            log.info("door keys migrated: %s", migrated)
        qc = json.loads(meta.get("qq_contacts") or "{}")
        qq.import_state({
            "messages": [json.loads(d) for (d,) in conn.execute("SELECT data FROM qq_messages")],
            "groups":   {gid: json.loads(d) for gid, d in conn.execute("SELECT id, data FROM qq_groups")},
            "contacts": qc.get("contacts", {}), "seq": qc.get("seq", 0),
        })
    finally:
        conn.close()

    with world_state.STATE_LOCK:
        chat_state.reconcile_chat_buffs(world_state._players)     # Q0：chat_active 与房间状态一致

    last_tick_ts = float(meta["last_tick_ts"])
    downtime = max(0.0, time_state.now_real() - last_tick_ts)
    return {
        "players": n, "last_tick_ts": last_tick_ts, "downtime_s": downtime,
        "catch_up_game_ms": catch_up_game_ms(downtime),
    }


def catch_up_game_ms(downtime_s: float) -> float:
    """停机时长 → 需要补算的游戏毫秒（running=False 为 0；上限 8 游戏小时）。"""
    st = time_state.export_state()
    if not st["running"]:
        return 0.0
    return min(CATCH_UP_MAX_GAME_MS, downtime_s * 1000.0 * st["speed"])


def catch_up(game_ms: float) -> float:
    """
    重启后补一次 buff tick（B7 / §3.7 裁定 5）：按停机时长补衰减，不补事件。
    前 4 h 全量（物品 buff + decay）；4–8 h 只补 social / fun / mood / closeness 的衰减，
    fullness / energy 不再扣（她离线等于在睡，假设）。返回实际补算的游戏毫秒（≤ 8 h）。
    """
    if game_ms <= 0:
        return 0.0
    from game.buff_tick import catch_up_tick
    end_ts = time_state.game_now_ts()
    done = 0.0
    with world_state.STATE_LOCK:
        for pid in list(world_state._players.keys()):
            p = world_state._players.get(pid)
            if p is None:
                continue
            r = catch_up_tick(p, game_ms, end_ts)
            done = r["full_ms"] + r["partial_ms"]
            world_state._check_auto_leave(pid)
    return done


def seed_agents_from_self() -> int:
    """启动时把 controller=agent 的 player 从自我层 GET /self/state 重新种一遍（report-A §5）。返回成功数。"""
    from game import self_sync
    if not self_sync.enabled():
        return 0
    n = 0
    gts = time_state.game_now_ts()
    with world_state.STATE_LOCK:
        for p in world_state._players.values():
            if p.get("controller") == "agent" and self_sync.seed_player(p, gts):
                n += 1
    return n
