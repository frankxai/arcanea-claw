# ============================================================================
# ArcaneaClaw — Production Dockerfile (Railway + Docker + Podman)
#
# Multi-stage build: builder installs deps, runtime copies only what's needed.
# Target: ~200MB final image. Runs as non-root user "claw".
# ============================================================================

# ── Stage 1: Builder ─────────────────────────────────────────────────────────

FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
       | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
       > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Python deps — cached layer
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Node deps — cached layer
COPY package.json .
RUN npm install --production --ignore-scripts \
    && npm cache clean --force

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────

FROM python:3.11-slim AS runtime

LABEL maintainer="FrankX <frank@arcanea.ai>"
LABEL org.opencontainers.image.title="ArcaneaClaw"
LABEL org.opencontainers.image.description="AI-powered media processing engine — scan, classify, score, transform, upload"
LABEL org.opencontainers.image.url="https://arcanea.ai"
LABEL org.opencontainers.image.source="https://github.com/frankxai/arcanea-claw"
LABEL org.opencontainers.image.vendor="Arcanea"
LABEL org.opencontainers.image.version="0.1.0"
LABEL railway.template="arcanea-claw"

# System deps — only what runtime needs (no build tools, no gnupg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
       | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
       > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get purge -y gnupg \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* /etc/apt/sources.list.d/nodesource.list /etc/apt/keyrings/nodesource.gpg

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /install /usr/local

# Copy Node modules from builder
COPY --from=builder /build/node_modules /app/node_modules

# Copy application code
COPY engine/ /app/engine/
COPY skills/ /app/skills/
COPY skillpacks/ /app/skillpacks/
COPY config.yaml /app/config.yaml
COPY deploy/railway-setup.sh /app/setup.sh

# Create non-root user + persistent volume mount point
RUN groupadd -r claw && useradd -r -g claw -d /app -s /sbin/nologin claw \
    && mkdir -p /data/source /data/staging /data/processed /data/logs /app/canon \
    && chmod +x /app/setup.sh \
    && chown -R claw:claw /app /data

# Railway persistent volume mount point
VOLUME ["/data"]

USER claw

EXPOSE 8080

# Health check — Railway uses /health endpoint, this is a fallback for Docker
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -sf http://localhost:8080/health || exit 1

# Run setup then start daemon
CMD ["/bin/sh", "-c", "/app/setup.sh && python engine/daemon.py"]
