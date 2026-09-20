"""
Core RAG query engine for the Enterprise Policy RAG project.

This module implements the "production RAG" techniques called out in
the project brief: metadata-filtered retrieval (so a query can be
scoped to one or more departments instead of searching everything) and
cross-encoder reranking on top of raw vector similarity (raw cosine
similarity from an embedding model is a decent first pass, but a
reranker that reads the actual query and chunk together is
substantially better at ranking true relevance).

Two entry points are exposed for use by other modules (e.g. the
LangGraph router in router_agent.py, or the FastAPI app in app.py):

    query(question, department_filter=None) -> QueryResult
    retrieve_only(question, department_filter=None, top_k=15) -> list[NodeWithScore]

query() does the full pipeline: filtered retrieval -> rerank -> LLM
synthesis -> a structured result with the answer text, the source
chunks used, and which department(s) they came from.

retrieve_only() exposes just the retrieval+rerank step without LLM
synthesis, which the router agent needs when it wants to gather
evidence from multiple departments before deciding how to combine them.
"""

import sys
from pathlib import Path
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag.config import (
    OLLAMA_API_KEY, OLLAMA_CLOUD_BASE_URL, LLM_MODEL_NAME,
    HUGGINGFACE_API_KEY, EMBEDDING_MODEL_NAME,
    QDRANT_URL, QDRANT_API_KEY, QDRANT_COLLECTION_NAME, DEPARTMENTS,
)

from llama_index.core import VectorStoreIndex, Settings
from llama_index.core.vector_stores import (
    MetadataFilters, MetadataFilter, FilterOperator, FilterCondition,
)
from llama_index.core.postprocessor import SentenceTransformerRerank
from llama_index.core.schema import NodeWithScore
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient


# --------------------------------------------------------------------
# Global LlamaIndex settings - configured once at import time
# --------------------------------------------------------------------

from llama_index.core.embeddings import BaseEmbedding
from huggingface_hub import InferenceClient
from typing import Any


class SyncHuggingFaceEmbedding(BaseEmbedding):
    """Simple synchronous embedding wrapper, avoiding the async-only
    HuggingFaceInferenceAPIEmbedding client which conflicts with
    FastAPI's own event loop under load."""

    _client: Any = None
    _model_name: str = EMBEDDING_MODEL_NAME

    def __init__(self, model_name, token, **kwargs):
        super().__init__(**kwargs)
        self._client = InferenceClient(token=token)
        self._model_name = model_name

    def _get_query_embedding(self, query: str):
        return list(self._client.feature_extraction(query, model=self._model_name))

    def _get_text_embedding(self, text: str):
        return list(self._client.feature_extraction(text, model=self._model_name))

    async def _aget_query_embedding(self, query: str):
        return self._get_query_embedding(query)

    async def _aget_text_embedding(self, text: str):
        return self._get_text_embedding(text)


Settings.embed_model = SyncHuggingFaceEmbedding(
    model_name=EMBEDDING_MODEL_NAME,
    token=HUGGINGFACE_API_KEY,
)

Settings.llm = Ollama(
    model=LLM_MODEL_NAME,
    base_url=OLLAMA_CLOUD_BASE_URL,
    additional_kwargs={"headers": {"Authorization": f"Bearer {OLLAMA_API_KEY}"}},
    request_timeout=120.0,
)

_reranker = None


def _get_reranker():
    """Lazily creates the reranker on first use rather than at import
    time. This avoids failing on import (or blocking other code that
    imports this module) if the Hugging Face model download is slow or
    briefly unavailable, and gives a clearer error message pointing at
    what actually happened."""
    global _reranker
    if _reranker is None:
        print("Loading reranker model (first use only, downloads ~80MB "
              "from Hugging Face if not already cached)...")
        _reranker = SentenceTransformerRerank(
            model="cross-encoder/ms-marco-MiniLM-L-6-v2",
            top_n=4,
        )
    return _reranker


def _get_index():
    """Connects to the existing Qdrant collection and wraps it as a
    LlamaIndex VectorStoreIndex. Does NOT re-embed or re-upload
    anything - it reads whatever is already in Qdrant (put there by
    bootstrap_sample_data.py for now, or Person A's real pipeline
    later)."""
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    vector_store = QdrantVectorStore(client=client, collection_name=QDRANT_COLLECTION_NAME)
    return VectorStoreIndex.from_vector_store(vector_store)


