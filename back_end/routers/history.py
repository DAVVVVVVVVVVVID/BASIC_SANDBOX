from fastapi import APIRouter
from game.action_log import get_log

router = APIRouter()


@router.get("/history")
def history():
    return get_log()
