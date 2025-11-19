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
          any important covariates, the forecasting intent, and data provenance (e.g., “OCR from PDF”).
        - Respect Chronos constraints: future covariates must be a subset of past covariate names,
          array lengths must line up with history/horizon requirements, timestamps must match the stated
          frequency, and categorical covariates must use consistent labels.
        - Incorporate the entire chunk payload. If the data references external benchmarks, enrich it
          with trusted public context (including via web search when appropriate) and cite sources in
          the fragment issues list.
        - When additional macro or covariate signals are discovered via web search, include them as
          structured covariates with clear naming (e.g., "macro:cpi", "macro:fed_funds").
        """
    ).strip()

    return f"{base_instructions}\n\n{get_fragment_guidelines().strip()}"


__all__ = ["get_system_prompt", "get_fragment_guidelines"]

