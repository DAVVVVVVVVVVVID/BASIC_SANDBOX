from fastapi import APIRouter
from models.world import WorldEvent
from game.world_state import get_events
from typing import List

router = APIRouter()


@router.get("/events", response_model=List[WorldEvent])
def get_events_data():
    return get_events()
