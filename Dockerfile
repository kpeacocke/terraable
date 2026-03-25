# Multi-stage Dockerfile for Terraable backend API server
# Build stage: Install dependencies with Poetry
FROM python:3.11-slim AS builder

WORKDIR /build

# Install Poetry and dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry into a fixed path so it is available in the builder stage
ENV POETRY_HOME=/opt/poetry
ARG POETRY_VERSION=1.8.5
RUN pip install --no-cache-dir "poetry==$POETRY_VERSION" && \
    mkdir -p "$POETRY_HOME/bin" && \
    ln -sf /usr/local/bin/poetry "$POETRY_HOME/bin/poetry"
ENV PATH="$POETRY_HOME/bin:$PATH"

# Copy only dependency files first (for better layer caching)
COPY pyproject.toml poetry.lock* ./

# Install dependencies (without dev dependencies for production)
RUN poetry config virtualenvs.create false && \
    poetry install --no-root --only main

# Runtime stage: Minimal image with only runtime dependencies
FROM python:3.11-slim

ARG TERRAFORM_VERSION=1.9.0
# TARGETARCH is set automatically by Docker BuildKit (amd64, arm64, etc.)
ARG TARGETARCH=amd64

WORKDIR /workspace

# Install runtime dependencies and Terraform CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    curl \
    ca-certificates \
    unzip \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -s /bin/bash terraable \
    && curl -fsSL "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_${TARGETARCH}.zip" -o /tmp/terraform.zip \
    && unzip /tmp/terraform.zip -d /usr/local/bin \
    && chmod +x /usr/local/bin/terraform \
    && rm -f /tmp/terraform.zip

# Copy only installed Python packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copy application code
COPY --chown=terraable:terraable . .

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/workspace:$PATH"

# Switch to non-root user
USER terraable

# Expose API server port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1

# Default command: start API server with workspace at /workspace
CMD ["python", "-m", "terraable.api_server", "--host", "0.0.0.0", "--port", "8000", "--workspace", "/workspace"]
