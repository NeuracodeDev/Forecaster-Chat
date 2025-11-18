from __future__ import annotations

import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from fastapi import HTTPException, status

from llm_service.models_modules.sessions import UploadArtifact


IMAGE_MIME_PREFIXES = {"image/"}
MAX_IMAGE_BATCH = 5
MAX_IMAGES_PER_REQUEST = 20

PDF_PAGES_PER_CHUNK = 5
CSV_ROWS_PER_CHUNK = 400
JSON_RECORDS_PER_CHUNK = 400
TEXT_SENTENCES_PER_CHUNK = 40

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
    try:
        import pypdf  # noqa: F401
        reader = pypdf.PdfReader(str(path))
        total_pages = len(reader.pages)
    except Exception:  # pragma: no cover
        total_pages = PDF_PAGES_PER_CHUNK

    chunks: List[ChunkDescriptor] = []
    for chunk_index, start_page in enumerate(range(0, total_pages, PDF_PAGES_PER_CHUNK)):
        end_page = min(start_page + PDF_PAGES_PER_CHUNK, total_pages)
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
            },
        )
        chunks.append(descriptor)
    return chunks


def _chunk_csv(artifact: UploadArtifact, path: Path, mime_type: str) -> List[ChunkDescriptor]:
    import pandas as pd

    try:
        iterator = pd.read_csv(path, chunksize=CSV_ROWS_PER_CHUNK)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {exc}") from exc

    chunks: List[ChunkDescriptor] = []
    for idx, chunk in enumerate(iterator):
        data_preview = chunk.head(5).to_json(orient="records")
        descriptor = ChunkDescriptor(
            upload_id=str(artifact.id),
            chunk_id=f"{artifact.id}_csv_{idx}",
            file_path=path,
            mime_type=mime_type,
            content_hint="csv",
            data={
                "start_row": idx * CSV_ROWS_PER_CHUNK,
                "end_row": idx * CSV_ROWS_PER_CHUNK + len(chunk),
                "columns": list(chunk.columns),
                "preview": data_preview,
                "chunk_path": str(path),
            },
        )
        chunks.append(descriptor)
    return chunks


def _chunk_json(artifact: UploadArtifact, path: Path, mime_type: str) -> List[ChunkDescriptor]:
    import json

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

