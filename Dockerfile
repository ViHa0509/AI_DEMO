# AI Learning Assistant: web UI + LangGraph backend.
# Built by GitHub Actions (smoke test) and by Hugging Face Spaces (deployment).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/user \
    HF_HOME=/home/user/.cache/huggingface \
    HOST=0.0.0.0 \
    PORT=7860

# Hugging Face Spaces runs containers as uid 1000
RUN useradd --create-home --uid 1000 user
WORKDIR /home/user/app

# CPU-only torch keeps the image ~1.5 GB smaller than the default CUDA build
COPY requirements.txt .
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r requirements.txt

USER user
COPY --chown=user . .

# Download the embedding model and pre-build the knowledge-base index into the image,
# so the container starts fast and needs no database
RUN python -m app.knowledge_base

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/api/health', timeout=4)"
CMD ["python", "-m", "app.server"]
