from __future__ import annotations

from pathlib import Path
from typing import List, Sequence
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_session
from llm_service.models_modules.sessions import (
    ConversationSession,
    Message,
    MessageRole,
    UploadArtifact,
)
from llm_service.orchestrator.file_processor import STORAGE_ROOT
from llm_service.orchestrator.pipeline import ForecastPipeline
from llm_service.schema_modules import ChatTurnResponse, MessageDTO, UploadArtifactDTO

router = APIRouter(prefix="/chat", tags=["chat"])
pipeline = ForecastPipeline()


@router.post("/message", response_model=ChatTurnResponse, status_code=status.HTTP_201_CREATED)
async def submit_message(
    session_id: UUID | None = Form(default=None),
    content: str | None = Form(default=None),
    files: List[UploadFile] | None = File(default=None),
    db: AsyncSession = Depends(get_session),
) -> ChatTurnResponse:
    files = files or []
    if not content and not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide content or at least one file.")

    if session_id:
        session = await db.get(ConversationSession, session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found.")
        created_new_session = False
    else:
        title = _derive_session_title(content, files)
        session = ConversationSession(title=title)
        db.add(session)
        await db.flush()
        created_new_session = True

    user_message = await pipeline._create_message(  # pylint: disable=protected-access
        db,
        session_id=session.id,
        role=MessageRole.USER,
        content=content,
        raw_payload=None,
    )

    uploads = await _store_uploads(db, session.id, user_message.id, files)

    result = await pipeline.run(db, session, user_message, uploads)

    assistant = await _get_message(db, result["assistant_message_id"])

    tool_messages: List[Message] = []
    if "tool_message_id" in result:
        tool_messages.append(await _get_message(db, result["tool_message_id"]))
    if "raw_tool_message_id" in result:
        tool_messages.append(await _get_message(db, result["raw_tool_message_id"]))

    chronos_response = None
    forecast_job_id = result.get("forecast_job_id")
    for message in tool_messages:
        payload = message.raw_payload or {}
        if chronos_response is None:
            chronos_response = payload.get("chronos_response")

    for upload in uploads:
        await db.refresh(upload)

    response = ChatTurnResponse(
        session_id=session.id,
        created_new_session=created_new_session,
        user_message=_serialize_message(user_message),
        assistant_message=_serialize_message(assistant),
        tool_messages=[_serialize_message(msg) for msg in tool_messages],
        uploads=[_serialize_upload(artifact) for artifact in uploads],
        forecast_job_id=UUID(forecast_job_id) if forecast_job_id else None,
        chronos_response=chronos_response,
    )

    return response


async def _store_uploads(
    db: AsyncSession,
    session_id: UUID,
    message_id: UUID,
    files: Sequence[UploadFile],
) -> List[UploadArtifact]:
    uploads: List[UploadArtifact] = []
    if not files:
        return uploads

    root = STORAGE_ROOT / str(session_id)
    root.mkdir(parents=True, exist_ok=True)

    for upload in files:
        filename = Path(upload.filename or "upload.bin").name
        target_path = root / f"{uuid4()}_{filename}"
        size_bytes = await _write_file(upload, target_path)
        relative_path = target_path.relative_to(STORAGE_ROOT).as_posix()

        artifact = UploadArtifact(
            session_id=session_id,
            message_id=message_id,
            original_filename=filename,
            stored_path=relative_path,
            mime_type=upload.content_type,
            size_bytes=size_bytes,
        )
        db.add(artifact)
        uploads.append(artifact)

    await db.flush()
    return uploads


async def _write_file(upload: UploadFile, destination: Path) -> int:
    with destination.open("wb") as buffer:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            buffer.write(chunk)
    await upload.close()
    return destination.stat().st_size


def _derive_session_title(content: str | None, files: Sequence[UploadFile]) -> str | None:
    if content:
        stripped = content.strip()
        if stripped:
            return stripped[:120]
    if files:
        filename = Path(files[0].filename or "Upload").stem
        return filename[:120]
    return None


async def _get_message(db: AsyncSession, message_id: str | UUID) -> Message:
    identifier = UUID(str(message_id))
    message = await db.get(Message, identifier)
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found after processing.")
    return message


def _serialize_message(message: Message) -> MessageDTO:
    return MessageDTO(
        id=message.id,
        role=message.role.value,
        content=message.content,
        raw_payload=message.raw_payload,
        sequence_index=message.sequence_index,
        created_at=message.created_at,
    )


def _serialize_upload(artifact: UploadArtifact) -> UploadArtifactDTO:
    return UploadArtifactDTO(
        id=artifact.id,
        session_id=artifact.session_id,
        message_id=artifact.message_id,
        original_filename=artifact.original_filename,
        stored_path=artifact.stored_path,
        mime_type=artifact.mime_type,
        size_bytes=artifact.size_bytes,
        extraction_status=artifact.extraction_status.value,
        extraction_result=artifact.extraction_result,
        created_at=artifact.created_at,
    )

