from __future__ import annotations

from chronos_service.logic_modules.preprocessing import PreparedChronosBatch, prepare_payload
from chronos_service.schema_modules.input_schemas import ChronosForecastPayload

__all__ = ["prepare_batch"]


def prepare_batch(payload: ChronosForecastPayload) -> PreparedChronosBatch:
    """Validate and normalise a forecast payload into Chronos-ready tensors."""

    return prepare_payload(payload)

