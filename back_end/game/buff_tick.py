"""
Buff Tick 引擎（B4）

run_tick(player, delta_ms) 由 world_state._run_buff_tick_all() 调用，后台 ticker 每 200 ms 驱动（B8）。
delta 单位：游戏毫秒（= 真实毫秒 × speed）。

EFFECT_HANDLERS 由工厂生成：
    <var>_regen        连续：每游戏秒 value（fullness/energy/social/fun/mood）
    <var>_delta        一次性：value，应用后移除（供 B13 推送）
    emotion_tag        timed：进入 emotion_tags（字段 tag），到期移除
    closeness_delta    一次性：closeness[target] += value
    decay              元 buff（source="decay"，_make_player 时挂上）：§2.5 自然衰减
    no_move / no_interact / no_use / move_speed   状态控制（不变）
    hp_regen           兼容别名 = fullness_regen

衰减速率（ARCHITECTURE §2.5，与 whale-self/state.py 同源）：
    fullness −12/游戏小时；energy −8/h，凌晨 0–6 点 ×1.5；fun −10/h；
    social 沙盒 −6/h、live −0.12/s；mood 指数回基线，半衰期 sandbox 120 分钟、live 70 s；
    closeness 每游戏日 −1。
需求值的每次改动都经 set_var/add_var，并通过 ON_VAR_CHANGE 钩子通知自我层同步（decay 不通知，
自我层自己算衰减）。
"""

import math
from datetime import datetime, timedelta
from typing import Callable

# 七变量（ARCHITECTURE §2.5 / B3）。hp 是 fullness 的别名（过渡一个版本）。
NEED_VARS: tuple[str, ...] = ("fullness", "energy", "social", "fun", "mood")
VAR_ALIASES: dict[str, str] = {"hp": "fullness"}
VAR_MIN, VAR_MAX = 0.0, 100.0

SCENES = ("sandbox", "live")
# 每游戏秒变化量（负为衰减）。world-v1.1：从 game/needs.json 读（醒 / 睡两套 + 直播 / 工作额外），这里的表只是「醒着」的派生视图（self_sync 等旧引用同源）。
def _load_rates() -> dict[str, dict[str, float]]:
    from game import needs_cfg as needs
    awake = {v: needs.per_hour("awake", v) / 3600.0 for v in ("fullness", "energy", "social", "fun")}
    live = dict(awake); live["fullness"] += needs.extra_per_hour("live", "fullness") / 3600.0
    asleep = {v: needs.per_hour("asleep", v) / 3600.0 for v in ("fullness", "energy", "social", "fun")}
    return {"sandbox": awake, "live": live, "asleep": asleep}


DECAY_RATES: dict[str, dict[str, float]] = _load_rates()


def reload_rates() -> None:
    DECAY_RATES.clear(); DECAY_RATES.update(_load_rates())


MOOD_HALF_LIFE_S = {"sandbox": 120 * 60.0, "live": 70.0}
NIGHT_HOURS = range(0, 6)
NIGHT_ENERGY_MULT = 1.0           # world-v1.1：不分昼夜（needs.json night_energy_mult；旧值 1.5）
CLOSENESS_PER_DAY = -1.0
MOOD_BASE_DEFAULT = 65.0

DECAY_SOURCE = "decay"
DECAY_BUFF = {"key": "decay", "value": 0.0, "mode": "persistent", "remaining": None, "source": DECAY_SOURCE}

# 自我层同步钩子：fn(player_id, var, applied_delta)。decay 不触发。
ON_VAR_CHANGE: Callable[[str, str, float], None] | None = None


def canonical_var(key: str) -> str | None:
    """把 effect key 归一到需求变量名；不是需求变量返回 None。"""
    key = VAR_ALIASES.get(key, key)
    return key if key in NEED_VARS else None


