from fastapi import APIRouter
from pydantic import BaseModel
from game.time_state import set_running, set_speed, reset_time, get_time_state

router = APIRouter(prefix="/time")


class SpeedRequest(BaseModel):
    value: float


@router.post("/toggle")
def toggle_time():
    state = get_time_state()
    set_running(not state["running"])
    return get_time_state()


@router.post("/speed")
def update_speed(body: SpeedRequest):
    actual = set_speed(body.value)
    return {"speed": actual}


@router.post("/reset")
def reset():
    reset_time()
    return get_time_state()
