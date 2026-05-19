from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import world, player, actions, events, history, time_control, agent

app = FastAPI(title="Town Game API")

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