def set_var(player: dict, key: str, value: float, *, track: bool = True) -> float:
    """对需求变量做 0–100 clamp 写入；fullness 与 hp 同步。返回实际变化量。"""
    var = canonical_var(key)
    if var is None:
        return 0.0
    old = float(player.get(var, 0.0))
    v = min(VAR_MAX, max(VAR_MIN, float(value)))
    player[var] = v
    if var == "fullness":
        player["hp"] = v
    applied = v - old
    if track and applied != 0.0 and ON_VAR_CHANGE is not None:
        ON_VAR_CHANGE(player.get("id", ""), var, applied)
    return applied


def add_var(player: dict, key: str, delta: float, *, track: bool = True) -> float:
    var = canonical_var(key)
    if var is None:
        return 0.0
    return set_var(player, var, player.get(var, 0.0) + delta, track=track)


def add_closeness(player: dict, target: str, delta: float) -> float:
    cl = player.setdefault("closeness", {})
    old = float(cl.get(target, 0.0))
    new = min(VAR_MAX, max(VAR_MIN, old + float(delta)))
    cl[target] = new
    return new - old


def mood_baseline(E: float = 50.0, N: float = 50.0) -> float:
    """mood 基线 = 65 + 0.2·(E−50) − 0.3·(N−50)（ARCHITECTURE §2.5）。"""
    return MOOD_BASE_DEFAULT + 0.2 * (float(E) - 50.0) - 0.3 * (float(N) - 50.0)


# ── 时间工具 ──────────────────────────────────────────────────────────────────

def _tz():
    from game.time_state import GAME_TZ
    return GAME_TZ


