from fastapi import APIRouter
from models.world import WorldData
from game.world_state import get_world

router = APIRouter()


@router.get("/world", response_model=WorldData)
def get_world_data():
    return get_world()
