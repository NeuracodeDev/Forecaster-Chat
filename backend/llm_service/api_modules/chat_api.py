from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import List, Sequence
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_session
from chronos_service.models_modules import ForecastJob
from llm_service.logic_modules.open_ai_client import OpenAIResponsesClient
from llm_service.logic_modules.title_generator import generate_chat_title
from llm_service.models_modules.sessions import (
    ConversationSession,
    Message,
    MessageRole,
    UploadArtifact,
)
from llm_service.orchestrator.file_processor import STORAGE_ROOT
from llm_service.orchestrator.pipeline import ForecastPipeline
from llm_service.schema_modules import (
    ChatTurnResponse,
    MessageDTO,
    SessionDetailResponse,
    SessionSummaryDTO,
    UploadArtifactDTO,
)

router = APIRouter(prefix="/chat", tags=["chat"])
pipeline = ForecastPipeline()
logger = logging.getLogger(__name__)


@router.post("/message", response_model=ChatTurnResponse, status_code=status.HTTP_201_CREATED)
async def submit_message(
    session_id: UUID | None = Form(default=None),
    content: str | None = Form(default=None),
    files: List[UploadFile] | None = File(default=None),
    db: AsyncSession = Depends(get_session),
) -> ChatTurnResponse:
    logger.info(
        "chat_api.submit_message.start",
        extra={
            "session_id": str(session_id) if session_id else None,
            "has_files": bool(files),
            "file_count": len(files or []),
            "has_content": bool(content),
        },
    )
    files = files or []
    if not content and not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide content or at least one file.")

    if session_id:
        session = await db.get(ConversationSession, session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found.")
        created_new_session = False
    else:
        session = ConversationSession()
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
    logger.info(
        "chat_api.uploads.stored",
        extra={"session_id": str(session.id), "message_id": str(user_message.id), "upload_count": len(uploads)},
    )

    if created_new_session:
        await _ensure_session_title(db, session, content=content, files=files)

    logger.info(
        "chat_api.pipeline.run.start",
        extra={"session_id": str(session.id), "message_id": str(user_message.id), "upload_count": len(uploads)},
    )
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
        session_title=session.title,
        created_new_session=created_new_session,
        user_message=_serialize_message(user_message),
        assistant_message=_serialize_message(assistant),
        tool_messages=[_serialize_message(msg) for msg in tool_messages],
        uploads=[_serialize_upload(artifact) for artifact in uploads],
        forecast_job_id=UUID(forecast_job_id) if forecast_job_id else None,
        chronos_response=chronos_response,
    )

    logger.info(
        "chat_api.submit_message.completed",
        extra={
            "session_id": str(session.id),
            "user_message_id": str(user_message.id),
            "assistant_message_id": str(assistant.id),
            "tool_count": len(tool_messages),
            "upload_count": len(uploads),
            "forecast_job_id": result.get("forecast_job_id"),
        },
    )

    return response


@router.get("/sessions", response_model=List[SessionSummaryDTO], status_code=status.HTTP_200_OK)
async def list_sessions(
    db: AsyncSession = Depends(get_session),
) -> List[SessionSummaryDTO]:
    last_activity = func.coalesce(func.max(Message.created_at), ConversationSession.updated_at)
    stmt = (
        select(
            ConversationSession.id,
            ConversationSession.title,
            ConversationSession.created_at,
            ConversationSession.updated_at,
            func.count(Message.id).label("message_count"),
            func.max(Message.created_at).label("last_message_at"),
        )
        .outerjoin(Message, Message.session_id == ConversationSession.id)
        .group_by(ConversationSession.id)
        .order_by(last_activity.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()
    summaries: List[SessionSummaryDTO] = []
    for row in rows:
        summaries.append(
            SessionSummaryDTO(
                id=row.id,
                title=row.title,
                created_at=row.created_at,
                updated_at=row.updated_at,
                last_message_at=row.last_message_at,
                message_count=row.message_count,
            )
        )
    return summaries


@router.get("/session/{session_id}", response_model=SessionDetailResponse, status_code=status.HTTP_200_OK)
async def get_session_detail(
    session_id: UUID,
    db: AsyncSession = Depends(get_session),
) -> SessionDetailResponse:
    session = await db.get(ConversationSession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found.")

    messages_result = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.sequence_index)
    )
    uploads_result = await db.execute(select(UploadArtifact).where(UploadArtifact.session_id == session_id))

    messages = [_serialize_message(message) for message in messages_result.scalars().all()]
    uploads = [_serialize_upload(upload) for upload in uploads_result.scalars().all()]

    return SessionDetailResponse(
        session_id=session.id,
        session_title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=messages,
        uploads=uploads,
    )


@router.delete("/session/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_session),
) -> None:
    session = await db.get(ConversationSession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation session not found.")

    logger.info("chat_api.delete_session.start", extra={"session_id": str(session_id)})

    await db.execute(delete(ForecastJob).where(ForecastJob.session_id == session_id))
    await db.delete(session)
    await db.commit()

    storage_dir = STORAGE_ROOT / str(session_id)
    if storage_dir.exists():
        shutil.rmtree(storage_dir, ignore_errors=True)

    logger.info("chat_api.delete_session.completed", extra={"session_id": str(session_id)})


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


async def _ensure_session_title(
    db: AsyncSession,
    session: ConversationSession,
    *,
    content: str | None,
    files: Sequence[UploadFile],
) -> None:
    if session.title:
        return

    title_context = _compose_title_context(content, files)
    if title_context:
        async with OpenAIResponsesClient() as client:
            session.title = await generate_chat_title(
                client=client,
                first_user_message=title_context,
            )
        db.add(session)
        await db.flush()
        return

    fallback = _derive_upload_title(files)
    if fallback:
        session.title = fallback
        db.add(session)
        await db.flush()


def _derive_upload_title(files: Sequence[UploadFile]) -> str | None:
    for upload in files:
        filename = Path(upload.filename or "").stem
        if filename:
            return filename[:120]
    return None


def _compose_title_context(content: str | None, files: Sequence[UploadFile]) -> str:
    parts: List[str] = []
    stripped = (content or "").strip()
    if stripped:
        parts.append(stripped)
    if files:
        file_list = ", ".join(Path(upload.filename or "upload").stem for upload in files[:5])
        parts.append(f"Files: {file_list}")
    return "\n".join(parts).strip()


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

