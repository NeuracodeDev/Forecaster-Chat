from __future__ import annotations

import logging
from typing import Sequence

from core.configs.llm_config import TITLE_MODEL_NAME
from llm_service.logic_modules.open_ai_client import OpenAIResponsesClient

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARS = 48
DEFAULT_MAX_OUTPUT_TOKENS = 64000

TITLE_SYSTEM_PROMPT = """\
You are ChronosTitle, a precise assistant that condenses a user's first message into a
short chat title.

Constraints:
- Keep titles between 3 and 8 words, <= {max_chars} characters.
- No quotation marks, emojis, numbering, or trailing punctuation.
- Summarize the user's goal or dataset focus directly.
- Title-case the result (capitalize principal words).
Output only the title text. Do not explain your reasoning.
"""


def _sanitize_title(text: str, max_chars: int) -> str:
    """Normalize whitespace, strip quotes, and enforce the character limit."""

    cleaned = " ".join(text.strip().split())
    cleaned = cleaned.strip("\"'")
    if not cleaned:
        return "New conversation"

    if len(cleaned) <= max_chars:
        return cleaned

    truncated = cleaned[:max_chars].rstrip()
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated or cleaned[:max_chars]


def _fallback_title(message: str, max_chars: int) -> str:
    """Fallback strategy when the model call fails."""

    snippet = " ".join(message.strip().split())[:max_chars]
    return snippet if snippet else "New conversation"


async def generate_chat_title(
    *,
    client: OpenAIResponsesClient,
    first_user_message: str,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str:
    """
    Generate a concise conversation title using the lightweight title model.

    Parameters
    ----------
    client:
        Shared OpenAIResponsesClient instance.
    first_user_message:
        The very first user utterance in the conversation.
    max_chars:
        Upper bound for the returned title length.
    """

    logger.info(f"title_generator.generate_chat_title.start message_length={len(first_user_message)} max_chars={max_chars} model={TITLE_MODEL_NAME}")

    stripped_message = first_user_message.strip()
    if not stripped_message:
        logger.info("title_generator.generate_chat_title.empty_message")
        return "New conversation"

    messages: Sequence[dict[str, str]] = [
        {"role": "system", "content": TITLE_SYSTEM_PROMPT.format(max_chars=max_chars)},
        {"role": "user", "content": stripped_message},
    ]

    try:
        logger.info(f"title_generator.generate_chat_title.calling_llm model={TITLE_MODEL_NAME} message_count={len(messages)}")
        raw_title = await client.create_text(
            messages,
            model_name=TITLE_MODEL_NAME,
            reasoning_effort=None,
            max_output_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
        )
        logger.info(f"title_generator.generate_chat_title.llm_response raw_title={raw_title} raw_length={len(raw_title)}")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"title_generator.generate_chat_title.llm_failed error_type={type(exc).__name__} error_message={str(exc)}", exc_info=exc)
        fallback = _fallback_title(stripped_message, max_chars)
        logger.info(f"title_generator.generate_chat_title.using_fallback fallback_title={fallback}")
        return fallback

    sanitized = _sanitize_title(raw_title, max_chars)
    logger.info(f"title_generator.generate_chat_title.completed final_title={sanitized} was_truncated={len(raw_title) != len(sanitized)}")
    return sanitized


__all__ = ["generate_chat_title"]

