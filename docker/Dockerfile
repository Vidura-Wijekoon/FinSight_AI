# 3.11 matches the version CI tests against and the floor stated in the README.
# The pinned dependency set is verified on 3.11 only; shipping 3.12 meant the
# published artefact ran a different minor version to the one under test.
#
# Multi-stage, for vulnerability surface rather than image size. The previous
# single-stage build shipped gcc and its toolchain — binutils, cpp, libc-dev —
# in the runtime image. None of it is needed to run the service, and all of it
# is scanned. Compiling happens in the builder, which is then discarded.

# ---------------------------------------------------------------------------
# Builder — compiles any dependency without a prebuilt wheel, then is discarded
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

# pip and setuptools as shipped in the base image routinely carry their own
# fixable advisories, so they are updated before anything is installed with them.
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install --prefix=/install -r requirements.txt

# ---------------------------------------------------------------------------
# Runtime — no compiler, base patched to current Debian security updates
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# The base tag is rebuilt periodically, not continuously, so it lags Debian
# security updates. Applying them here is what keeps the scan clean between
# base image refreshes.
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip setuptools wheel

# Installed packages and entry point scripts from the builder. /usr/local is
# already on sys.path and PATH in this image.
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy source code. .dockerignore keeps keys/, .env, data/ and chroma_db/ out.
COPY . .

# Create required directories
RUN mkdir -p data/uploads data/processed logs keys chroma_db

# Expose API port
EXPOSE 8000

# Default: API server
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
