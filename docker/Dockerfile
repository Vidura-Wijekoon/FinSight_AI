# 3.11 matches the version CI tests against and the floor stated in the README.
# The pinned dependency set is verified on 3.11 only; shipping 3.12 meant the
# published artefact ran a different minor version to the one under test.
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for document processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Create required directories
RUN mkdir -p data/uploads data/processed logs keys chroma_db

# Expose API port
EXPOSE 8000

# Default: API server
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
