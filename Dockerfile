# =============================================================
# Guion_expert — Dockerfile multietapa
# =============================================================
# Etapa 1 (builder): instala deps en un venv aislado.
# Etapa 2 (runtime): imagen final liviana con solo lo necesario.
#
# Build:    docker build -t guion-expert:latest .
# Run:      docker compose up -d
# =============================================================

# ----------- Etapa 1: builder -----------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Dependencias de compilación (algunas wheels de Pydantic/structlog las piden)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# venv aislado
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Instalar deps en capa cacheable
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt


# ----------- Etapa 2: runtime -----------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    GUION_RUNTIME=docker \
    LOG_FORMAT=json

# Runtime deps:
#   - ffmpeg: procesamiento video/audio (bridge OpenMontage, lipsync futuro)
#   - curl:   healthchecks
#   - tini:   init mínimo para manejo correcto de SIGTERM
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Usuario no-root (best practice de seguridad)
RUN groupadd -r guion && useradd -r -g guion -u 1000 guion

# Copiar venv desde builder
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# Copiar código de la app (respeta .dockerignore)
COPY --chown=guion:guion . .

# Crear directorios que se van a montar como volúmenes (con permisos correctos)
RUN mkdir -p output logs webapp/uploads && \
    chown -R guion:guion output logs webapp/uploads

USER guion

EXPOSE 5001

# Healthcheck — usa $PORT si Railway lo inyecta, cae a 5001 si no.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-5001}/api/health || exit 1

# tini como init para manejar señales correctamente
ENTRYPOINT ["/usr/bin/tini", "--"]

# Entry point del server (igual a ejecución local)
CMD ["python", "webapp/server.py"]
