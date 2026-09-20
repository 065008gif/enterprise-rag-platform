"""
FastAPI backend for the Enterprise Policy RAG project.

Wraps rag/router_agent.py's route_query() function as a REST API so a
frontend (React or otherwise) can send a question and get back a JSON
response with the answer, departments used, and source citations.

Endpoints:
    POST /api/query        - main query endpoint
    GET  /api/departments   - list of department names
    GET  /health            - health check

Run locally:
    uvicorn rag.app:app --reload --host 0.0.0.0 --port 8000

Then test with:
    curl -X POST http://localhost:8000/api/query \
      -H "Content-Type: application/json" \
      -d '{"question": "What is the leave carry-forward limit?"}'
"""

import sys
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

from rag.config import DEPARTMENTS
from rag.router_agent import route_query


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("enterprise-rag-api")

app = FastAPI(title="Enterprise Policy RAG API", version="1.0")

# Allow requests from any origin during development. Tighten this to a
# specific frontend URL once deployed, if desired.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------
# Request / response schemas
# --------------------------------------------------------------------

class QueryRequest(BaseModel):
    question: str


class SourceItem(BaseModel):
    text: str
    department: str
    source_file: str
    score: Optional[float] = None


class QueryResponse(BaseModel):
    answer: str
    departments_used: list
    sources: list
    classification_confident: bool
    response_time_seconds: float


# --------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/departments")
def get_departments():
    return {"departments": DEPARTMENTS}


@app.post("/api/query", response_model=QueryResponse)
def post_query(request: QueryRequest):
    question = request.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="Question must not be empty.")

    logger.info(f"Received query: {question!r}")
    start_time = time.time()

    try:
        result = route_query(question)
    except Exception as e:
        logger.exception(f"Error processing query: {question!r}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while processing the query: {type(e).__name__}: {e}",
        )

    elapsed = time.time() - start_time
    logger.info(f"Query completed in {elapsed:.2f}s, "
                f"departments={result.departments_used}, "
                f"sources={len(result.sources)}")

    return QueryResponse(
        answer=result.answer,
        departments_used=result.departments_used,
        sources=[SourceItem(**s).dict() for s in result.sources],
        classification_confident=result.classification_confident,
        response_time_seconds=round(elapsed, 2),
    )


# --------------------------------------------------------------------
# Serve the built React frontend, if present, as static files.
# This lets one server host both the API and the UI. If the frontend
# hasn't been built yet, this is silently skipped so the API still
# works standalone.
# --------------------------------------------------------------------

_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
    logger.info(f"Serving frontend from {_frontend_dist}")
else:
    logger.info(f"No built frontend found at {_frontend_dist} - API-only mode.")
