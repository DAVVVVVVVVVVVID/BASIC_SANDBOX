import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import world, player, actions, events, history, time_control, agent, chat, ws, scenario, qq, door
from game import persistence, ticker, time_state, self_sync

log = logging.getLogger("sandbox")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：回填检查点 → 补算停机期间的 tick → 启动后台 ticker（B2 / B7 / B8）
    info = persistence.load_checkpoint()
    if info:
        done = persistence.catch_up(info["catch_up_game_ms"])
        log.info("checkpoint restored: %d players, downtime %.1fs, caught up %.0f game-ms",
                 info["players"], info["downtime_s"], done)
        seeded = persistence.seed_agents_from_self()
        if seeded:
            log.info("re-seeded %d agent player(s) from self-layer %s", seeded, self_sync.stats["self_url"])
    else:
        time_state.reset_time()   # 首次启动：游戏时间 = 真实当前时间
        log.info("no checkpoint; fresh world at %s", time_state.game_now_iso())
    ticker.start()
    self_sync.start()             # 自我层 delta 同步线程（SELF_SYNC=0 关闭）
    ws.hub.start()                # B17：/ws/world 推送
    try:
        yield
    finally:
        # 关停：停 ticker，写最后一份检查点
        await ticker.stop()
        await ws.hub.stop()
        self_sync.stop()
        try:
            persistence.save_checkpoint()
        except Exception:
            log.exception("final checkpoint failed")


app = FastAPI(title="Town Game API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get(
        "SANDBOX_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()],   # §3.11 B 小修 ④
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
app.include_router(ws.router)
app.include_router(scenario.router)
app.include_router(qq.router)                    # W10 ③
app.include_router(door.router)                  # §3.40
