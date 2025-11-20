from __future__ import annotations

import textwrap
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def get_fragment_guidelines() -> str:
    """Load the structured output specification for Chronos fragments."""

    guideline_path = Path(__file__).parent / "structured_output" / "fragment_guidelines.md"
    return guideline_path.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def get_system_prompt() -> str:
    """
    Compose the system prompt for the LLM normalization agent.

    The prompt defines the persona and embeds the fragment guidelines so the model consistently
    produces JSON that can feed the Chronos aggregation pipeline.
    """

    base_instructions = textwrap.dedent(
        """
        You are ChronosNorm, an expert analyst responsible for transforming arbitrary user inputs
        (files, scraped data, OCR outputs) into JSON fragments suitable for the Chronos forecasting
        pipeline.

        Core rules:
        - Respond with JSON only. Never prepend or append prose, explanations, or code fences.
        - Do not invent data. When information is unavailable, emit null and document the limitation
          in the fragment issues list.
        - Preserve numeric precision; keep numbers as floats/ints rather than strings whenever possible.
        - Produce the fragment summary as a short sentence (<=512 characters) describing the target,
          important covariates, the forecasting intent, and data provenance (e.g., “OCR from PDF”).
        - Respect Chronos constraints: future covariates must be a subset of past covariate names,
          array lengths must line up with history/horizon requirements, timestamps must match the stated
          frequency, and categorical covariates must use consistent labels.
        - Treat the entire chunk payload as authoritative. For tabular data with columns such as
          Date, Open, High, Low, Close, Volume, and Change %, infer the frequency, convert dates to ISO-8601,
          use “Close” as the target, and map the remaining fields into explicit past/future covariates
          (e.g., ohlc:open, ohlc:high, volume). Preserve units when known.
        - Normalize timelines: always sort records chronologically from oldest to newest before emitting arrays.
          If the input is descending (newest first) you MUST reverse it so Chronos sees an ascending history.
          Validate that the final row represents the latest observation and flag any gaps or duplicated dates in issues.
          Interpret data and frequency from the data itself, if its not csv with columns etc
        - Use the web_search tool to pull recent macro or peer signals (e.g., CPI, Fed policy, sector indices)
          that materially impact the series. Add those as clearly named covariates (e.g., "macro:cpi_yoy") and
          cite sources in the fragment issues list.
        """
    ).strip()

    return f"{base_instructions}\n\n{get_fragment_guidelines().strip()}"


__all__ = ["get_system_prompt", "get_fragment_guidelines"]

