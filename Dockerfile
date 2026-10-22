# One image for both the web service and the research worker (different start commands).
# TabPFN/Torch ("ranking" extra) are intentionally not installed: the demo uses the
# transparent baseline ranking. See docs/DEPLOYMENT.md.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY migrations ./migrations
COPY scripts ./scripts
RUN pip install ".[ui]" && useradd --create-home app
USER app
ENV APP_ENV=demo
# Web by default; the worker overrides this with scripts/research_worker.py.
CMD ["python", "scripts/serve.py"]
