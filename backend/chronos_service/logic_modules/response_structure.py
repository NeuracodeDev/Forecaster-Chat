from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np

from chronos_service.logic_modules.inference import ForecastResult
from chronos_service.logic_modules.preprocessing import PreparedChronosBatch
from chronos_service.schema_modules.input_schemas import ChronosForecastPayload
from chronos_service.schema_modules.response_schemas import (
    ChronosForecastResponse,
    SeriesForecastQuantiles,
    SeriesForecastResult,
)


def build_forecast_response(
    payload: ChronosForecastPayload, batch: PreparedChronosBatch, result: ForecastResult
) -> ChronosForecastResponse:
    series_results: List[SeriesForecastResult] = []

    for meta, series_output in zip(batch.series_metadata, result.series_outputs):
        quantile_payload = _build_quantile_payload(series_output.quantiles, result.quantile_levels)

        metadata_dict: Dict[str, str | int | float | List[str]] = {}
        if meta.metadata:
            metadata_dict = meta.metadata.model_dump(exclude_none=True)  # type: ignore[assignment]

        series_results.append(
            SeriesForecastResult(
                series_id=meta.series_id,
                frequency=meta.frequency,
                context_summary=meta.summary,
                forecast_timestamps=meta.forecast_timestamps,
                point_forecast=series_output.point_forecast.tolist(),
                quantiles=quantile_payload,
                units=meta.units,
                scale_factor=meta.scale_factor,
                dropped_covariates=meta.dropped_covariates or None,
                device=result.device,
                horizon=meta.horizon,
                metadata=metadata_dict or None,
            )
        )

    warnings = [report for report in payload.global_context.validation_reports]

    return ChronosForecastResponse(
        schema_version=payload.schema_version,
        request_meta=payload.request_meta,
        quantile_levels=list(result.quantile_levels),
        series=series_results,
        warnings=warnings or None,
        engine_info={
            "device": result.device,
            "model_name": payload.chronos_target.model_name,
        },
    )


def _build_quantile_payload(
    quantiles: List[List[List[float]]] | np.ndarray, quantile_levels: Sequence[float]
) -> SeriesForecastQuantiles:
    quantile_array = np.asarray(quantiles)
    quantile_dict = {
        f"{level:.3f}": quantile_array[:, :, idx].tolist()
        for idx, level in enumerate(quantile_levels)
    }
    return SeriesForecastQuantiles(
        quantile_levels=list(quantile_levels),
        values=quantile_dict,
    )

