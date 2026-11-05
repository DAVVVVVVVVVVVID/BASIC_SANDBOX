import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import world, player, actions, events, history, time_control, agent, chat
from game import persistence, ticker, time_state

log = logging.getLogger("sandbox")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：回填检查点 → 补算停机期间的 tick → 启动后台 ticker（B2 / B7 / B8）
    info = persistence.load_checkpoint()
    if info:
        done = persistence.catch_up(info["catch_up_game_ms"])
        log.info("checkpoint restored: %d players, downtime %.1fs, caught up %.0f game-ms",
                 info["players"], info["downtime_s"], done)
    else:
        time_state.reset_time()   # 首次启动：游戏时间 = 真实当前时间
        log.info("no checkpoint; fresh world at %s", time_state.game_now_iso())
    ticker.start()
    try:
        yield
    finally:
        # 关停：停 ticker，写最后一份检查点
        await ticker.stop()
        try:
            persistence.save_checkpoint()
        except Exception:
            log.exception("final checkpoint failed")


app = FastAPI(title="Town Game API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(world.router)
app.include_router(player.router)
app.include_router(actions.router)
app.include_router(events.router)
app.include_router(history.router)
app.include_router(time_control.router)
app.include_router(agent.router)
app.include_router(chat.router)
