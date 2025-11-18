from __future__ import annotations

from fastapi import APIRouter

from llm_service.api_modules import chat_router

router = APIRouter()
router.include_router(chat_router)

__all__ = ["router"]

