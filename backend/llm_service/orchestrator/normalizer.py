from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Sequence

from fastapi import HTTPException, status

from llm_service.logic_modules.open_ai_client import OpenAIResponsesClient
from llm_service.logic_modules.system_prompt import get_system_prompt
from llm_service.orchestrator.file_processor import (
    ChunkDescriptor,
    MAX_IMAGE_BATCH,
    MAX_IMAGES_PER_REQUEST,
)

logger = logging.getLogger(__name__)

MAX_CONCURRENT_REQUESTS = 4


@dataclass
class NormalizationResult:
    fragments: List[dict]
    upload_reports: Dict[str, dict]


async def normalize_chunks(
    client: OpenAIResponsesClient,
    chunks: Sequence[ChunkDescriptor],
) -> NormalizationResult:
    if not chunks:
        return NormalizationResult([], {})

    image_chunks = [chunk for chunk in chunks if chunk.content_hint == "image"]
    if len(image_chunks) > MAX_IMAGES_PER_REQUEST:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum of {MAX_IMAGES_PER_REQUEST} images per request exceeded.",
        )

    other_chunks = [chunk for chunk in chunks if chunk.content_hint != "image"]

    jobs: List[_NormalizationJob] = []
    if image_chunks:
        for index in range(0, len(image_chunks), MAX_IMAGE_BATCH):
            jobs.append(_NormalizationJob(chunks=image_chunks[index : index + MAX_IMAGE_BATCH], is_image=True))
    for chunk in other_chunks:
        jobs.append(_NormalizationJob(chunks=[chunk], is_image=False))

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    upload_reports: Dict[str, dict] = defaultdict(lambda: {"chunks": [], "issues": []})
    fragments: List[dict] = []

    async def _worker(job: _NormalizationJob) -> None:
        async with semaphore:
            try:
                result_chunks, issues = await _process_job(client, job)
            except Exception as exc:
                logger.exception("Failed to normalize chunk batch: %s", exc)
                raise HTTPException(status_code=500, detail="Normalization failed.") from exc

        fragments.extend(result_chunks)
        for chunk in job.chunks:
            report = upload_reports[str(chunk.upload_id)]
            report["chunks"].append(
                {
                    "chunk_id": chunk.chunk_id,
                    "content_hint": chunk.content_hint,
                    "data": chunk.data,
                }
            )
            report["issues"].extend(issues)

    await asyncio.gather(*[_worker(job) for job in jobs])

    return NormalizationResult(fragments=fragments, upload_reports=dict(upload_reports))


@dataclass
class _NormalizationJob:
    chunks: List[ChunkDescriptor]
    is_image: bool


async def _process_job(
    client: OpenAIResponsesClient,
    job: _NormalizationJob,
) -> tuple[List[dict], List[str]]:
    messages = [{"role": "system", "content": get_system_prompt()}]

    if job.is_image:
        messages.append(await _build_image_user_message(client, job.chunks))
    else:
        messages.append(_build_text_user_message(job.chunks[0]))

    response_text = await client.create_text(messages)

    try:
        parsed = json.loads(response_text)
        if isinstance(parsed, dict):
            fragments = [parsed]
        elif isinstance(parsed, list):
            fragments = parsed
        else:
            raise ValueError("LLM output must be a list or object.")
    except Exception as exc:
        logger.exception("Failed to decode LLM JSON output: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="LLM returned invalid JSON.",
        ) from exc

    issues: List[str] = []
    for fragment in fragments:
        if not isinstance(fragment, dict):
            issues.append("Discarded non-dict fragment.")
    fragments = [fragment for fragment in fragments if isinstance(fragment, dict)]

    return fragments, issues


async def _build_image_user_message(
    client: OpenAIResponsesClient,
    chunks: Sequence[ChunkDescriptor],
) -> dict:
    uploads = []
    for chunk in chunks:
        file_id = await client.upload_file(chunk.file_path)
        uploads.append(file_id)

    chunk_map = "\n".join(
        f"- Image {idx + 1}: chunk_id={chunk.chunk_id}, upload_id={chunk.upload_id}, filename={chunk.file_path.name}"
        for idx, chunk in enumerate(chunks)
    )
    text_instruction = (
        "Analyze the provided images and extract any observable time-series data. "
        "Use the chunk mapping below to reference which image each fragment originated from. "
        "Return JSON fragments that follow the structured guidelines.\n\n"
        f"{chunk_map}"
    )

    content = [{"type": "text", "text": text_instruction}]
    for file_id in uploads:
        content.append({"type": "input_image", "image": {"file_id": file_id}})

    return {"role": "user", "content": content}


def _build_text_user_message(chunk: ChunkDescriptor) -> dict:
    serialized = json.dumps(chunk.data, ensure_ascii=False) if chunk.data else "{}"
    if len(serialized) > 4000:
        serialized = serialized[:4000] + "..."

    prompt = (
        "Normalize the following data chunk into structured JSON fragments. "
        "Each fragment must include the chunk_id so it can be traced back to this source.\n\n"
        f"Chunk ID: {chunk.chunk_id}\n"
        f"Upload ID: {chunk.upload_id}\n"
        f"Content hint: {chunk.content_hint}\n"
        f"Metadata: {serialized}"
    )

    return {"role": "user", "content": prompt}

