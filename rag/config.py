"""
Central configuration for the Enterprise Policy RAG project.

Every script (chunking, embedding, retrieval, the FastAPI app) should
import from this file instead of hardcoding model names, URLs, or the
department list in multiple places.

Requires a .env file in the project root (NEVER commit this file's
values elsewhere, and NEVER commit .env itself - it's gitignored):

    OLLAMA_API_KEY=your_actual_key_here
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load variables from .env into the environment
load_dotenv()

# --------------------------------------------------------------------
# Ollama Cloud - used for the LLM that generates answers
# --------------------------------------------------------------------
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")
OLLAMA_CLOUD_BASE_URL = "https://ollama.com"
LLM_MODEL_NAME = "gpt-oss:20b"

# --------------------------------------------------------------------
# Local Ollama - used ONLY for embeddings (Ollama Cloud free tier has
# no hosted embedding models as of Sept 2026; nomic-embed-text is a
# small ~274MB model run locally instead - negligible disk/RAM cost).
# --------------------------------------------------------------------
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# --------------------------------------------------------------------
# Qdrant vector store
# --------------------------------------------------------------------
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", None)
QDRANT_COLLECTION_NAME = "enterprise_policy_docs"

# --------------------------------------------------------------------
# Departments - the single list every script should reference
# --------------------------------------------------------------------
DEPARTMENTS = ["hr", "legal", "finance", "it"]

# --------------------------------------------------------------------
# Project paths
# --------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATA_PARSED_DIR = PROJECT_ROOT / "data" / "parsed"
CHUNKS_FILE_PATH = PROJECT_ROOT / "data" / "chunks.pkl"


def validate_config():
    """Call this at the start of any script to fail fast with a clear
    error message if something essential is missing, instead of a
    confusing error deep inside a library call later."""
    if not OLLAMA_API_KEY:
        raise RuntimeError(
            "OLLAMA_API_KEY not found. Make sure you have a .env file "
            "in the project root with: OLLAMA_API_KEY=your_key_here"
        )
    print("Config validated OK.")
    print(f"  Embedding model: {EMBEDDING_MODEL_NAME} (via Hugging Face)")
    print(f"  Qdrant: {QDRANT_URL}, collection '{QDRANT_COLLECTION_NAME}'")
    print(f"  Departments: {DEPARTMENTS}")


if __name__ == "__main__":
    validate_config()
