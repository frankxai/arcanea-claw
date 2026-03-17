# ArcaneaClaw — Podman Containerfile (OCI-compliant)
# Python 3.11 + Node 20 + FFmpeg + Pillow
# Lightweight — runs on old laptop (2GB RAM / 2 CPUs)
# Rootless by default — no daemon, no sudo at runtime

FROM python:3.11-slim

LABEL maintainer="FrankX <frank@arcanea.ai>"
LABEL org.opencontainers.image.title="ArcaneaClaw"
LABEL org.opencontainers.image.description="Arcanea media processing engine — scan, classify, transform, upload"
LABEL org.opencontainers.image.source="https://github.com/frankxai/arcanea"
LABEL org.opencontainers.image.vendor="Arcanea"
LABEL io.containers.autoupdate="registry"

# Install system deps — pin Node 20 via nodesource for consistency
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
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

WORKDIR /app

# Install Python deps (layer cached separately from app code)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Node deps (layer cached separately from app code)
COPY package.json .
RUN npm install --production --ignore-scripts && npm cache clean --force

# Copy application code
COPY engine/ /app/engine/
COPY skills/ /app/skills/
COPY config.yaml /app/config.yaml

# Create non-root user for rootless operation
RUN groupadd -r claw && useradd -r -g claw -d /app -s /sbin/nologin claw \
    && mkdir -p /data/source /data/staging /data/processed /app/canon \
    && chown -R claw:claw /app /data

USER claw

EXPOSE 8080

# Health check — lightweight curl every 30s
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

CMD ["python", "engine/daemon.py"]
