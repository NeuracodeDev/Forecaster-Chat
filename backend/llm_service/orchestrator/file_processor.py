from __future__ import annotations

import json
import logging
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import List

from fastapi import HTTPException, status

from core.configs.llm_config import (
    CSV_ROWS_PER_CHUNK,
    JSON_RECORDS_PER_CHUNK,
    PDF_PAGES_PER_CHUNK,
    TEXT_SENTENCES_PER_CHUNK,
)
from llm_service.models_modules.sessions import UploadArtifact


logger = logging.getLogger(__name__)

IMAGE_MIME_PREFIXES = {"image/"}
MAX_IMAGE_BATCH = 5
MAX_IMAGES_PER_REQUEST = 20

STORAGE_ROOT = Path("/app/storage/uploads")


@dataclass(frozen=True)
class ChunkDescriptor:
    upload_id: str
    chunk_id: str
    file_path: Path
    mime_type: str
    content_hint: str
    data: dict


def process_upload_artifact(artifact: UploadArtifact) -> List[ChunkDescriptor]:
    if artifact.stored_path is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Upload {artifact.id} missing stored_path.",
        )

    absolute_path = STORAGE_ROOT / artifact.stored_path.lstrip("/\\")
    if not absolute_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Upload file not found: {artifact.stored_path}",
        )

    mime = artifact.mime_type or mimetypes.guess_type(absolute_path.name)[0] or "application/octet-stream"

    if _is_image(mime):
        return [
            ChunkDescriptor(
                upload_id=str(artifact.id),
                chunk_id=f"{artifact.id}_image",
                file_path=absolute_path,
                mime_type=mime,
                content_hint="image",
                data={"image_path": str(absolute_path)},
            )
        ]

    suffix = absolute_path.suffix.lower()
    if suffix == ".pdf":
        return _chunk_pdf(artifact, absolute_path, mime)
    if suffix in {".csv", ".tsv"}:
        return _chunk_csv(artifact, absolute_path, mime)
    if suffix in {".json", ".jsonl"}:
        return _chunk_json(artifact, absolute_path, mime)
    return _chunk_text(artifact, absolute_path, mime)


def _is_image(mime_type: str) -> bool:
    return any(mime_type.startswith(prefix) for prefix in IMAGE_MIME_PREFIXES)


def _chunk_pdf(artifact: UploadArtifact, path: Path, mime_type: str) -> List[ChunkDescriptor]:
    reader = None
    total_pages = PDF_PAGES_PER_CHUNK
    try:
        import pypdf  # noqa: F401

        reader = pypdf.PdfReader(str(path))
        total_pages = len(reader.pages)
    except Exception:  # pragma: no cover
        logger.warning("Failed to parse PDF text; only metadata will be provided.", exc_info=True)

    chunks: List[ChunkDescriptor] = []
    for chunk_index, start_page in enumerate(range(0, total_pages, PDF_PAGES_PER_CHUNK)):
        end_page = min(start_page + PDF_PAGES_PER_CHUNK, total_pages)
        page_texts: List[str] = []
        if reader is not None:
            for page_num in range(start_page, end_page):
                try:
                    page_texts.append(reader.pages[page_num].extract_text() or "")
                except Exception:  # pragma: no cover
                    page_texts.append("")

        descriptor = ChunkDescriptor(
            upload_id=str(artifact.id),
            chunk_id=f"{artifact.id}_pdf_{chunk_index}",
            file_path=path,
            mime_type=mime_type,
            content_hint="pdf",
            data={
                "page_start": start_page,
                "page_end": end_page,
                "description": f"Pages {start_page + 1}–{end_page} of PDF {path.name}",
                "text": "\n".join(page_texts) if page_texts else None,
            },
        )
        chunks.append(descriptor)
    return chunks


