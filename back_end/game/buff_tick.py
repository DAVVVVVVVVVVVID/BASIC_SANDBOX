# Buff Tick 引擎
# run_tick(player, delta) 由 world_state.run_buff_tick() 调用，每次 GET /player 前执行
# delta 单位：毫秒（通常为 200）

def _handler_energy_regen(player: dict, buff: dict, delta: float) -> None:
    player["energy"] = min(100.0, max(0.0, player["energy"] + buff["value"] * delta / 1000.0))

def _handler_hp_regen(player: dict, buff: dict, delta: float) -> None:
    player["hp"] = min(100.0, max(0.0, player["hp"] + buff["value"] * delta / 1000.0))

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


def run_tick(player: dict, delta: float) -> None:
    """
    固定三步：
    ① 递减 instant buff 的 remaining，移除归零项
    ② 重置状态控制字段
    ③ 遍历 buffs，执行 EFFECT_HANDLERS
    """
    # ① 递减 instant buff
    surviving = []
    for b in player["buffs"]:
        if b["mode"] == "instant":
            b["remaining"] -= delta
            if b["remaining"] > 0:
                surviving.append(b)
        else:
            surviving.append(b)
    player["buffs"] = surviving

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
