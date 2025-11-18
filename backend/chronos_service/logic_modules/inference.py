from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import List, Sequence

import numpy as np
import torch
from chronos import Chronos2Pipeline

from chronos_service.logic_modules.preprocessing import PreparedChronosBatch

import logging

logger = logging.getLogger(__name__)


def _detect_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@dataclass
class ForecastSeriesOutput:
    quantiles: np.ndarray  # Shape: (n_variates, horizon, n_quantiles)
    point_forecast: np.ndarray  # Shape: (n_variates, horizon)


@dataclass
class ForecastResult:
    series_outputs: List[ForecastSeriesOutput]
    quantile_levels: Sequence[float]
    device: str


class ChronosEngine:
    """Lightweight singleton wrapper around Chronos2Pipeline."""

    _instance: "ChronosEngine | None" = None
    _lock = threading.Lock()

    def __init__(self, model_name: str = "amazon/chronos-2", device: str | None = None):
        self.model_name = model_name
        self.device = device or _detect_device()
        self._pipeline: Chronos2Pipeline | None = None
        self._pipeline_lock = threading.Lock()

    @classmethod
    def instance(cls) -> "ChronosEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = ChronosEngine()
        return cls._instance

    def _ensure_pipeline(self) -> Chronos2Pipeline:
        if self._pipeline is not None:
            return self._pipeline
        with self._pipeline_lock:
            if self._pipeline is None:
                pipeline = Chronos2Pipeline.from_pretrained(self.model_name)
                pipeline.model.to(self.device)
                self._pipeline = pipeline
                logger.info(
                    "chronos.pipeline.initialised",
                    extra={"model_name": self.model_name, "device": self.device},
                )
        return self._pipeline

    def forecast(self, batch: PreparedChronosBatch, batch_size: int = 128) -> ForecastResult:
        pipeline = self._ensure_pipeline()
        logger.info(
            "chronos.forecast.start",
            extra={
                "num_series": len(batch.tasks),
                "prediction_length": batch.prediction_length,
                "batch_size": batch_size,
                "device": self.device,
            },
        )
        quantiles, means = pipeline.predict_quantiles(
            inputs=batch.tasks,
            prediction_length=batch.prediction_length,
            quantile_levels=list(batch.quantile_levels),
            limit_prediction_length=False,
            batch_size=batch_size,
        )

        outputs: List[ForecastSeriesOutput] = []
        for quantile_tensor, mean_tensor in zip(quantiles, means):
            q_array = quantile_tensor.detach().cpu().numpy()
            mean_array = mean_tensor.detach().cpu().numpy()
            outputs.append(ForecastSeriesOutput(quantiles=q_array, point_forecast=mean_array))

        logger.info(
            "chronos.forecast.complete",
            extra={"num_series": len(outputs), "device": self.device},
        )

        return ForecastResult(
            series_outputs=outputs,
            quantile_levels=batch.quantile_levels,
            device=self.device,
        )

