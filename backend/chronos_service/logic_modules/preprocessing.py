from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from chronos_service.schema_modules.input_schemas import (
    ChronosForecastPayload,
    ChronosGlobalContext,
    ChronosTargetConfig,
    CovariateSeries,
    SeriesArray,
    SeriesCatalogEntry,
    SeriesMetadata,
)

import logging

logger = logging.getLogger(__name__)


class PreprocessingError(ValueError):
    """Raised when incoming payloads cannot be normalised for Chronos."""


@dataclass
class PreparedSeriesMetadata:
    series_id: str
    frequency: str | None
    history_timestamps: List[str] | None
    forecast_timestamps: List[str] | None
    units: str | None
    scale_factor: float | None
    dropped_covariates: List[str]
    horizon: int
    history_length: int
    metadata: SeriesMetadata | None
    summary: str | None


@dataclass
class PreparedChronosBatch:
    tasks: List[Dict[str, Any]]
    series_metadata: List[PreparedSeriesMetadata]
    prediction_length: int
    quantile_levels: List[float]


def prepare_payload(payload: ChronosForecastPayload) -> PreparedChronosBatch:
    """
    Normalise a ChronosForecastPayload into Chronos-ready tensors and runtime metadata.
    """

    target_cfg = payload.chronos_target
    global_ctx = payload.global_context
    quantiles = target_cfg.quantile_set

    prepared_tasks: List[Dict[str, Any]] = []
    prepared_metadata: List[PreparedSeriesMetadata] = []

    for entry in payload.series_catalog:
        task, metadata = _prepare_single_series(entry, target_cfg, global_ctx)
        prepared_tasks.append(task)
        prepared_metadata.append(metadata)

    # Use global prediction horizon as default response length (after respecting budgets per series).
    max_horizon = max(meta.horizon for meta in prepared_metadata)

    return PreparedChronosBatch(
        tasks=prepared_tasks,
        series_metadata=prepared_metadata,
        prediction_length=max_horizon,
        quantile_levels=quantiles,
    )


def _prepare_single_series(
    entry: SeriesCatalogEntry,
    target_cfg: ChronosTargetConfig,
    global_ctx: ChronosGlobalContext,
) -> Tuple[Dict[str, Any], PreparedSeriesMetadata]:
    horizon = _resolve_horizon(entry, target_cfg, global_ctx)
    target_array, history_timestamps = _normalise_target(entry.target)
    past_covariates = _normalise_past_covariates(entry, target_array.shape[1])
    future_covariates = _normalise_future_covariates(entry, horizon)

    target_array, history_timestamps, past_covariates = _enforce_context_budget(
        target_array,
        history_timestamps,
        past_covariates,
        target_cfg.context_budget,
        global_ctx.context_strategy,
        entry.frequency,
        entry.series_id,
        global_ctx,
    )

    forecast_timestamps = _generate_future_timestamps(history_timestamps, entry.frequency, horizon)

    task: Dict[str, Any] = {"target": target_array}
    if past_covariates:
        task["past_covariates"] = past_covariates
    if future_covariates:
        task["future_covariates"] = future_covariates

    metadata = PreparedSeriesMetadata(
        series_id=entry.series_id,
        frequency=entry.frequency,
        history_timestamps=history_timestamps,
        forecast_timestamps=forecast_timestamps,
        units=entry.target.units,
        scale_factor=entry.target.scale_factor,
        dropped_covariates=(entry.metadata.dropped_covariates or []) if entry.metadata else [],
        horizon=horizon,
        history_length=target_array.shape[1],
        metadata=entry.metadata,
        summary=entry.summary,
    )

    return task, metadata


def _resolve_horizon(
    entry: SeriesCatalogEntry, target_cfg: ChronosTargetConfig, global_ctx: ChronosGlobalContext
) -> int:
    requested = entry.requested_horizon or global_ctx.prediction_horizon
    horizon = min(requested, target_cfg.prediction_budget)
    if horizon <= 0:
        raise PreprocessingError(f"Invalid prediction horizon for series '{entry.series_id}'.")
    if requested > horizon:
        detail = (
            f"Requested horizon {requested} trimmed to model limit {horizon} "
            f"for series '{entry.series_id}'."
        )
        _append_validation_report(global_ctx, entry.series_id, "horizon_capped", detail)
        logger.info(
            "chronos.horizon_capped",
            extra={"series_id": entry.series_id, "requested": requested, "resolved": horizon},
        )
    if entry.future_covariates:
        for name, covariate in entry.future_covariates.items():
            if len(covariate.values) != horizon:
                raise PreprocessingError(
                    f"Future covariate '{name}' for series '{entry.series_id}' "
                    f"must match resolved horizon ({len(covariate.values)} != {horizon})."
                )
    return horizon


