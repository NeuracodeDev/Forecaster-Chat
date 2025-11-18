from __future__ import annotations

from chronos_service.logic_modules.inference import ChronosEngine
from .forecast import ForecastJob, ForecastSeries, ForecastStatus

__all__ = ["get_engine", "ForecastJob", "ForecastSeries", "ForecastStatus"]


def get_engine() -> ChronosEngine:
    """Return the shared ChronosEngine instance."""

    return ChronosEngine.instance()

