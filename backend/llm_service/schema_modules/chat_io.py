from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MessageDTO(BaseModel):
    id: UUID
    role: str = Field(description="Message role: user, assistant, or tool.")
    content: Optional[str] = None
    raw_payload: Optional[dict] = None
    sequence_index: int
    created_at: datetime


class UploadArtifactDTO(BaseModel):
    id: UUID
    session_id: UUID
    message_id: Optional[UUID] = None
    original_filename: str
    stored_path: str
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    extraction_status: str
    extraction_result: Optional[dict] = None
    created_at: datetime


class ChatTurnResponse(BaseModel):
    session_id: UUID
    session_title: Optional[str] = None
    created_new_session: bool
    user_message: MessageDTO
    assistant_message: MessageDTO
    tool_messages: List[MessageDTO]
    uploads: List[UploadArtifactDTO]
    forecast_job_id: Optional[UUID] = None
    chronos_response: Optional[dict] = None


class SessionSummaryDTO(BaseModel):
    id: UUID
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_message_at: Optional[datetime] = None
    message_count: int


class SessionDetailResponse(BaseModel):
    session_id: UUID
    session_title: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    messages: List[MessageDTO]
    uploads: List[UploadArtifactDTO]

