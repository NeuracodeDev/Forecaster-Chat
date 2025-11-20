from __future__ import annotations

import logging
import json
from pathlib import Path
from typing import Any, AsyncIterator, Dict, MutableMapping, Sequence
from openai import AsyncOpenAI
from openai.types.responses import Response

from core.configs.llm_config import MODEL_NAME, OPENAI_API_KEY, REASONING_EFFORT, VERBOSITY

logger = logging.getLogger(__name__)


def _extract_output_text(response: Response) -> str:
    """
    Normalize the Responses API output into a plain string.

    The helper inspects multiple fields because `response.output_text` can be empty even
    when the richer `output` payload still contains text blocks (e.g., `output_text` types).
    """

    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    outputs = getattr(response, "output", None)
    if outputs:
        fragments: list[str] = []
        for item in outputs:
            content_list = getattr(item, "content", None) or []
            for block in content_list:
                block_type = getattr(block, "type", None)
                block_text = getattr(block, "text", None)
                if block_type not in {"output_text", "text"}:
                    continue

                if isinstance(block_text, str) and block_text.strip():
                    fragments.append(block_text.strip())
                elif isinstance(block_text, list):
                    sub_chunks = [
                        chunk.strip()
                        for chunk in block_text
                        if isinstance(chunk, str) and chunk.strip()
                    ]
                    fragments.extend(sub_chunks)
                elif isinstance(block_text, dict):
                    text_value = block_text.get("text")
                    if isinstance(text_value, str) and text_value.strip():
                        fragments.append(text_value.strip())
        if fragments:
            return "\n".join(fragments)

    text_list = getattr(response, "text", None)
    if isinstance(text_list, list):
        fragments = [chunk.strip() for chunk in text_list if isinstance(chunk, str) and chunk.strip()]
        if fragments:
            return "\n".join(fragments)

    return ""


ALLOWED_TEXT_TYPES = {"text", "input_text", "output_text"}


def _coerce_dict_payload(item: dict[str, Any], text_type: str) -> dict[str, Any]:
    """
    Normalize a single dict payload into the Responses API compliant schema.

    Anything that previously used {"type": "text"} (legacy ChatCompletion-style payloads)
    will be rewritten to the correct `input_text` / `output_text` flavor.
    """

    item_type = item.get("type")
    if item_type in {"output_text"}:
        return {"type": "output_text", "text": item.get("text", "")}
    if item_type in {"input_text", "text", None}:
        return {"type": text_type, "text": item.get("text", "")}

    # Non-text payload (images, tools, etc.) – pass through untouched.
    return item


def _coerce_content(content: Any, role: str) -> list[dict[str, Any]]:
    """
    Convert simple string content into the Responses API rich content format.
    """
    text_type = "output_text" if role == "assistant" else "input_text"

    if isinstance(content, list):
        normalized: list[dict[str, Any]] = []
        for item in content:
            if isinstance(item, dict):
                normalized.append(_coerce_dict_payload(item, text_type))
            else:
                normalized.append({"type": text_type, "text": str(item)})
        return normalized

    if isinstance(content, dict):
        return [_coerce_dict_payload(content, text_type)]

    if content is None:
        return [{"type": text_type, "text": ""}]

    return [{"type": text_type, "text": str(content)}]


