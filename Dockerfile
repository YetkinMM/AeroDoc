FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements-docker.lock.txt ./
RUN python -m pip install --no-cache-dir -r requirements-docker.lock.txt \
    && python -m pip check \
    && groupadd --gid 10001 aerodoc \
    && useradd --no-create-home --uid 10001 --gid 10001 aerodoc \
    && mkdir -p audit/chunking audit/retrieval audit/answers

COPY config/answers.json config/retrieval.json ./config/
COPY scripts/ask_api.py scripts/answering.py scripts/openai_answers.py scripts/retrieval.py ./scripts/
COPY web/index.html web/styles.css web/demo.js web/examples.json ./web/

USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "scripts.ask_api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
