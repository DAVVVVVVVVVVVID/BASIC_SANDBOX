from fastapi import APIRouter
from models.player import Player
from game.world_state import get_player, get_player_profile, run_buff_tick

router = APIRouter()

_TICK_DELTA = 200.0  # ms，与前端轮询间隔对齐


@router.get("/player")
def get_player_data():
    run_buff_tick(_TICK_DELTA)
    data = get_player()
    data["profile"] = get_player_profile()
    return data
