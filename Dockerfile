# Multi-stage Dockerfile for Terraable backend API server
# Build stage: Install dependencies with Poetry
FROM python:3.11-slim as builder

WORKDIR /build

# Install Poetry and dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /root/.local/bin/poetry /usr/local/bin/poetry

# Copy only dependency files first (for better layer caching)
COPY pyproject.toml poetry.lock* ./

# Install dependencies (without dev dependencies for production)
RUN poetry config virtualenvs.create false && \
    poetry install --no-dev --no-directory

# Runtime stage: Minimal image with only runtime dependencies
FROM python:3.11-slim

WORKDIR /app

# Install only runtime dependencies (Ansible, Terraform, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -s /bin/bash terraable

# Copy installed packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=terraable:terraable . .

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app:$PATH"

# Switch to non-root user
USER terraable

# Expose API server port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1

# Default command: start API server
# Mount workspace root at /workspace if custom environment needed
CMD ["python", "-m", "terraable.api_server", "--host", "0.0.0.0", "--port", "8000", "--workspace", "/app"]
