from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from chronos_service.schema_modules.input_schemas import (
    ChronosForecastPayload,
    ChronosGlobalContext,
    ChronosTargetConfig,
    CovariateCatalogEntry,
    CovariateSeries,
    RequestMeta,
    SeriesArray,
    SeriesCatalogEntry,
    SeriesFragment,
    SeriesMetadata,
)

logger = logging.getLogger(__name__)

DEFAULT_CONFIDENCE = 0.5


class AggregationError(ValueError):
    """Raised when fragment aggregation fails."""


@dataclass
class CovariateCandidate:
    covariate: CovariateSeries
    confidence: float


@dataclass
class AggregatedSeries:
    series_id: str
    frequency: Optional[str] = None
    summary: Optional[str] = None
    target: Optional[SeriesArray] = None
    target_confidence: float = 0.0
    past_covariates: Dict[str, CovariateCandidate] = field(default_factory=dict)
    future_covariates: Dict[str, CovariateCandidate] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)


def assemble_payload(
    *,
    chronos_target: ChronosTargetConfig,
    global_context: ChronosGlobalContext,
    fragments: List[SeriesFragment],
    request_meta: Optional[RequestMeta] = None,
    covariate_catalog: Optional[List[CovariateCatalogEntry]] = None,
    default_confidence: float = DEFAULT_CONFIDENCE,
) -> ChronosForecastPayload:
    """
    Merge a collection of SeriesFragment objects into a canonical ChronosForecastPayload.
    """

    if not fragments:
        raise AggregationError("No fragments provided for aggregation.")

    series_map: Dict[str, AggregatedSeries] = defaultdict(lambda: AggregatedSeries(series_id=""))

    for fragment in fragments:
        confidence = fragment.confidence if fragment.confidence is not None else default_confidence
        series = series_map.get(fragment.series_id)
        if not series or series.series_id == "":
            series = AggregatedSeries(series_id=fragment.series_id)
            series_map[fragment.series_id] = series

        if fragment.frequency:
            if series.frequency and series.frequency != fragment.frequency:
                msg = (
                    f"Conflicting frequency '{fragment.frequency}' for series '{fragment.series_id}'. "
                    f"Keeping '{series.frequency}'."
                )
                logger.warning("chronos.fragment.frequency_conflict", extra={"series_id": fragment.series_id})
                series.issues.append(msg)
                _append_validation_report(
                    global_context,
                    fragment.series_id,
                    "frequency_conflict",
                    msg,
                )
            else:
                series.frequency = fragment.frequency

        if fragment.target:
            if confidence >= series.target_confidence:
                series.target = fragment.target
                series.target_confidence = confidence
        if fragment.summary and (series.summary is None or confidence >= series.target_confidence):
            series.summary = fragment.summary
        elif series.summary is None and fragment.issues:
            series.summary = fragment.issues[0]

        if fragment.past_covariates:
            for name, cov in fragment.past_covariates.items():
                _merge_covariate(series.past_covariates, name, cov, confidence)

        if fragment.future_covariates:
            for name, cov in fragment.future_covariates.items():
                _merge_covariate(series.future_covariates, name, cov, confidence)

        if fragment.issues:
            series.issues.extend(fragment.issues)

    series_catalog: List[SeriesCatalogEntry] = []
    for series_id, aggregated in series_map.items():
        if aggregated.target is None:
            raise AggregationError(f"Series '{series_id}' is missing target values after aggregation.")

        _enforce_covariate_cap(
            aggregated,
            chronos_target.max_covariates,
            global_context,
        )

        metadata = SeriesMetadata(notes=aggregated.issues or None)

        series_catalog.append(
            SeriesCatalogEntry(
                series_id=series_id,
                display_name=None,
                summary=aggregated.summary,
                frequency=aggregated.frequency,
                target=aggregated.target,
                past_covariates={name: candidate.covariate for name, candidate in aggregated.past_covariates.items()}
                or None,
                future_covariates={name: candidate.covariate for name, candidate in aggregated.future_covariates.items()}
                or None,
                metadata=metadata if metadata.notes else None,
            )
        )

    payload = ChronosForecastPayload(
        chronos_target=chronos_target,
        global_context=global_context,
        series_catalog=series_catalog,
        covariate_catalog=covariate_catalog,
        request_meta=request_meta,
    )

    logger.info(
        "chronos.fragments.aggregated",
        extra={"num_series": len(series_catalog), "num_fragments": len(fragments)},
    )

    return payload


def _merge_covariate(
    container: Dict[str, CovariateCandidate],
    name: str,
    covariate: CovariateSeries,
    confidence: float,
) -> None:
    existing = container.get(name)
    if not existing or confidence >= existing.confidence:
        container[name] = CovariateCandidate(covariate=covariate, confidence=confidence)


def _enforce_covariate_cap(
    series: AggregatedSeries,
    max_covariates: int,
    global_context: ChronosGlobalContext,
) -> None:
    total = len(series.past_covariates) + len(series.future_covariates)
    if total <= max_covariates:
        return

    candidates: List[Tuple[str, str, float]] = []
    for name, candidate in series.past_covariates.items():
        candidates.append(("past", name, candidate.confidence))
    for name, candidate in series.future_covariates.items():
        candidates.append(("future", name, candidate.confidence))

    candidates.sort(key=lambda item: item[2])

    while len(series.past_covariates) + len(series.future_covariates) > max_covariates and candidates:
        scope, name, _ = candidates.pop(0)
        if scope == "past" and name in series.past_covariates:
            del series.past_covariates[name]
        elif scope == "future" and name in series.future_covariates:
            del series.future_covariates[name]
        msg = f"Dropped covariate '{name}' to respect max_covariates={max_covariates}."
        logger.warning("chronos.covariate.dropped", extra={"series_id": series.series_id, "covariate": name})
        series.issues.append(msg)
        _append_validation_report(global_context, series.series_id, "covariate_dropped", msg)


def _append_validation_report(
    global_context: ChronosGlobalContext, series_id: str, status: str, detail: Optional[str] = None
) -> None:
    report = {"series_id": series_id, "status": status}
    if detail:
        report["detail"] = detail
    global_context.validation_reports.append(report)

