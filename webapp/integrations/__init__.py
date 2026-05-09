"""
Integrations — clientes HTTP a servicios externos.
===================================================

Cada integration vive en su propio módulo:

- base.py   → BaseHTTPClient compartido (retries, timeouts, auth, logs).
- fal.py    → FLUX / Kling / Runway / WAN / Real-ESRGAN / mmaudio / TTS
              (Commit 9).
- suno.py   → gcui-art/suno-api — música original (Commit 10).

Todos los clients heredan de `BaseHTTPClient` — no hay llamadas HTTP
crudas (httpx.Client() directo) fuera de este módulo.
"""

from webapp.integrations.base import (
    BaseHTTPClient,
    HTTPClientError,
    RateLimitError,
    RetryableError,
)
from webapp.integrations.fal import (
    FAL_MODEL_IDS,
    FalClient,
    FalJobFailed,
    FalJobResult,
    FalJobTimeout,
)
from webapp.integrations.suno import (
    SunoClient,
    SunoClip,
    SunoClipFailed,
    SunoTimeout,
)

__all__ = [
    # base
    "BaseHTTPClient",
    "HTTPClientError",
    "RateLimitError",
    "RetryableError",
    # fal
    "FalClient",
    "FalJobResult",
    "FalJobFailed",
    "FalJobTimeout",
    "FAL_MODEL_IDS",
    # suno
    "SunoClient",
    "SunoClip",
    "SunoClipFailed",
    "SunoTimeout",
]
