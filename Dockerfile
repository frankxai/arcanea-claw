# ============================================================================
# ArcaneaClaw — The Claw Fleet Engine
#
# One image, many profiles. Set CLAW_PROFILE to run different claws:
#   docker run -e CLAW_PROFILE=media  arcanea-claw
#   docker run -e CLAW_PROFILE=forge  arcanea-claw
#   docker run -e CLAW_PROFILE=herald arcanea-claw
#
# Multi-stage build, ~200MB final image, non-root user.
# ============================================================================

# ── Stage 1: Builder ─────────────────────────────────────────────────────────

FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────

FROM python:3.11-slim AS runtime

LABEL maintainer="FrankX <frank@arcanea.ai>"
LABEL org.opencontainers.image.title="ArcaneaClaw Fleet Engine"
LABEL org.opencontainers.image.description="5 specialized AI engines: Media, Forge, Herald, Scout, Scribe"
LABEL org.opencontainers.image.url="https://arcanea.ai/claw"
LABEL org.opencontainers.image.source="https://github.com/frankxai/arcanea-claw"
LABEL org.opencontainers.image.version="0.3.0"

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl ca-certificates \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python packages from builder
COPY --from=builder /install /usr/local

# Application code
COPY engine/ /app/engine/
COPY profiles/ /app/profiles/
COPY config.yaml /app/config.yaml
COPY deploy/railway-setup.sh /app/setup.sh

# Non-root user + data dirs
RUN groupadd -r claw && useradd -r -g claw -d /app -s /sbin/nologin claw \
    && mkdir -p /data/source /data/staging /data/processed /data/logs \
                /data/nft-raw /data/nft-composed /data/nft-metadata /data/nft-layers \
    && chmod +x /app/setup.sh \
    && chown -R claw:claw /app /data

VOLUME ["/data"]

USER claw

EXPOSE 8080

# Default: production JSON logs
ENV LOG_FORMAT=json
ENV CLAW_PROFILE=media
ENV PORT=8080

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -sf http://localhost:${PORT}/health || exit 1

# Entrypoint: setup script + daemon with profile from env
CMD ["/bin/sh", "-c", "/app/setup.sh && python -m engine.cli run --profile ${CLAW_PROFILE} --port ${PORT} --json-logs"]
