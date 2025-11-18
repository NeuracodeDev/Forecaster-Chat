from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db import Base


class ForecastStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ForecastJob(Base):
    __tablename__ = "forecast_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    trigger_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    response_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    fragment_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    chronos_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[ForecastStatus] = mapped_column(
        SqlEnum(ForecastStatus), default=ForecastStatus.PENDING, nullable=False
    )
    requested_horizon: Mapped[int | None] = mapped_column(Integer, nullable=True)
    device: Mapped[str | None] = mapped_column(String(32), nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    series: Mapped[list["ForecastSeries"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class ForecastSeries(Base):
    __tablename__ = "forecast_series"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("forecast_jobs.id", ondelete="CASCADE"), nullable=False
    )
    series_id: Mapped[str] = mapped_column(String(255), nullable=False)
    frequency: Mapped[str | None] = mapped_column(String(32), nullable=True)
    context_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    point_forecast: Mapped[dict] = mapped_column(JSONB, nullable=False)
    quantiles: Mapped[dict] = mapped_column(JSONB, nullable=False)
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    job: Mapped["ForecastJob"] = relationship(back_populates="series")


__all__ = ["ForecastJob", "ForecastSeries", "ForecastStatus"]

