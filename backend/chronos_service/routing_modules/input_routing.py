from __future__ import annotations

from fastapi import APIRouter, Query

from chronos_service.api_modules.output_api import run_forecast
from chronos_service.schema_modules.input_schemas import ChronosForecastPayload
from chronos_service.schema_modules.response_schemas import ChronosForecastResponse

router = APIRouter(prefix="/chronos", tags=["chronos"])


@router.post("/forecast", response_model=ChronosForecastResponse)
def forecast_endpoint(
    payload: ChronosForecastPayload,
    batch_size: int = Query(default=128, ge=1, description="Maximum number of series per inference batch."),
) -> ChronosForecastResponse:
    """
    Accept a canonical Chronos payload, execute inference, and return structured forecasts.
    """

    return run_forecast(payload, batch_size=batch_size)

