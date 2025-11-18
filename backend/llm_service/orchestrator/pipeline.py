from __future__ import annotations

import asyncio
from datetime import datetime
from typing import List, Sequence
import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from chronos_service.api_modules.output_api import run_forecast
from chronos_service.logic_modules.aggregation import DEFAULT_CONFIDENCE, assemble_payload
from chronos_service.models_modules import ForecastJob, ForecastSeries, ForecastStatus
from chronos_service.schema_modules.input_schemas import (
    ChronosForecastPayload,
    ChronosGlobalContext,
    ChronosTargetConfig,
    RequestMeta,
    SeriesFragment,
)
from chronos_service.schema_modules.response_schemas import ChronosForecastResponse
from llm_service.logic_modules.chat_prompt import (
    ForecastDigest,
    build_chat_messages,
    render_digest,
    render_digest_json,
)
from llm_service.logic_modules.open_ai_client import OpenAIResponsesClient
from llm_service.models_modules.sessions import (
    ConversationSession,
    ExtractionStatus,
    Message,
    MessageRole,
    UploadArtifact,
)
from llm_service.orchestrator.file_processor import ChunkDescriptor, process_upload_artifact
from llm_service.orchestrator.normalizer import NormalizationResult, normalize_chunks

DEFAULT_TARGET_CONFIG = ChronosTargetConfig(
    context_budget=8192,
    prediction_budget=128,
    input_patch_size=32,
    quantile_set=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
    allowed_frequencies=["1d", "1h", "1wk"],
    max_covariates=24,
    frequency_guidelines="Use daily cadence when uncertain; resample irregular data before inference.",
)

DEFAULT_GLOBAL_CONTEXT = ChronosGlobalContext(
    prediction_horizon=96,
    context_strategy="truncate_latest",
    frequency_policy="resample_to_allowed",
)


