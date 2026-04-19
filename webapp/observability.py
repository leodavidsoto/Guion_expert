"""
Logging estructurado con structlog — Guion_expert
====================================================
- Desarrollo local: consola con colores, legible.
- Producción (Docker o LOG_FORMAT=json): JSON line-delimited, listo para
  ingestar en Grafana Loki, Datadog, CloudWatch, etc.
- Context vars: cada log puede traer `pipeline_id`, `trace_id`, `expert`,
  etc. automáticamente gracias a contextvars — no hay que pasarlos como
  argumento en cada llamada.

Formato automático:
    - Si `LOG_FORMAT=json`  → JSON
    - Si `GUION_RUNTIME=docker` → JSON
    - Si no → consola con colores

Uso típico:

    from observability import (
        configure_logging, get_logger, bind_pipeline_context,
    )

    configure_logging()   # llamar UNA vez al arrancar
    log = get_logger(__name__)

    log.info("app_started", version="1.0")

    with bind_pipeline_context(pipeline_id="pipe-abc-123"):
        log.info("stage_start", stage="concepto")
        # output incluye automáticamente pipeline_id=pipe-abc-123
"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import contextmanager
from typing import Any, Iterator

import structlog


# ============================================================
# Configuración principal
# ============================================================


def configure_logging(
    *,
    level: str | None = None,
    format_type: str | None = None,
) -> None:
    """Configura structlog para toda la app. Llamar UNA vez al arrancar.

    Args:
        level: DEBUG | INFO | WARNING | ERROR. Default: env LOG_LEVEL o INFO.
        format_type: 'json' | 'console'. Default: JSON si corre en Docker
            o LOG_FORMAT=json, si no console con colores.
    """
    level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()

    if format_type is None:
        format_type = os.getenv(
            "LOG_FORMAT",
            "json" if os.getenv("GUION_RUNTIME") == "docker" else "console",
        )

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if format_type == "json":
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level)
        ),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Devuelve un logger structlog. Típicamente `log = get_logger(__name__)`."""
    return structlog.get_logger(name)


# ============================================================
# Contexto de pipeline (pipeline_id, trace_id, expert, etc.)
# ============================================================


@contextmanager
def bind_pipeline_context(**kwargs: Any) -> Iterator[None]:
    """Inyecta variables en todos los logs del bloque.

    Ejemplo:
        with bind_pipeline_context(pipeline_id="abc", expert="dialoguista"):
            log.info("start")
            # log tiene pipeline_id y expert automáticamente
    """
    structlog.contextvars.bind_contextvars(**kwargs)
    try:
        yield
    finally:
        structlog.contextvars.unbind_contextvars(*kwargs.keys())


def clear_context() -> None:
    """Limpia todo el contexto (útil entre requests HTTP)."""
    structlog.contextvars.clear_contextvars()


# ============================================================
# Integración con Flask
# ============================================================


def init_flask_logging(app: Any) -> None:
    """Integra structlog con Flask: trace_id por request + start/end logs.

    Uso:
        from observability import configure_logging, init_flask_logging
        configure_logging()
        app = Flask(__name__)
        init_flask_logging(app)
    """
    from uuid import uuid4
    from flask import g, request

    log = get_logger("http")

    @app.before_request
    def _before_request() -> None:
        trace_id = request.headers.get("X-Trace-Id", str(uuid4()))
        g.trace_id = trace_id
        structlog.contextvars.bind_contextvars(
            trace_id=trace_id,
            method=request.method,
            path=request.path,
        )
        # No loguear /api/health (es muy ruidoso — healthcheck del container)
        if request.path != "/api/health":
            log.info("request_start")

    @app.after_request
    def _after_request(response):
        if request.path != "/api/health":
            log.info("request_end", status=response.status_code)
        structlog.contextvars.clear_contextvars()
        return response


if __name__ == "__main__":
    # Smoke test: python -m webapp.observability
    configure_logging()
    log = get_logger(__name__)
    log.info("smoke_test", message="structlog configurado correctamente")
    with bind_pipeline_context(pipeline_id="pipe-test-123", expert="dialoguista"):
        log.info("context_test", stage="concepto")