def _chunk_csv(artifact: UploadArtifact, path: Path, mime_type: str) -> List[ChunkDescriptor]:
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        lines = [line.rstrip("\n") for line in fh if line.rstrip("\n")]

    if not lines:
        raise HTTPException(status_code=400, detail="CSV file is empty.")

    header = lines[0]
    rows = lines[1:]
    chunks: List[ChunkDescriptor] = []

    for idx in range(0, len(rows), CSV_ROWS_PER_CHUNK):
        chunk_rows = rows[idx : idx + CSV_ROWS_PER_CHUNK]
        raw_csv = "\n".join([header, *chunk_rows])
        descriptor = ChunkDescriptor(
            upload_id=str(artifact.id),
            chunk_id=f"{artifact.id}_csv_{idx}",
            file_path=path,
            mime_type=mime_type,
            content_hint="csv",
            data={
                "format": "csv",
                "header": header,
                "row_start": idx + 1,
                "row_end": idx + len(chunk_rows),
                "row_count": len(chunk_rows),
                "raw_csv": raw_csv,
                "chunk_path": str(path),
            },
        )
        chunks.append(descriptor)

    logger.info(
        "file_processor.chunk_csv.completed",
        extra={
            "upload_id": str(artifact.id),
        "path": str(path),
        "chunk_count": len(chunks),
        "total_rows": len(rows),
        },
    )
    return chunks


def _chunk_json(artifact: UploadArtifact, path: Path, mime_type: str) -> List[ChunkDescriptor]:
    records: List[str]
    with path.open("r", encoding="utf-8") as fh:
        content = fh.read().strip()
        if content.startswith("["):
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail=f"Invalid JSON file: {exc}") from exc
            if not isinstance(parsed, list):
                parsed = [parsed]
            records = [json.dumps(item, ensure_ascii=False) for item in parsed]
        else:
            records = [line for line in content.splitlines() if line.strip()]

    if len(records) <= JSON_RECORDS_PER_CHUNK:
        chunks = [records]
    else:
        chunks = [
            records[i : i + JSON_RECORDS_PER_CHUNK] for i in range(0, len(records), JSON_RECORDS_PER_CHUNK)
        ]

    descriptors: List[ChunkDescriptor] = []
    for idx, record_chunk in enumerate(chunks):
        preview = json.dumps(
            [json.loads(rec) for rec in record_chunk[:5]],
            ensure_ascii=False,
        )
        descriptor = ChunkDescriptor(
            upload_id=str(artifact.id),
            chunk_id=f"{artifact.id}_json_{idx}",
            file_path=path,
            mime_type=mime_type,
            content_hint="json",
            data={
                "records": record_chunk,
                "count": len(record_chunk),
                "preview": preview,
                "description": f"JSON records {idx * JSON_RECORDS_PER_CHUNK + 1}-{idx * JSON_RECORDS_PER_CHUNK + len(record_chunk)}",
            },
        )
        descriptors.append(descriptor)
    return descriptors


def _chunk_text(artifact: UploadArtifact, path: Path, mime_type: str) -> List[ChunkDescriptor]:
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        content = fh.read()

    sentences = []
    sentence = []
    for token in content.replace("\n", " ").split(" "):
        sentence.append(token)
        if token.endswith((".", "!", "?", ";")):
            sentences.append(" ".join(sentence).strip())
            sentence = []
    if sentence:
        sentences.append(" ".join(sentence).strip())

    if not sentences:
        sentences = [content]

    chunks = [
        sentences[i : i + TEXT_SENTENCES_PER_CHUNK]
        for i in range(0, len(sentences), TEXT_SENTENCES_PER_CHUNK)
    ]

    descriptors: List[ChunkDescriptor] = []
    for idx, sentence_chunk in enumerate(chunks):
        chunk_text = " ".join(sentence_chunk)
        descriptor = ChunkDescriptor(
            upload_id=str(artifact.id),
            chunk_id=f"{artifact.id}_text_{idx}",
            file_path=path,
            mime_type=mime_type,
            content_hint="text",
            data={
                "content": chunk_text,
                "sentence_count": len(sentence_chunk),
                "description": f"Text chunk {idx + 1}/{len(chunks)}",
            },
        )
        descriptors.append(descriptor)
    return descriptors

