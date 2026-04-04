from fastapi import APIRouter
from game.world_state import get_player, get_player_profile, run_buff_tick
from game.time_state import get_last_game_delta

router = APIRouter()


@router.get("/player")
def get_player_data():
    game_delta_ms = get_last_game_delta()
    run_buff_tick(game_delta_ms)
    data = get_player()
    data["profile"] = get_player_profile()
    return data
