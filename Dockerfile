# One image for all six GridMind services. GRIDMIND_ROLE selects the role at
# runtime (see server.py), so a single build serves the whole system.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first: this layer is cached across rebuilds, so an edit to agent
# code does not reinstall the SDKs.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agents/ ./agents/
COPY seed/ ./seed/
COPY server.py .

# Non-root. Nothing here needs write access to the filesystem, and the only
# credential in play is the Cloud Run service identity from the metadata
# server -- there are no key files to protect.
RUN useradd --create-home --uid 1000 gridmind && chown -R gridmind:gridmind /app
USER gridmind

ENV PORT=8080
EXPOSE 8080

# Single worker per container: Cloud Run scales by adding instances, and the
# harness already runs the four specialists concurrently with threads. Extra
# workers would multiply memory for no throughput gain on this workload.
CMD exec uvicorn server:app --host 0.0.0.0 --port ${PORT} --workers 1 --timeout-keep-alive 300
