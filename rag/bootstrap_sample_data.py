"""
TEMPORARY bootstrap script for Person B (RAG core) to have real,
department-tagged chunks in Qdrant to build and test retrieval against,
without waiting for Person A's full Docling parsing/chunking pipeline.

This is intentionally simple (not Docling-quality parsing) - it exists
ONLY so query_engine.py and router_agent.py can be built and tested in
parallel with Person A's real work. Once Person A's
digest/embed_and_upsert.py is ready and has populated the same Qdrant
collection with properly-parsed chunks, this script's output should be
considered superseded - just re-run Person A's real pipeline to replace
this bootstrap data.

Run:
    python rag/bootstrap_sample_data.py

What it does:
    1. Reads every PDF/DOCX/XLSX under data/raw/{department}/
    2. Extracts plain text (simple extraction, not layout-aware)
    3. Splits into paragraph-based chunks
    4. Tags each chunk with department + source_file metadata
    5. Embeds each chunk using the local nomic-embed-text model
    6. Upserts everything into the Qdrant collection defined in config.py
"""

import sys
import hashlib
from pathlib import Path

import pymupdf  # PDF text extraction (formerly imported as `fitz`)
from docx import Document as DocxDocument
from openpyxl import load_workbook
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from rag.config import (
    DATA_RAW_DIR, DEPARTMENTS, OLLAMA_LOCAL_BASE_URL, EMBEDDING_MODEL_NAME,
    QDRANT_HOST, QDRANT_PORT, QDRANT_COLLECTION_NAME, validate_config
)

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct


def extract_text_from_pdf(filepath):
    doc = pymupdf.open(filepath)
    text = "\n\n".join(page.get_text() for page in doc)
    doc.close()
    return text


def extract_text_from_docx(filepath):
    doc = DocxDocument(filepath)
    parts = []
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text)
    return "\n\n".join(parts)


def extract_text_from_xlsx(filepath):
    wb = load_workbook(filepath, data_only=True)
    parts = []
    for sheet in wb.worksheets:
        parts.append(f"Sheet: {sheet.title}")
        for row in sheet.iter_rows(values_only=True):
            row_text = " | ".join(str(c) for c in row if c is not None)
            if row_text.strip():
                parts.append(row_text)
    return "\n".join(parts)


def chunk_text(text, max_chars=1000, overlap_chars=150):
    """
    Paragraph-based chunking with a hard-size fallback.

    PDF text extraction often doesn't preserve reliable paragraph breaks
    (PyMuPDF gives per-line text, not per-paragraph), so relying on
    `\n\n` alone can leave a whole multi-page document as one "paragraph".
    To guard against that, any single paragraph longer than max_chars is
    itself split on sentence boundaries with a small overlap, so no
    chunk is ever unreasonably large regardless of how the source text
    was extracted.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    # Fallback: if extraction produced basically one giant paragraph,
    # also split on single newlines so we have real chunk boundaries.
    if len(paragraphs) <= 1 and text.strip():
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]

    chunks = []
    current = ""
    for para in paragraphs:
        # If a single paragraph alone exceeds max_chars, hard-split it
        # on sentence boundaries so it doesn't dominate one giant chunk.
        if len(para) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            sentences = para.replace(". ", ".|").split("|")
            piece = ""
            for sent in sentences:
                if len(piece) + len(sent) < max_chars:
                    piece += sent
                else:
                    if piece:
                        chunks.append(piece.strip())
                    piece = sent
            if piece:
                current = piece
            continue

        if len(current) + len(para) < max_chars:
            current += ("\n" if current else "") + para
        else:
            if current:
                chunks.append(current)
            current = para

    if current:
        chunks.append(current)

    return chunks


def guess_doc_type(filename):
    lower = filename.lower()
    if "sop" in lower:
        return "sop"
    if filename.endswith(".xlsx"):
        return "data_sheet"
    return "policy"


def get_embedding(text):
    resp = requests.post(
        f"{OLLAMA_LOCAL_BASE_URL}/api/embed",
        json={"model": EMBEDDING_MODEL_NAME, "input": text},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"][0]


def stable_id(text):
    """Deterministic ID so re-running this script upserts (overwrites)
    rather than duplicating points."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def main():
    validate_config()

    print("\nConnecting to Qdrant...")
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    # Create collection if it doesn't exist (768 dims = nomic-embed-text's output size)
    existing = [c.name for c in client.get_collections().collections]
    if QDRANT_COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=QDRANT_COLLECTION_NAME,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )
        print(f"Created collection '{QDRANT_COLLECTION_NAME}'")
    else:
        print(f"Collection '{QDRANT_COLLECTION_NAME}' already exists, upserting into it")

    total_chunks = 0
    points_batch = []

    for dept in DEPARTMENTS:
        dept_dir = DATA_RAW_DIR / dept
        if not dept_dir.exists():
            print(f"  WARNING: {dept_dir} does not exist, skipping")
            continue

        for filepath in dept_dir.iterdir():
            if filepath.suffix.lower() not in [".pdf", ".docx", ".xlsx"]:
                continue

            print(f"Processing [{dept}] {filepath.name}...")
            try:
                if filepath.suffix.lower() == ".pdf":
                    text = extract_text_from_pdf(filepath)
                elif filepath.suffix.lower() == ".docx":
                    text = extract_text_from_docx(filepath)
                elif filepath.suffix.lower() == ".xlsx":
                    text = extract_text_from_xlsx(filepath)
                else:
                    continue
            except Exception as e:
                print(f"  ERROR parsing {filepath.name}: {e}")
                continue

            chunks = chunk_text(text)
            doc_type = guess_doc_type(filepath.name)

            for i, chunk in enumerate(chunks):
                try:
                    vector = get_embedding(chunk)
                except Exception as e:
                    print(f"  ERROR embedding chunk {i} of {filepath.name}: {e}")
                    continue

                point_id = stable_id(f"{filepath.name}-{i}")
                points_batch.append(
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "text": chunk,
                            "department": dept,
                            "source_file": filepath.name,
                            "doc_type": doc_type,
                            "chunk_index": i,
                        },
                    )
                )
                total_chunks += 1

            print(f"  -> {len(chunks)} chunks")

    print(f"\nUpserting {len(points_batch)} points into Qdrant...")
    # Batch upsert in groups of 50
    batch_size = 50
    for i in range(0, len(points_batch), batch_size):
        batch = points_batch[i : i + batch_size]
        client.upsert(collection_name=QDRANT_COLLECTION_NAME, points=batch)
        print(f"  Upserted {min(i + batch_size, len(points_batch))}/{len(points_batch)}")

    info = client.get_collection(QDRANT_COLLECTION_NAME)
    print(f"\nDone. Collection '{QDRANT_COLLECTION_NAME}' now has "
          f"{info.points_count} total points.")
    print(f"Total chunks processed this run: {total_chunks}")


if __name__ == "__main__":
    main()
