from fastapi import APIRouter
from pydantic import BaseModel
from game.time_state import set_running, set_speed, reset_time, get_time_state

router = APIRouter(prefix="/time")


class SpeedRequest(BaseModel):
    value: float


def _nd(op: str, **f):
    from game import external_log
    external_log.log("nondeterministic", None, op=op, **f)


@router.post("/toggle")
def toggle_time():
    state = get_time_state()
    set_running(not state["running"])
    _nd("time_toggle", running=not state["running"])
    return get_time_state()


@router.post("/speed")
def update_speed(body: SpeedRequest):
    actual = set_speed(body.value)
    _nd("time_speed", speed=actual)
    return {"speed": actual}


@router.post("/reset")
def reset():
    reset_time()
    _nd("time_reset")
    return get_time_state()
