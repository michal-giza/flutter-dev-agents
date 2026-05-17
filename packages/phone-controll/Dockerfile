# mcp-phone-controll — CI / headless server image
#
# Two ways to use this:
#   1. HTTP MCP server (this is the default ENTRYPOINT):
#        docker run -p 8765:8765 \
#          -e MCP_HTTP_API_KEY=mysecret \
#          ghcr.io/michal-giza/mcp-phone-controll:0.2.0
#      Hit http://localhost:8765/health, /ready, /metrics, /tools.
#
#   2. Stdio MCP for headless CI agents (override ENTRYPOINT):
#        docker run -i ghcr.io/michal-giza/mcp-phone-controll:0.2.0 \
#          python -m mcp_phone_controll
#
# Doesn't include iOS support (Apple-side toolchain isn't
# containerisable). Android emulator support requires a second
# container running the emulator + adb; see
# docs/runbook.md#docker-android-ci.
#
# Image size optimisation: multi-stage with a slim runtime base,
# wheel cache from the builder stage. Final image is ~280 MB.

ARG PYTHON_VERSION=3.11

# ---------- builder stage ----------
FROM python:${PYTHON_VERSION}-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src

# Install with the extras a CI box needs: dev (pytest, ruff), ar
# (cv2 for image-cap latency tests), http (FastAPI for the HTTP
# adapter). Skip rag (qdrant) + debug (websockets) + ios — they're
# specialised.
RUN pip install --no-cache-dir --upgrade pip && \
    pip wheel --no-cache-dir --wheel-dir /wheels -e ".[dev,ar,http]"

# ---------- runtime stage ----------
FROM python:${PYTHON_VERSION}-slim AS runtime

# Runtime deps: adb (Android), git (patch_apply_safe), bash (run scripts),
# curl (debugging). NO iOS toolchain — Apple-only and unsupported on Linux.
RUN apt-get update && apt-get install -y --no-install-recommends \
        adb \
        git \
        bash \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Run as a non-root user. Closes the residual risk in ADR-0006: an
# RCE through patch_apply_safe (none known) shouldn't escalate to
# anything beyond this user's permissions.
RUN groupadd --gid 1000 mcp && \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash mcp

WORKDIR /app
COPY --chown=mcp:mcp pyproject.toml README.md ./
COPY --chown=mcp:mcp src ./src
COPY --from=builder /wheels /wheels

# Install from the local wheel cache for speed.
RUN pip install --no-cache-dir --no-index --find-links /wheels mcp-phone-controll && \
    rm -rf /wheels

USER mcp

# The HTTP adapter expects to bind to 0.0.0.0:8765 by default; the
# Kubernetes deployment overrides via $PORT.
ENV PORT=8765 \
    PYTHONUNBUFFERED=1 \
    MCP_LOG_FORMAT=json

EXPOSE 8765

# Healthcheck uses the /health endpoint. 5s startup grace, 30s
# interval, fail after 3 misses.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -fsS http://localhost:${PORT}/health || exit 1

# Default entrypoint: HTTP server. Override with `docker run ... python -m mcp_phone_controll`
# for stdio mode.
ENTRYPOINT ["python", "-m", "mcp_phone_controll.adapters"]
