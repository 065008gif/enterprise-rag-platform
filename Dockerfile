FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (better Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project
COPY rag/ ./rag/
COPY frontend/dist/ ./frontend/dist/

EXPOSE 8080

CMD exec uvicorn rag.app:app --host 0.0.0.0 --port ${PORT:-8080}