def _prepare_response_input(messages: Sequence[Dict[str, Any]]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role", "user")
        content = _coerce_content(message.get("content"), role)
        prepared.append({"role": role, "content": content})
    return prepared





class OpenAIResponsesClient:
    """
    Thin async wrapper around the OpenAI Responses API.

    Exposes helpers for single-shot calls and streaming, ensuring that every request inherits the
    project defaults (model, reasoning effort, verbosity) defined in `core.configs.llm_config`.
    """

    def __init__(
        self,
        *,
        api_key: str | None = OPENAI_API_KEY,
        model_name: str = MODEL_NAME,
        reasoning_effort: str | None = REASONING_EFFORT,
        verbosity: str | None = VERBOSITY,
    ) -> None:
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")

        self._model = model_name
        self._default_reasoning_effort = reasoning_effort
        self._default_verbosity = verbosity
        self._client = AsyncOpenAI(api_key=api_key)

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""

        await self._client.close()

    async def upload_file(self, path: Path, *, purpose: str = "responses") -> str:
        """Upload a local file to OpenAI and return the file_id."""

        with path.open("rb") as handle:
            file_obj = await self._client.files.create(file=handle, purpose=purpose)
        return file_obj.id

    async def create_response(
        self,
        messages: Sequence[Dict[str, Any]],
        *,
        model_name: str | None = None,
        reasoning_effort: str | None = None,
        response_format: Dict[str, Any] | None = None,
        tools: Sequence[Dict[str, Any]] | None = None,
        metadata: MutableMapping[str, Any] | None = None,
        max_output_tokens: int | None = None,
        extra_options: Dict[str, Any] | None = None,
    ) -> Response:
        """
        Execute a responses.create call and return the raw Response object.

        Parameters mirror the OpenAI Responses API. Additional keyword arguments may be supplied
        via `extra_options` when the caller needs to experiment with new parameters.
        """

        payload: Dict[str, Any] = {
            "model": model_name or self._model,
            "input": _prepare_response_input(messages),
        }

        effort = reasoning_effort or self._default_reasoning_effort
        if effort:
            payload["reasoning"] = {"effort": effort}

        if response_format:
            payload["response_format"] = response_format

        if tools:
            payload["tools"] = list(tools)

        if max_output_tokens is not None:
            payload["max_output_tokens"] = max_output_tokens

        if metadata:
            payload["metadata"] = dict(metadata)
        else:
            payload["metadata"] = {}

        if self._default_verbosity and "verbosity" not in payload["metadata"]:
            payload["metadata"]["verbosity"] = self._default_verbosity

        if extra_options:
            payload.update(extra_options)

        logger.info(
            "openai.responses.create.start",
            extra={
                "model": payload["model"],
                "input_messages": len(payload["input"]),
                "reasoning_effort": payload.get("reasoning"),
                "max_output_tokens": payload.get("max_output_tokens"),
                "has_tools": bool(tools),
            },
        )

        response = await self._client.responses.create(**payload)

        logger.info(
            "openai.responses.create.completed",
            extra={
                "response_id": response.id,
                "model": response.model,
                "usage": getattr(response, "usage", None),
            },
        )
        return response

    async def create_text(
        self,
        messages: Sequence[Dict[str, Any]],
        *,
        model_name: str | None = None,
        reasoning_effort: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Convenience helper returning the combined text output."""

        response = await self.create_response(
            messages,
            model_name=model_name,
            reasoning_effort=reasoning_effort,
            **kwargs,
        )

        text_output = _extract_output_text(response)
        has_structured_output = bool(getattr(response, "output", None))
        logger.info(
            "openai.create_text.response_inspection raw_len=%s normalized_len=%s has_structured_output=%s",
            len(response.output_text or "") if isinstance(response.output_text, str) else 0,
            len(text_output),
            has_structured_output,
        )
        if not text_output:
            serialized_output = None
            outputs = getattr(response, "output", None)
            if outputs:
                try:
                    serialized_output = json.dumps(
                        [item.model_dump() for item in outputs], default=str
                    )
                except Exception:  # noqa: BLE001
                    serialized_output = str(outputs)
            logger.warning(
                "openai.create_text.empty_output response_id=%s model=%s serialized_output=%s text_field=%s",
                response.id,
                response.model,
                serialized_output[:512] if isinstance(serialized_output, str) else serialized_output,
                getattr(response, "text", None),
            )
        return text_output

    async def stream_text(
        self,
        messages: Sequence[Dict[str, Any]],
        *,
        model_name: str | None = None,
        reasoning_effort: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """
        Stream text deltas from the Responses API.

        Yields incremental string chunks; once the stream ends the final response is awaited so
        the caller can observe usage metadata if desired.
        """

        payload: Dict[str, Any] = {
            "model": model_name or self._model,
            "input": _prepare_response_input(messages),
        }

        effort = reasoning_effort or self._default_reasoning_effort
        if effort:
            payload["reasoning"] = {"effort": effort}

        if self._default_verbosity:
            metadata = kwargs.pop("metadata", {})
            payload["metadata"] = {**metadata, "verbosity": metadata.get("verbosity", self._default_verbosity)}

        payload.update(kwargs)

        stream = await self._client.responses.stream(**payload)
        try:
            async for event in stream:
                if event.type == "response.output_text.delta":
                    yield event.delta
        finally:
            await stream.get_final_response()

    async def __aenter__(self) -> "OpenAIResponsesClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