def night_seconds(start_ts: float, end_ts: float) -> float:
    """[start, end) 中落在凌晨 0–6 点（GAME_TZ）的秒数。与 whale-self night_seconds 同算法。"""
    if end_ts <= start_ts:
        return 0.0
    tz = _tz()
    start = datetime.fromtimestamp(start_ts, tz)
    end = datetime.fromtimestamp(end_ts, tz)
    total = 0.0
    cur = start
    while cur < end:
        nxt = (cur + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        seg_end = min(nxt, end)
        if cur.hour in NIGHT_HOURS:
            total += (seg_end - cur).total_seconds()
        cur = seg_end
    return total


# ── handler 工厂 ──────────────────────────────────────────────────────────────

def _make_regen(var: str):
    def handler(player: dict, buff: dict, delta: float) -> None:
        add_var(player, var, buff["value"] * delta / 1000.0)
    handler.__name__ = f"_handler_{var}_regen"
    return handler


def _consume(buff: dict) -> None:
    """一次性 buff：标记为 timed 且 remaining=0，下一次 ① 步移除。"""
    buff["mode"] = "timed"
    buff["remaining"] = 0.0


def _make_delta(var: str):
    def handler(player: dict, buff: dict, delta: float) -> None:
        add_var(player, var, buff["value"])
        _consume(buff)
    handler.__name__ = f"_handler_{var}_delta"
    return handler


def _handler_emotion_tag(player: dict, buff: dict, delta: float) -> None:
    """buffs 里出现 emotion_tag 时搬到 emotion_tags（去重），本条消费掉。"""
    tag = buff.get("tag") or buff.get("source") or "unknown"
    tags = player.setdefault("emotion_tags", [])
    player["emotion_tags"] = [t for t in tags if t["key"] != tag] + [{
        "key": tag, "value": buff.get("value", 0.0), "mode": "timed",
        "remaining": buff.get("remaining") if buff.get("mode") == "timed" else None,
        "source": buff.get("source", "effects"),
    }]
    _consume(buff)


def _handler_closeness_delta(player: dict, buff: dict, delta: float) -> None:
    target = buff.get("target")
    if target:
        add_closeness(player, target, buff["value"])
    _consume(buff)


# 当前 tick 的游戏时刻区间（由 run_tick 设置，供 decay 算夜间倍率）
_TICK_CTX: dict = {"game_end_ts": None, "skip_vars": frozenset()}


def _handler_decay(player: dict, buff: dict, delta: float) -> None:
    dt = delta / 1000.0
    if dt <= 0:
        return
    scene = player.get("scene", "sandbox")
    if scene not in DECAY_RATES:
        scene = "sandbox"
    skip = _TICK_CTX["skip_vars"]
    tags = player.get("tags") or []
    rates = DECAY_RATES["asleep"] if "sleeping" in tags else DECAY_RATES[scene]      # world-v1.1：睡着另一套（精力 / 社交 / 娱乐不降）
    end_ts = _TICK_CTX["game_end_ts"]
    from game import needs_cfg as needs
    work_extra = needs.extra_per_hour("work", "energy") / 3600.0 if "working" in tags else 0.0   # 使用 work 类物品：精力再扣
    for var, r in rates.items():
        if var in skip:
            continue
        if var == "energy":
            r = r + work_extra
        if var == "energy" and end_ts is not None and NIGHT_ENERGY_MULT != 1.0:
            ns = night_seconds(end_ts - dt, end_ts)
            d = r * (dt - ns) + r * NIGHT_ENERGY_MULT * ns
        else:
            d = r * dt
        add_var(player, var, d, track=False)
    if "mood" not in skip:
        base = float(player.get("mood_base", MOOD_BASE_DEFAULT))
        half = MOOD_HALF_LIFE_S.get(scene, MOOD_HALF_LIFE_S["sandbox"])
        cur = float(player.get("mood", base))
        set_var(player, "mood", base + (cur - base) * math.pow(0.5, dt / half), track=False)
    if "closeness" not in skip and player.get("closeness"):
        dec = CLOSENESS_PER_DAY * dt / 86400.0
        for k in list(player["closeness"].keys()):
            add_closeness(player, k, dec)


def _handler_table_social(player: dict, buff: dict, delta: float) -> None:
    """world-v1.1：同桌社交——只有这张桌上还有第二个人时才按 value（点 / 游戏秒）加。buff.source = 物品 id。"""
    try:
        from game.world_state import get_object_by_id
        obj = get_object_by_id(buff.get("source") or "")
    except Exception:
        obj = None
    if obj is None or int(obj.get("currentUsers", 0)) < 2:
        return
    add_var(player, "social", buff["value"] * delta / 1000.0)


def _handler_no_move(player: dict, buff: dict, delta: float) -> None:
    player["canMove"] = False

def _handler_no_interact(player: dict, buff: dict, delta: float) -> None:
    player["canInteract"] = False

def _handler_no_use(player: dict, buff: dict, delta: float) -> None:
    player["canUse"] = False

def _handler_move_speed(player: dict, buff: dict, delta: float) -> None:
    player["moveSpeed"] *= buff["value"]

def _handler_reading(player: dict, buff: dict, delta: float) -> None:
    """W10 ③：读 QQ 期间不可做别的（canMove / canUse=false，tags 带 reading；buff 到期由 run_tick 摘 tag）。"""
    player["canMove"] = False
    player["canUse"] = False
    if "reading" not in player.get("tags", []):
        player.setdefault("tags", []).append("reading")


EFFECT_HANDLERS: dict = {
    **{f"{v}_regen": _make_regen(v) for v in NEED_VARS},
    **{f"{v}_delta": _make_delta(v) for v in NEED_VARS},
    "hp_regen":        _make_regen("fullness"),     # 兼容别名
    "hp_delta":        _make_delta("fullness"),
    "emotion_tag":     _handler_emotion_tag,
    "closeness_delta": _handler_closeness_delta,
    "decay":           _handler_decay,
    "table_social":    _handler_table_social,
    "no_move":         _handler_no_move,
    "no_interact":     _handler_no_interact,
    "no_use":          _handler_no_use,
    "move_speed":      _handler_move_speed,
    "reading":         _handler_reading,
}


CONTROL_KEYS = ("no_move", "no_interact", "no_use", "move_speed", "reading")


def apply_control_flags(player: dict) -> None:
    """Q0c：buff 增删后立刻重算 canMove / canInteract / canUse / moveSpeed（不等下一个 tick）。
    只跑控制类 handler，不动需求值、不扣计时。"""
    player["canMove"] = True
    player["canInteract"] = True
    player["canUse"] = True
    player["moveSpeed"] = 1.0
    for b in player.get("buffs", []):
        if b.get("key") in CONTROL_KEYS:
            EFFECT_HANDLERS[b["key"]](player, b, 0.0)


def _expire_timed(items: list[dict], delta: float) -> list[dict]:
    surviving = []
    for b in items:
        if b.get("mode") == "timed":
            b["remaining"] = (b.get("remaining") or 0.0) - delta
            if b["remaining"] > 0:
                surviving.append(b)
        else:
            surviving.append(b)
    return surviving


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, _tz()).isoformat(timespec="seconds")


