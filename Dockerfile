FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev tesseract-ocr tesseract-ocr-eng tesseract-ocr-fas tesseract-ocr-ara \
    qpdf ghostscript libreoffice-writer libreoffice-calc libreoffice-impress \
    fonts-noto-core fonts-noto-extra fonts-noto-cjk fonts-dejavu-core \
    libjpeg62-turbo libpng16-16 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install --no-cache-dir '.[ocr]' && \
    useradd --create-home --uid 10001 --shell /usr/sbin/nologin pdfbot && \
    mkdir -p /data/files /tmp/pdfbot && chown -R 10001:10001 /data /tmp/pdfbot /app
USER 10001:10001
ENV HOME=/tmp PYTHONPATH=/app
EXPOSE 8000
CMD ["python", "-m", "app.main"]
