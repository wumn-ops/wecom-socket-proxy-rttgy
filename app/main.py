import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.feedback_routes import router as feedback_router
from app.register_daily_routes import router as register_daily_router
from app.routes import router
from app.upload_routes import router as upload_router
from app.ws_service import WebSocketBotService

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

bot_service = WebSocketBotService(settings)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await bot_service.start()
    yield
    await bot_service.stop()


app = FastAPI(
    title="wecom-socket-proxy-rttgy",
    description="企业微信智能机器人 WebSocket 长连接代理",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.bot_service = bot_service
app.include_router(router)
app.include_router(upload_router)
app.include_router(feedback_router)
app.include_router(register_daily_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "wecom-socket-proxy-rttgy",
        "mode": "websocket",
        "health": settings.health_path,
        "callback_placeholder": settings.wecom_callback_path,
        "register_upload": settings.register_upload_path,
        "register_daily": settings.register_daily_path,
        "feedback": settings.feedback_path,
    }