def run_tick(
    player: dict,
    delta: float,
    now_ts: float | None = None,
    game_ts: float | None = None,
    skip_vars: frozenset | set = frozenset(),
) -> None:
    """
    固定四步：
    ① 递减 timed buff / emotion_tag 的 remaining，移除归零项
    ② 重置状态控制字段
    ③ 遍历 buffs，执行 EFFECT_HANDLERS（decay 元 buff 在其中）
    ④ 记录 last_tick_ts（ISO 8601，游戏时刻）
    game_ts：本 tick 结束时的游戏时刻（epoch 秒），缺省取 time_state.game_now_ts()。
    skip_vars：catch_up 第二阶段用，decay 跳过这些变量。
    """
    if game_ts is None:
        from game.time_state import game_now_ts
        game_ts = game_now_ts()
    _TICK_CTX["game_end_ts"] = game_ts
    _TICK_CTX["skip_vars"] = frozenset(skip_vars)

    # ① 递减 timed 项
    player["buffs"] = _expire_timed(player["buffs"], delta)
    if "reading" in player.get("tags", []) and not any(b.get("key") == "reading" for b in player["buffs"]):
        player["tags"].remove("reading")                           # W10 ③：读完 1 游戏分钟摘 reading
    if "emotion_tags" in player:
        player["emotion_tags"] = _expire_timed(player["emotion_tags"], delta)

    # ② 重置状态控制字段
    player["canMove"]     = True
    player["canInteract"] = True
    player["canUse"]      = True
    player["moveSpeed"]   = 1.0

    # ③ 执行 effect handlers（遍历副本：handler 可能消费 / 搬运 buff）
    for b in list(player["buffs"]):
        handler = EFFECT_HANDLERS.get(b["key"])
        if handler:
            handler(player, b, delta)

    # ④ 记录 tick 时刻（ISO，§3.7 裁定 3）
    player["last_tick_ts"] = _iso(game_ts)


# ── catch_up（B7 / §3.7 裁定 5） ───────────────────────────────────────────────

CATCH_UP_MAX_MS        = 8 * 3600 * 1000.0   # social / fun / mood / closeness 与物品 buff
CATCH_UP_SLEEP_CAP_MS  = 4 * 3600 * 1000.0   # fullness / energy：她离线等于在睡（假设）
SLEEP_CAPPED_VARS = frozenset({"fullness", "energy"})


def catch_up_tick(player: dict, game_ms: float, game_end_ts: float) -> dict:
    """
    停机补算：前 4 h 全量 tick；4–8 h 只补 social / fun / mood / closeness 的衰减，
    不再扣 fullness / energy。返回 {"full_ms", "partial_ms"}。
    """
    total = min(max(0.0, game_ms), CATCH_UP_MAX_MS)
    full = min(total, CATCH_UP_SLEEP_CAP_MS)
    partial = total - full
    start_ts = game_end_ts - total / 1000.0
    if full > 0:
        run_tick(player, full, game_ts=start_ts + full / 1000.0)
    if partial > 0:
        # 第二阶段只跑 decay 元 buff
        saved = player["buffs"]
        player["buffs"] = [b for b in saved if b.get("key") == "decay"]
        run_tick(player, partial, game_ts=game_end_ts, skip_vars=SLEEP_CAPPED_VARS)
        player["buffs"] = _expire_timed([b for b in saved if b.get("key") != "decay"], partial) + player["buffs"]
    return {"full_ms": full, "partial_ms": partial}
