from fastapi import APIRouter
from models.player import Player
from game.world_state import get_player

router = APIRouter()


@router.get("/player", response_model=Player)
def get_player_data():
    return get_player()
