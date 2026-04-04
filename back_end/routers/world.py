import time
from fastapi import APIRouter
from models.world import WorldData
from game.world_state import get_world
from game.time_state import advance_time

router = APIRouter()

_last_tick: float = time.monotonic()


@router.get("/world", response_model=WorldData)
def get_world_data():
    global _last_tick
    now = time.monotonic()
    real_delta_ms = (now - _last_tick) * 1000.0
    _last_tick = now
    advance_time(real_delta_ms)
    return get_world()
