# embed_and_upsert.py
#
# Deliverable 3: embed each chunk (via Hugging Face Inference API) and
# upsert into Qdrant Cloud, with department metadata as filterable payload
# and stable content-hash IDs so re-running the script doesn't create
# duplicates.

import hashlib
import os
import pickle
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import InferenceClient
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHUNKS_PATH = PROJECT_ROOT / "data" / "chunks.pkl"

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = "enterprise_policy_docs"

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")

BATCH_SIZE = 32


def stable_id(text, metadata):
    """Deterministic ID from content + source file, so re-running this
    script upserts (overwrites) the same points instead of duplicating."""
    key = f"{metadata.get('source_file', '')}|{metadata.get('section_heading', '')}|{text}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def get_embedding_dimension(hf_client):
    """Embed a throwaway string once to discover the model's vector size,
    so we can create the Qdrant collection with the right dimensions."""
    result = hf_client.feature_extraction("dimension probe", model=EMBEDDING_MODEL)
    return len(result)


def ensure_collection(qdrant_client, hf_client):
    existing = [c.name for c in qdrant_client.get_collections().collections]
    if COLLECTION_NAME in existing:
        print(f"Collection '{COLLECTION_NAME}' already exists — reusing it.")
        return
    print(f"Collection '{COLLECTION_NAME}' not found. Creating it...")
    dim = get_embedding_dimension(hf_client)
    qdrant_client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )
    print(f"Created collection '{COLLECTION_NAME}' with vector size {dim}.")


def load_chunks():
    if not CHUNKS_PATH.exists():
        raise FileNotFoundError(
            f"{CHUNKS_PATH} not found — run chunk_documents.py first."
        )
    with open(CHUNKS_PATH, "rb") as f:
        return pickle.load(f)


def main():
    print("Loading chunks...")
    chunks = load_chunks()
    print(f"Loaded {len(chunks)} chunk(s) from {CHUNKS_PATH.relative_to(PROJECT_ROOT)}\n")
    if not chunks:
        print("No chunks to process. Exiting.")
        return

    print(f"Connecting to Hugging Face Inference API (model: {EMBEDDING_MODEL})...")
    hf_client = InferenceClient(token=HUGGINGFACE_API_KEY)

    print(f"Connecting to Qdrant Cloud at {QDRANT_URL}...")
    qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    ensure_collection(qdrant_client, hf_client)

    print(f"\nEmbedding and upserting {len(chunks)} chunk(s) in batches of {BATCH_SIZE}...\n")

    total_upserted = 0
    total_failed = 0

    for batch_start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[batch_start:batch_start + BATCH_SIZE]
        batch_num = batch_start // BATCH_SIZE + 1
        print(f"Batch {batch_num}: embedding {len(batch)} chunk(s)...")

        points = []
        for node in batch:
            text = node.get_content()
            metadata = dict(node.metadata)
            try:
                vector = hf_client.feature_extraction(text, model=EMBEDDING_MODEL)
                vector = list(vector)
            except Exception as e:
                print(f"  FAILED to embed a chunk (source_file={metadata.get('source_file')}): "
                      f"{type(e).__name__}: {e}")
                total_failed += 1
                continue

            point_id = stable_id(text, metadata)
            payload = dict(metadata)
            payload["text"] = text  # keep the raw text too, useful for retrieval later

            points.append(PointStruct(id=point_id, vector=vector, payload=payload))

        if points:
            qdrant_client.upsert(collection_name=COLLECTION_NAME, points=points)
            total_upserted += len(points)
            print(f"  Batch {batch_num} done: {len(points)} point(s) upserted.")
        else:
            print(f"  Batch {batch_num}: no points to upsert (all failed).")

    collection_info = qdrant_client.get_collection(COLLECTION_NAME)
    print(f"\nQdrant collection '{COLLECTION_NAME}' now reports "
          f"{collection_info.points_count} point(s) stored.")

    if collection_info.points_count < total_upserted:
        print("NOTE: reported count is lower than what we just upserted — "
              "this can happen if some IDs already existed and were overwritten "
              "(expected on a re-run), not necessarily an error.")

    print(f"\nDone. {total_upserted} upserted, {total_failed} failed.")


if __name__ == "__main__":
    main()
