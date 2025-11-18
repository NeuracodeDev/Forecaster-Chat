from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .input_schemas import RequestMeta


class SeriesForecastQuantiles(BaseModel):
    """Stores quantile forecasts for a single series."""

    quantile_levels: List[float]
    values: Dict[str, List[List[float]]]  # quantile -> [variates][horizon]


class SeriesForecastResult(BaseModel):
    """Response payload for a single time series."""

    series_id: str
    frequency: Optional[str] = None
    context_summary: Optional[str] = Field(
        default=None, description="Short description of what was forecast and relevant covariates."
    )
    forecast_timestamps: Optional[List[str]] = None
    point_forecast: List[List[float]] = Field(description="Shape: [n_variates][horizon]")
    quantiles: SeriesForecastQuantiles
    units: Optional[str] = None
    scale_factor: Optional[float] = None
    dropped_covariates: Optional[List[str]] = None
    device: str
    horizon: int
    metadata: Optional[Dict[str, str | int | float | List[str]]] = None


class ChronosForecastResponse(BaseModel):
    """Top-level response returned by the Chronos service."""

    schema_version: str = Field(default="1.0")
    request_meta: Optional[RequestMeta] = None
    quantile_levels: List[float]
    series: List[SeriesForecastResult]
    warnings: Optional[List[str]] = None
    engine_info: Dict[str, str]

