from fastapi import APIRouter
from models.world import WorldData
from game.world_state import get_world

router = APIRouter()


@router.get("/world", response_model=WorldData)
def get_world_data():
    # 只读（B8）：时间推进与 buff tick 由后台 ticker 负责
    return get_world()