class ForecastPipeline:
    def __init__(self) -> None:
        self.target_config = DEFAULT_TARGET_CONFIG
        self.global_context_template = DEFAULT_GLOBAL_CONTEXT

    async def run(
        self,
        db: AsyncSession,
        session: ConversationSession,
        message: Message,
        uploads: Sequence[UploadArtifact],
    ) -> dict:
        async with OpenAIResponsesClient() as client:
            if not uploads:
                assistant_message = await self._run_chat_only(db, session, message, client)
                await db.commit()
                return {"assistant_message_id": str(assistant_message.id)}

            result = await self._run_with_uploads(db, session, message, uploads, client)
            await db.commit()
            return result

    async def _run_chat_only(
        self,
        db: AsyncSession,
        session: ConversationSession,
        message: Message,
        client: OpenAIResponsesClient,
    ) -> Message:
        history = await self._load_history(db, session.id)
        messages_payload = build_chat_messages(history=history)
        assistant_text = await client.create_text(messages_payload)

        assistant_message = await self._create_message(
            db,
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            content=assistant_text,
            raw_payload=None,
        )
        return assistant_message

    async def _run_with_uploads(
        self,
        db: AsyncSession,
        session: ConversationSession,
        message: Message,
        uploads: Sequence[UploadArtifact],
        client: OpenAIResponsesClient,
    ) -> dict:
        chunk_descriptors: List[ChunkDescriptor] = []
        for upload in uploads:
            chunk_descriptors.extend(process_upload_artifact(upload))

        normalization = await normalize_chunks(client, chunk_descriptors)
        fragments = [
            SeriesFragment.model_validate(fragment) for fragment in normalization.fragments
        ]

        payload = self._build_payload(
            fragments=fragments,
            job_id=str(message.id),
        )

        chronos_response = await asyncio.to_thread(run_forecast, payload, batch_size=16)

        forecast_job = await self._persist_forecast_results(
            db, session.id, message.id, payload, chronos_response
        )

        await self._update_uploads(db, uploads, normalization)

        digest = self._compose_forecast_digest(forecast_job, chronos_response)
        tool_summary = render_digest(digest)
        tool_message = await self._create_message(
            db,
            session_id=session.id,
            role=MessageRole.TOOL,
            content=tool_summary,
            raw_payload={"forecast_job_id": str(forecast_job.id)},
        )
        raw_json_message = await self._create_message(
            db,
            session_id=session.id,
            role=MessageRole.TOOL,
            content=render_digest_json(digest),
            raw_payload={
                "forecast_job_id": str(forecast_job.id),
                "chronos_response": chronos_response.model_dump(),
            },
        )

        assistant_message = await self._generate_assistant_reply(
            db, session, client, forecast_job_id=forecast_job.id
        )

        return {
            "forecast_job_id": str(forecast_job.id),
            "tool_message_id": str(tool_message.id),
            "assistant_message_id": str(assistant_message.id),
            "raw_tool_message_id": str(raw_json_message.id),
        }

    def _build_payload(
        self,
        *,
        fragments: Sequence[SeriesFragment],
        job_id: str,
    ) -> ChronosForecastPayload:
        global_context = ChronosGlobalContext(**self.global_context_template.model_dump())
        request_meta = RequestMeta(job_id=job_id, created_at=datetime.utcnow().isoformat())
        return assemble_payload(
            chronos_target=self.target_config,
            global_context=global_context,
            fragments=list(fragments),
            request_meta=request_meta,
            default_confidence=DEFAULT_CONFIDENCE,
        )

    async def _persist_forecast_results(
        self,
        db: AsyncSession,
        session_id: uuid.UUID,
        trigger_message_id: uuid.UUID,
        payload: ChronosForecastPayload,
        response: ChronosForecastResponse,
    ) -> ForecastJob:
        job = ForecastJob(
            session_id=session_id,
            trigger_message_id=trigger_message_id,
            fragment_payload=payload.model_dump(),
            chronos_response=response.model_dump(),
            status=ForecastStatus.SUCCEEDED,
            requested_horizon=payload.global_context.prediction_horizon,
            device=response.engine_info.get("device"),
            elapsed_ms=None,
            extra={"validation_reports": payload.global_context.validation_reports},
        )
        db.add(job)
        await db.flush()

        for series in response.series:
            forecast_series = ForecastSeries(
                job_id=job.id,
                series_id=series.series_id,
                frequency=series.frequency,
                context_summary=series.context_summary,
                point_forecast=series.point_forecast,
                quantiles={
                    level: values
                    for level, values in series.quantiles.values.items()
                },
                extra={
                    "warnings": response.warnings,
                    "engine_info": response.engine_info,
                },
            )
            db.add(forecast_series)

        return job

    async def _update_uploads(
        self,
        db: AsyncSession,
        uploads: Sequence[UploadArtifact],
        normalization: NormalizationResult,
    ) -> None:
        for upload in uploads:
            report = normalization.upload_reports.get(str(upload.id), {"chunks": [], "issues": []})
            upload.extraction_status = ExtractionStatus.COMPLETE
            upload.extraction_result = report
            db.add(upload)

    async def _generate_assistant_reply(
        self,
        db: AsyncSession,
        session: ConversationSession,
        client: OpenAIResponsesClient,
        *,
        forecast_job_id: uuid.UUID | None = None,
    ) -> Message:
        history = await self._load_history(db, session.id)
        messages_payload = build_chat_messages(history=history)
        assistant_text = await client.create_text(messages_payload)
        assistant_message = await self._create_message(
            db,
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            content=assistant_text,
            raw_payload={"forecast_job_id": str(forecast_job_id)} if forecast_job_id else None,
        )
        return assistant_message

    async def _create_message(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        role: MessageRole,
        content: str | None,
        raw_payload: dict | None,
    ) -> Message:
        sequence_index = await self._next_sequence_index(db, session_id)
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            raw_payload=raw_payload,
            sequence_index=sequence_index,
        )
        db.add(message)
        await db.flush()
        return message

    async def _next_sequence_index(self, db: AsyncSession, session_id: uuid.UUID) -> int:
        result = await db.execute(
            select(func.max(Message.sequence_index)).where(Message.session_id == session_id)
        )
        current = result.scalar()
        return 0 if current is None else current + 1

    async def _load_history(self, db: AsyncSession, session_id: uuid.UUID) -> List[Message]:
        result = await db.execute(
            select(Message).where(Message.session_id == session_id).order_by(Message.sequence_index)
        )
        return list(result.scalars())

    async def _latest_forecast_digest(
        self, db: AsyncSession, session_id: uuid.UUID
    ) -> ForecastDigest | None:
        result = await db.execute(
            select(ForecastJob).where(ForecastJob.session_id == session_id).order_by(ForecastJob.created_at.desc())
        )
        job = result.scalars().first()
        if not job:
            return None
        response = ChronosForecastResponse.model_validate(job.chronos_response)
        return self._compose_forecast_digest(job, response)

    def _compose_forecast_digest(
        self, job: ForecastJob, response: ChronosForecastResponse
    ) -> ForecastDigest:
        summary = (
            f"Forecast job {job.id} completed on device {response.engine_info.get('device', 'unknown')} "
            f"using model {response.engine_info.get('model_name', 'chronos-2')}."
        )
        highlights: List[str] = []
        for series in response.series:
            first_point = _extract_first_point(series.point_forecast)
            highlight = (
                f"{series.series_id}: horizon {series.horizon}, "
                f"median forecast starts at {first_point}"
            )
            highlights.append(highlight)

        warnings = response.warnings or []

        return ForecastDigest(
            job_id=str(job.id),
            summary=summary,
            highlights=highlights,
            warnings=[warning if isinstance(warning, str) else str(warning) for warning in warnings],
            raw_json=response.model_dump_json(),
        )


def _extract_first_point(point_forecast: list) -> str:
    if not point_forecast:
        return "n/a"
    first_row = point_forecast[0]
    if isinstance(first_row, list) and first_row:
        value = first_row[0]
    elif isinstance(first_row, (int, float)):
        value = first_row
    else:
        return "n/a"
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "n/a"