def _normalise_target(target: SeriesArray) -> Tuple[np.ndarray, List[str] | None]:
    target_matrix = np.asarray(target.values, dtype=np.float32)
    history_timestamps = target.timestamps[:] if target.timestamps else None
    return target_matrix, history_timestamps


def _normalise_past_covariates(entry: SeriesCatalogEntry, history_length: int) -> Dict[str, np.ndarray]:
    past_covariates: Dict[str, np.ndarray] = {}
    for name, covariate in (entry.past_covariates or {}).items():
        array = _to_numpy_covariate(covariate)
        if array.shape[-1] != history_length:
            raise PreprocessingError(
                f"Past covariate '{name}' for series '{entry.series_id}' must match "
                f"history length ({array.shape[-1]} != {history_length})."
            )
        past_covariates[name] = array
    return past_covariates


def _normalise_future_covariates(entry: SeriesCatalogEntry, horizon: int) -> Dict[str, np.ndarray]:
    future_covariates: Dict[str, np.ndarray] = {}
    for name, covariate in (entry.future_covariates or {}).items():
        array = _to_numpy_covariate(covariate)
        if array.shape[-1] != horizon:
            raise PreprocessingError(
                f"Future covariate '{name}' for series '{entry.series_id}' must match "
                f"horizon ({array.shape[-1]} != {horizon})."
            )
        future_covariates[name] = array
    return future_covariates


def _enforce_context_budget(
    target_array: np.ndarray,
    history_timestamps: List[str] | None,
    past_covariates: Dict[str, np.ndarray],
    context_budget: int,
    strategy: str,
    frequency: str | None,
    series_id: str,
    global_ctx: ChronosGlobalContext,
) -> Tuple[np.ndarray, List[str] | None, Dict[str, np.ndarray]]:
    if target_array.shape[1] <= context_budget:
        return target_array, history_timestamps, past_covariates

    if strategy != "truncate_latest":
        raise PreprocessingError(f"Unsupported context strategy: {strategy}")

    start_idx = target_array.shape[1] - context_budget
    truncated_target = target_array[:, start_idx:]
    truncated_timestamps = history_timestamps[start_idx:] if history_timestamps else None

    truncated_covariates = {
        name: cov[..., start_idx:] for name, cov in past_covariates.items()
    }

    _validate_frequency_alignment(truncated_timestamps, frequency)
    detail = f"Context truncated from {target_array.shape[1]} to {context_budget} for series '{series_id}'."
    _append_validation_report(global_ctx, series_id, "context_truncated", detail)
    logger.info(
        "chronos.context_truncated",
        extra={"series_id": series_id, "original_length": target_array.shape[1], "budget": context_budget},
    )
    return truncated_target, truncated_timestamps, truncated_covariates


def _generate_future_timestamps(
    history_timestamps: List[str] | None, frequency: str | None, horizon: int
) -> List[str] | None:
    if not history_timestamps or not frequency:
        return None
    last_timestamp = pd.to_datetime(history_timestamps[-1])
    future_index = pd.date_range(start=last_timestamp, periods=horizon + 1, freq=frequency)[1:]
    return future_index.strftime("%Y-%m-%dT%H:%M:%S").tolist()


def _validate_frequency_alignment(timestamps: List[str] | None, frequency: str | None) -> None:
    if not timestamps or not frequency:
        return
    series_index = pd.to_datetime(timestamps)
    inferred = pd.infer_freq(series_index)
    if inferred is None:
        raise PreprocessingError("Unable to infer frequency after truncation.")
    # We do not strictly compare with provided frequency; the validation ensures a consistent cadence.


def _to_numpy_covariate(covariate: CovariateSeries) -> np.ndarray:
    values = covariate.values
    array = np.asarray(values)
    if array.ndim > 2:
        raise PreprocessingError("Covariate arrays cannot exceed 2 dimensions.")
    if array.ndim == 2:
        if array.shape[0] != 1:
            raise PreprocessingError("Covariate arrays must be one-dimensional after normalisation.")
        array = array[0]
    return array


def _append_validation_report(
    global_ctx: ChronosGlobalContext, series_id: str, status: str, detail: str | None = None
) -> None:
    report = {"series_id": series_id, "status": status}
    if detail:
        report["detail"] = detail
    global_ctx.validation_reports.append(report)

