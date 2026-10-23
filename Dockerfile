FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
RUN useradd --create-home --uid 1000 app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY troubleshooter ./troubleshooter
COPY eval ./eval
COPY data ./data

# Bake the embedding model and FAISS index into the image so containers
# start without network access to Hugging Face and without a warm-up step.
RUN python -m troubleshooter.cli --build-index && chown -R app:app /app

ENV HF_HUB_OFFLINE=1
USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

CMD ["uvicorn", "troubleshooter.api:app", "--host", "0.0.0.0", "--port", "8000"]
