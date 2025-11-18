from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


Frequency = str


class ChronosTargetConfig(BaseModel):
    """Model-level constraints and preferences for Chronos inference."""

    model_name: str = Field(default="chronos-2")
    context_budget: int = Field(ge=1)
    prediction_budget: int = Field(ge=1)
    input_patch_size: int = Field(ge=1)
    quantile_set: List[float] = Field(min_length=1)
    allowed_frequencies: List[Frequency] = Field(default_factory=list)
    max_covariates: int = Field(ge=0, default=24)
    frequency_guidelines: Optional[str] = None

    @model_validator(mode="after")
    def _validate_quantiles(cls, values: "ChronosTargetConfig") -> "ChronosTargetConfig":
        quantiles = values.quantile_set
        if sorted(quantiles) != quantiles:
            raise ValueError("quantile_set must be sorted in ascending order.")
        if quantiles[0] <= 0.0 or quantiles[-1] >= 1.0:
            raise ValueError("quantile_set must lie strictly within (0, 1).")
        return values


class ChronosGlobalContext(BaseModel):
    """Global inference options shared by all series in a request."""

    prediction_horizon: int = Field(gt=0)
    context_strategy: Literal["truncate_latest"] = "truncate_latest"
    frequency_policy: Literal["resample_to_allowed", "accept_as_is"] = "resample_to_allowed"
    validation_reports: List[Dict[str, str]] = Field(default_factory=list)


class SeriesArray(BaseModel):
    """Represents an ordered collection of values with optional timestamps and units."""

    values: List[List[float] | float]
    timestamps: Optional[List[str]] = None
    source_chunks: Optional[List[str]] = None
    units: Optional[str] = None
    scale_factor: Optional[float] = None
    normalized: Optional[bool] = None

    @model_validator(mode="after")
    def _ensure_structure(cls, values: "SeriesArray") -> "SeriesArray":
        # Allow both flat and nested lists. Convert flat list into list of list for uniformity.
        first_entry = values.values[0] if values.values else None
        if isinstance(first_entry, list):
            # Ensure consistent lengths across variates.
            expected_length = len(first_entry)
            for row in values.values:
                if not isinstance(row, list):
                    raise ValueError("Mixed dimensionality detected in SeriesArray.values.")
                if len(row) != expected_length:
                    raise ValueError("All variates must share the same history length.")
        else:
            # Wrap flat values for downstream processing.
            values.values = [values.values]  # type: ignore[assignment]

        if values.timestamps and len(values.timestamps) != len(values.values[0]):
            raise ValueError("timestamps length must match the history length of values.")
        return values


class CovariateSeries(BaseModel):
    """Represents a covariate aligned with either history or prediction horizon."""

    values: List[float | str | List[float | str]]
    timestamps: Optional[List[str]] = None
    type: Literal["continuous", "categorical"] = "continuous"
    units: Optional[str] = None
    scale_factor: Optional[float] = None

    @model_validator(mode="after")
    def _validate_dimensions(cls, values: "CovariateSeries") -> "CovariateSeries":
        if values.timestamps and len(values.timestamps) != len(values.values):
            raise ValueError("CovariateSeries timestamps must match value length.")
        return values


class SeriesMetadata(BaseModel):
    """Auxiliary metadata describing how the series was prepared."""

    context_length: Optional[int] = None
    downsampling: Optional[Dict[str, str | int | float]] = None
    missing_value_strategy: Optional[str] = None
    confidence: Optional[float] = None
    notes: Optional[List[str]] = None
    dropped_covariates: Optional[List[str]] = None


class SeriesCatalogEntry(BaseModel):
    """Canonical representation of a fully assembled time series ready for inference."""

    series_id: str
    display_name: Optional[str] = None
    summary: Optional[str] = Field(
        default=None,
        description="Short description provided by the LLM summarising targets and covariates.",
        max_length=512,
    )
    frequency: Optional[Frequency] = None
    target: SeriesArray
    past_covariates: Optional[Dict[str, CovariateSeries]] = None
    future_covariates: Optional[Dict[str, CovariateSeries]] = None
    requested_horizon: Optional[int] = None
    metadata: Optional[SeriesMetadata] = None

    @model_validator(mode="after")
    def _validate_covariates(cls, values: "SeriesCatalogEntry") -> "SeriesCatalogEntry":
        target_length = len(values.target.values[0])
        past = values.past_covariates or {}
        for name, covariate in past.items():
            if len(covariate.values) != target_length:
                raise ValueError(
                    f"Past covariate '{name}' must match target history length "
                    f"({len(covariate.values)} != {target_length})."
                )
        future = values.future_covariates or {}
        if values.requested_horizon is not None:
            horizon = values.requested_horizon
            for name, covariate in future.items():
                if len(covariate.values) != horizon:
                    raise ValueError(
                        f"Future covariate '{name}' must match requested horizon "
                        f"({len(covariate.values)} != {horizon})."
                    )
        return values


class CovariateCatalogEntry(BaseModel):
    """Describes an available covariate for documentation and visualization."""

    covariate_id: str
    description: Optional[str] = None
    type: Literal["continuous", "categorical"] = "continuous"
    units: Optional[str] = None
    scale_factor: Optional[float] = None


class RequestMeta(BaseModel):
    """Optional metadata carried alongside the request."""

    job_id: Optional[str] = None
    created_at: Optional[str] = None
    llm_origin: Optional[List[str]] = None
    notes: Optional[List[str]] = None


class ChronosForecastPayload(BaseModel):
    """Top-level request schema accepted by the Chronos service."""

    schema_version: str = Field(default="1.0")
    chronos_target: ChronosTargetConfig
    global_context: ChronosGlobalContext
    series_catalog: List[SeriesCatalogEntry]
    covariate_catalog: Optional[List[CovariateCatalogEntry]] = None
    request_meta: Optional[RequestMeta] = None

    @model_validator(mode="after")
    def _validate_catalog(cls, values: "ChronosForecastPayload") -> "ChronosForecastPayload":
        if not values.series_catalog:
            raise ValueError("series_catalog must contain at least one series entry.")

        max_covariates = values.chronos_target.max_covariates
        for entry in values.series_catalog:
            past = entry.past_covariates or {}
            future = entry.future_covariates or {}
            total_covariates = len(past) + len(future)
            if total_covariates > max_covariates:
                raise ValueError(
                    f"Series '{entry.series_id}' exceeds max_covariates ({total_covariates} > {max_covariates})."
                )
        return values


class SeriesFragment(BaseModel):
    """
    Partial contribution generated by the LLM normalisation layer.
    These fragments are merged into the canonical series catalog before inference.
    """

    chunk_id: str
    series_id: str
    summary: Optional[str] = Field(
        default=None, description="Short description of the fragment contents.", max_length=512
    )
    frequency: Optional[Frequency] = None
    target: Optional[SeriesArray] = None
    past_covariates: Optional[Dict[str, CovariateSeries]] = None
    future_covariates: Optional[Dict[str, CovariateSeries]] = None
    issues: Optional[List[str]] = None
    confidence: Optional[float] = None

