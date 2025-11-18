from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Sequence

from llm_service.models_modules.sessions import Message, MessageRole


CHAT_SYSTEM_PROMPT = (
    "You are ChronosChat, a forecasting analyst. Summaries must stay grounded in the "
    "Chronos inference results and user-provided context. Highlight key patterns, cite "
    "quantitative insights, and recommend pragmatic next steps. Avoid speculation beyond the "
    "available data and call out uncertainty when quantiles diverge."
)


@dataclass
class ForecastDigest:
    """Compact representation of a forecast run for conversational grounding."""

    job_id: str
    summary: str
    highlights: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    raw_json: str | None = None


def render_digest(digest: ForecastDigest) -> str:
    """Serialize a digest into a tool-friendly message block."""

    lines = [f"[Forecast Job {digest.job_id}]", digest.summary]
    if digest.highlights:
        lines.append("Highlights:")
        lines.extend(f"- {item}" for item in digest.highlights)
    if digest.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in digest.warnings)
    return "\n".join(lines)


def render_digest_json(digest: ForecastDigest) -> str:
    """Render the raw Chronos response as a tool message."""

    header = f"[Forecast Job {digest.job_id} JSON]"
    payload = digest.raw_json or "{}"
    return f"{header}\n{payload}"


def build_chat_messages(
    *,
    history: Sequence[Message],
    extra_tool_messages: Iterable[str] | None = None,
) -> List[dict]:
    """Construct an OpenAI Responses-compatible message list for the chat LLM."""

    messages: List[dict] = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]

    for entry in history:
        role = entry.role.value
        if role == MessageRole.TOOL.value:
            role = "tool"
        messages.append(
            {
                "role": role,
                "content": (entry.content or "").strip(),
            }
        )

    if extra_tool_messages:
        for payload in extra_tool_messages:
            messages.append({"role": "tool", "content": payload})

    return messages