def _build_department_filter(departments):
    """Builds a LlamaIndex MetadataFilters object that restricts
    retrieval to chunks whose 'department' payload field matches ANY of
    the given department names. Pass None or an empty list to search
    across all departments with no restriction."""
    if not departments:
        return None
    filters = [
        MetadataFilter(key="department", value=dept, operator=FilterOperator.EQ)
        for dept in departments
    ]
    if len(filters) == 1:
        return MetadataFilters(filters=filters)
    return MetadataFilters(filters=filters, condition=FilterCondition.OR)


@dataclass
class QueryResult:
    answer: str
    departments_used: list = field(default_factory=list)
    sources: list = field(default_factory=list)  # list of dicts: {text, department, source_file, score}


def retrieve_only(question: str, department_filter=None, top_k: int = 15) -> list[NodeWithScore]:
    """
    Runs retrieval + reranking WITHOUT LLM synthesis. Returns a list of
    NodeWithScore, reranked and truncated to the reranker's top_n.

    department_filter: None (search all departments) or a list of
    department name strings to restrict the search to.
    """
    index = _get_index()
    filters = _build_department_filter(department_filter)

    retriever = index.as_retriever(
        similarity_top_k=top_k,
        filters=filters,
    )
    nodes = retriever.retrieve(question)

    if not nodes:
        return []

    reranked = _get_reranker().postprocess_nodes(nodes, query_str=question)
    return reranked


def query(question: str, department_filter=None) -> QueryResult:
    """
    Full pipeline: filtered retrieval -> rerank -> LLM synthesis.

    If retrieval finds nothing relevant (empty result after filtering),
    this returns an honest "not found in the documents" answer rather
    than letting the LLM hallucinate a response with no grounding -
    this is the abstention behavior that's part of what makes this a
    trustworthy system rather than a naive RAG demo.
    """
    reranked_nodes = retrieve_only(question, department_filter=department_filter)

    if not reranked_nodes:
        return QueryResult(
            answer=(
                "I couldn't find anything in the available department "
                "documents that answers this question. It may be outside "
                "the scope of what's been indexed, or phrased differently "
                "than how it appears in the source documents."
            ),
            departments_used=[],
            sources=[],
        )

    context_blocks = []
    sources = []
    departments_seen = set()

    for node in reranked_nodes:
        dept = node.node.metadata.get("department", "unknown")
        source_file = node.node.metadata.get("source_file", "unknown")
        departments_seen.add(dept)
        context_blocks.append(
            f"[Source: {source_file} | Department: {dept}]\n{node.node.get_content()}"
        )
        sources.append({
            "text": node.node.get_content(),
            "department": dept,
            "source_file": source_file,
            "score": round(node.score, 4) if node.score is not None else None,
        })

    context_str = "\n\n---\n\n".join(context_blocks)

    prompt = f"""You are an internal assistant answering employee questions using ONLY the provided company document excerpts below. Do not use any outside knowledge.

Rules:
- Answer using only the information in the excerpts below.
- If the excerpts don't fully answer the question, say so explicitly rather than guessing.
- When relevant, mention which department's policy the answer comes from.
- Be concise and direct.

Document excerpts:
{context_str}

Question: {question}

Answer:"""

    response = Settings.llm.complete(prompt)

    return QueryResult(
        answer=str(response).strip(),
        departments_used=sorted(departments_seen),
        sources=sources,
    )


if __name__ == "__main__":
    # Quick manual test when running this file directly.
    print("Testing query_engine.py...\n")

    test_questions = [
        ("What is the leave carry-forward limit for privilege leave?", ["hr"]),
        ("What is our data retention policy for personal data?", None),
        ("What is the capital of France?", None),  # should abstain
    ]

    for q, dept_filter in test_questions:
        print(f"Q: {q}")
        print(f"   (department filter: {dept_filter})")
        result = query(q, department_filter=dept_filter)
        print(f"A: {result.answer}")
        print(f"   Departments used: {result.departments_used}")
        print(f"   Sources: {[s['source_file'] for s in result.sources]}")
        print()
