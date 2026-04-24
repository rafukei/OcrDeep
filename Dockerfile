FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for pdf2image + Pillow
RUN apt-get update && apt-get install -y \
    poppler-utils \
    libsm6 \
    libxext6 \
    libxrender1 \
    libjpeg62-turbo \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Modal CLI (for local development / token setup)
RUN pip install modal

# Copy application code
COPY app.py modal_worker.py .env.example ./

# Expose FastAPI port (port 7000 as specified)
EXPOSE 7000

# Shared volume mount point (for Modal file exchange)
ENV SHARED_DIR=/tmp/modal-ocr-mcp

# Default command: run FastAPI server
CMD ["python", "app.py"]
