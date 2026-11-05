# Buff Tick 引擎
# run_tick(player, delta) 由 world_state._run_buff_tick_all() 调用，
# 由后台 ticker（game/ticker.py）每 200 ms 驱动（B8），不再依赖客户端轮询。
# delta 单位：游戏毫秒（= 真实毫秒 × speed）

import time

# 七变量（ARCHITECTURE §2.5 / B3）。hp 是 fullness 的别名（过渡一个版本）。
NEED_VARS: tuple[str, ...] = ("fullness", "energy", "social", "fun", "mood")
VAR_ALIASES: dict[str, str] = {"hp": "fullness"}
VAR_MIN, VAR_MAX = 0.0, 100.0


def canonical_var(key: str) -> str | None:
    """把 effect key 归一到七变量名；不是需求变量返回 None。"""
    key = VAR_ALIASES.get(key, key)
    return key if key in NEED_VARS else None


def set_var(player: dict, key: str, value: float) -> None:
    """对需求变量做 0–100 clamp 写入；fullness 与 hp 同步。"""
    var = canonical_var(key)
    if var is None:
        return
    v = min(VAR_MAX, max(VAR_MIN, float(value)))
    player[var] = v
    if var == "fullness":
        player["hp"] = v


def add_var(player: dict, key: str, delta: float) -> None:
    var = canonical_var(key)
    if var is None:
        return
    set_var(player, var, player.get(var, 0.0) + delta)


def _handler_energy_regen(player: dict, buff: dict, delta: float) -> None:
    add_var(player, "energy", buff["value"] * delta / 1000.0)

def _handler_hp_regen(player: dict, buff: dict, delta: float) -> None:
    # hp 已是 fullness 别名：两者同步修改
    add_var(player, "fullness", buff["value"] * delta / 1000.0)

def _handler_no_move(player: dict, buff: dict, delta: float) -> None:
    player["canMove"] = False

def _handler_no_interact(player: dict, buff: dict, delta: float) -> None:
    player["canInteract"] = False

def _handler_no_use(player: dict, buff: dict, delta: float) -> None:
    player["canUse"] = False

def _handler_move_speed(player: dict, buff: dict, delta: float) -> None:
    player["moveSpeed"] *= buff["value"]


EFFECT_HANDLERS: dict = {
    "energy_regen": _handler_energy_regen,
    "hp_regen":     _handler_hp_regen,
    "no_move":      _handler_no_move,
    "no_interact":  _handler_no_interact,
    "no_use":       _handler_no_use,
    "move_speed":   _handler_move_speed,
}


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


def run_tick(player: dict, delta: float, now_ts: float | None = None) -> None:
    """
    固定四步：
    ① 递减 timed buff / emotion_tag 的 remaining，移除归零项
    ② 重置状态控制字段
    ③ 遍历 buffs，执行 EFFECT_HANDLERS
    ④ 记录 last_tick_ts（墙钟 epoch 秒）
    """
    # ① 递减 timed 项
    player["buffs"] = _expire_timed(player["buffs"], delta)
    if "emotion_tags" in player:
        player["emotion_tags"] = _expire_timed(player["emotion_tags"], delta)

    # ② 重置状态控制字段
    player["canMove"]     = True
    player["canInteract"] = True
    player["canUse"]      = True
    player["moveSpeed"]   = 1.0

    # ③ 执行 effect handlers
    for b in player["buffs"]:
        handler = EFFECT_HANDLERS.get(b["key"])
        if handler:
            handler(player, b, delta)

    # ④ 记录 tick 时刻
    player["last_tick_ts"] = now_ts if now_ts is not None else time.time()
