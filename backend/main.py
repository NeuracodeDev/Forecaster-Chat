import logging
from typing import Iterable

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chronos_service import engine_router, forecast_router
from llm_service.routing_modules import chat_router as llm_chat_router

API_PREFIX = "/api/v1"
HEALTH_ROUTE = "/health"
FRONTEND_ORIGINS: Iterable[str] = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


api_router = APIRouter(prefix=API_PREFIX, tags=["core"])


@api_router.get(HEALTH_ROUTE, summary="Application health probe")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


def configure_cors(app: FastAPI, *, origins: Iterable[str]) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def register_routers(app: FastAPI) -> None:
    app.include_router(api_router)
    app.include_router(forecast_router, prefix=API_PREFIX)
    app.include_router(engine_router, prefix=API_PREFIX)
    app.include_router(llm_chat_router, prefix=API_PREFIX)


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="Forecaster API", version="0.1.0")
    configure_cors(app, origins=FRONTEND_ORIGINS)
    register_routers(app)
    return app


app = create_app()
