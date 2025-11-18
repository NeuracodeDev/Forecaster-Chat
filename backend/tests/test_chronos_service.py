from __future__ import annotations

import sys
import numpy as np
import pandas as pd

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from chronos_service import assemble_payload  # noqa: E402
from chronos_service.api_modules.output_api import run_forecast  # noqa: E402
from chronos_service.logic_modules.aggregation import DEFAULT_CONFIDENCE  # noqa: E402
from chronos_service.logic_modules.preprocessing import prepare_payload  # noqa: E402
from chronos_service.schema_modules.input_schemas import (  # noqa: E402
    ChronosGlobalContext,
    ChronosTargetConfig,
    SeriesFragment,
)


def run_end_to_end_inference() -> dict:
    """
    Full pipeline test:
    fragments -> canonical payload -> preprocessing -> Chronos inference -> response assembly.
    """

    history_length = 120
    multivariate_length = 90
    prediction_horizon = 5

    history_index = pd.date_range(start="2024-01-01", periods=history_length, freq="D")
    mv_history_index = pd.date_range(start="2024-02-01", periods=multivariate_length, freq="D")

    target_values = (np.linspace(100, 130, history_length)).tolist()
    temperature_values = (15 + 10 * np.sin(np.linspace(0, 3, history_length))).tolist()
    multivariate_values = [
        (50 + 5 * np.sin(np.linspace(0, 2, multivariate_length))).tolist(),
        (75 + 3 * np.cos(np.linspace(0, 4, multivariate_length))).tolist(),
    ]

    print("=== Fragment generation ===")
    print(f"Univariate history length: {history_length}")
    print(f"Multivariate history length: {multivariate_length}")
    print(f"Prediction horizon: {prediction_horizon}")

    fragment_json = [
        {
            "chunk_id": "chunk-target",
            "series_id": "synthetic:series",
            "summary": "Synthetic demand with seasonal trend and temperature covariate.",
            "frequency": "1d",
            "target": {
                "values": [target_values],
                "timestamps": [ts.isoformat() for ts in history_index],
                "units": "units",
            },
            "past_covariates": {
                "temperature": {"values": temperature_values, "units": "celsius"},
                "price_index": {"values": (np.linspace(1.0, 1.5, history_length)).tolist()},
                "promotion_flag": {"values": ([0] * history_length)},
            },
            "confidence": 0.9,
        },
        {
            "chunk_id": "chunk-future",
            "series_id": "synthetic:series",
            "future_covariates": {
                "promotion_flag": {"values": [0, 1, 0, 0, 1]},
            },
            "issues": ["Derived future promotion schedule from marketing calendar."],
            "confidence": 0.6,
        },
        {
            "chunk_id": "mv-chunk-target",
            "series_id": "synthetic:multivariate",
            "summary": "Two-variate energy consumption with macro drivers.",
            "frequency": "1d",
            "target": {
                "values": multivariate_values,
                "timestamps": [ts.isoformat() for ts in mv_history_index],
                "units": "megawatts",
            },
            "past_covariates": {
                "holiday": {
                    "values": ([0, 1] * (multivariate_length // 2 + 1))[:multivariate_length]
                },
                "macro_index": {"values": (np.linspace(0.5, 0.9, multivariate_length)).tolist()},
                "temperature_forecast": {"values": (20 + 2 * np.sin(np.linspace(0, 2, multivariate_length))).tolist()},
                "event_index": {"values": ([0] * multivariate_length)},
            },
            "confidence": 0.85,
        },
        {
            "chunk_id": "mv-chunk-future",
            "series_id": "synthetic:multivariate",
            "future_covariates": {
                "temperature_forecast": {"values": [21.5, 22.0, 22.3, 22.7, 23.0]},
                "event_index": {"values": [0, 0, 1, 0, 0]},
            },
            "confidence": 0.7,
        },
    ]

    fragments = [SeriesFragment.model_validate(fragment) for fragment in fragment_json]

    target_config = ChronosTargetConfig(
        context_budget=8192,
        prediction_budget=128,
        input_patch_size=32,
        quantile_set=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
        allowed_frequencies=["1d"],
        max_covariates=24,
        frequency_guidelines="Use daily cadence; resample irregular data to 1d.",
    )
    global_context = ChronosGlobalContext(
        prediction_horizon=prediction_horizon,
        context_strategy="truncate_latest",
        frequency_policy="resample_to_allowed",
        validation_reports=[],
    )

    print("=== Aggregating fragments ===")

    payload = assemble_payload(
        chronos_target=target_config,
        global_context=global_context,
        fragments=fragments,
        request_meta=None,
        default_confidence=DEFAULT_CONFIDENCE,
    )

    assert len(payload.series_catalog) == 2
    assert payload.series_catalog[0].summary == fragments[0].summary

    prepared_batch = prepare_payload(payload)
    assert prepared_batch.prediction_length == prediction_horizon
    assert prepared_batch.series_metadata[0].summary == fragments[0].summary
    assert len(prepared_batch.series_metadata) == 2

    print("=== Prepared batch metadata ===")
    for meta in prepared_batch.series_metadata:
        print(
            f"Series: {meta.series_id} | freq={meta.frequency} | history={meta.history_length} "
            f"| horizon={meta.horizon} | summary={meta.summary}"
        )

    print("=== Running Chronos inference ===")
    response = run_forecast(payload, batch_size=16)

    print("=== Forecast response summary ===")
    print(f"Quantiles: {response.quantile_levels}")
    print(f"Warnings: {response.warnings}")
    print(f"Engine info: {response.engine_info}")
    print(f"Series count: {len(response.series)}")

    assert len(response.series) == 2, "Expected forecasts for both univariate and multivariate series."

    univariate_result = next(series for series in response.series if series.series_id == "synthetic:series")
    multivariate_result = next(series for series in response.series if series.series_id == "synthetic:multivariate")

    print("=== Univariate forecast detail ===")
    print(f"Context summary: {univariate_result.context_summary}")
    print(f"Point forecast: {univariate_result.point_forecast}")
    print(f"Quantile keys: {list(univariate_result.quantiles.values.keys())[:5]} ...")

    assert len(univariate_result.point_forecast) == 1
    assert len(univariate_result.point_forecast[0]) == prediction_horizon
    assert len(univariate_result.quantiles.quantile_levels) == len(target_config.quantile_set)
    assert univariate_result.context_summary == fragments[0].summary

    print("=== Multivariate forecast detail ===")
    print(f"Context summary: {multivariate_result.context_summary}")
    print(f"Point forecast variates: {len(multivariate_result.point_forecast)}")
    print(f"First variate forecast: {multivariate_result.point_forecast[0]}")

    assert len(multivariate_result.point_forecast) == 2
    assert all(len(var) == prediction_horizon for var in multivariate_result.point_forecast)
    assert multivariate_result.context_summary == fragments[2].summary

    assert response.engine_info["model_name"] == target_config.model_name
    assert response.engine_info["device"] in {"cpu", "cuda", "mps"}

    return response.model_dump()


if __name__ == "__main__":
    result = run_end_to_end_inference()
    preview = json.dumps(result, indent=2)
    print(preview[:2000] + ("..." if len(preview) > 2000 else ""))
    print("Chronos end-to-end inference completed successfully.")
