from __future__ import annotations

from fastapi import APIRouter

from chronos_service.models_modules import get_engine

router = APIRouter(prefix="/chronos", tags=["chronos-meta"])


@router.get("/engine")
def engine_info() -> dict:
    """Return runtime information about the Chronos engine."""

    engine = get_engine()
    return {
        "model_name": engine.model_name,
        "device": engine.device,
    }

