from __future__ import annotations

from chronos_service.api_modules.input_api import prepare_batch
from chronos_service.logic_modules.inference import ChronosEngine
from chronos_service.logic_modules.response_structure import build_forecast_response
from chronos_service.schema_modules.input_schemas import ChronosForecastPayload
from chronos_service.schema_modules.response_schemas import ChronosForecastResponse

__all__ = ["run_forecast"]


def run_forecast(payload: ChronosForecastPayload, *, batch_size: int = 128) -> ChronosForecastResponse:
    """
    High-level orchestration entrypoint:
    1. Normalise payload into Chronos tensors.
    2. Execute Chronos2 inference.
    3. Assemble the structured forecast response.
    """

    prepared_batch = prepare_batch(payload)
    engine = ChronosEngine.instance()
    forecast_result = engine.forecast(prepared_batch, batch_size=batch_size)
    return build_forecast_response(payload, prepared_batch, forecast_result)

