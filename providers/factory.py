"""
providers/factory.py — Selección y composición de providers.

Entrega al resto del sistema un único punto de entrada:

    from providers import get_provider

    provider = get_provider()  # lee .env, decide, cachea
    result = provider.generate_i2v(...)

Comportamiento por .env:

    TRINITY_ENABLED=false  (default)
        → devuelve FalProvider puro. Cero chance de tocar Trinity.

    TRINITY_ENABLED=true
        → devuelve ChainedProvider:
          1. intenta Trinity
          2. si Trinity falla con retriable=True, cae a Fal
          3. si Fal también falla, propaga el último error

    TRINITY_ENABLED=true, TRINITY_STRICT=true
        → devuelve TrinityProvider puro (sin fallback). Útil para tests
          o para asegurar que no se consuman créditos fal.

Además, `resolve_provider_for_scene(veo_scene)` es un helper que respeta
`preferred_backend` emitido por el director_flow — permite que escenas
críticas fuercen fal aunque Trinity esté habilitado globalmente.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from .base import GenerationResult, ProviderError, VideoProvider
from .fal_provider import FalProvider
from .trinity_provider import TrinityProvider

log = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────
# Provider compuesto: Trinity → Fal (con fallback)
# ────────────────────────────────────────────────────────────────────────

class ChainedProvider(VideoProvider):
    """Trinity primary + Fal fallback. Se usa cuando TRINITY_ENABLED=true."""

    name = "fal"  # reportamos fal por default (ChainedProvider es transparente)

    def __init__(self, primary: VideoProvider, fallback: VideoProvider):
        self.primary = primary
        self.fallback = fallback

    def is_healthy(self) -> bool:
        # "Sano" si al menos uno de los dos responde.
        return self.primary.is_healthy() or self.fallback.is_healthy()

    def _try_then_fallback(self, method_name: str, *args, **kwargs) -> GenerationResult:
        # 1. Intentar primary si está sano
        if self.primary.is_healthy():
            try:
                return getattr(self.primary, method_name)(*args, **kwargs)
            except ProviderError as e:
                if not e.retriable:
                    # Error duro (modelo no soportado, bad request): no caer,
                    # re-raise para que el director lo vea.
                    raise
                log.warning(
                    "primary_provider_failed",
                    extra={"primary": self.primary.name, "error": str(e),
                           "falling_back_to": self.fallback.name},
                )
            except Exception as e:
                log.warning(
                    "primary_provider_unexpected",
                    extra={"primary": self.primary.name, "error": str(e),
                           "falling_back_to": self.fallback.name},
                )

        # 2. Fallback
        return getattr(self.fallback, method_name)(*args, **kwargs)

    def generate_i2v(self, *args, **kwargs) -> GenerationResult:
        return self._try_then_fallback("generate_i2v", *args, **kwargs)

    def generate_t2v(self, *args, **kwargs) -> GenerationResult:
        return self._try_then_fallback("generate_t2v", *args, **kwargs)


# ────────────────────────────────────────────────────────────────────────
# Singleton cache (evita reconstruir providers por escena)
# ────────────────────────────────────────────────────────────────────────

_provider_cache: Optional[VideoProvider] = None


def _read_env_flag(name: str, default: bool = False) -> bool:
    v = os.getenv(name, "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


def get_provider(force_reload: bool = False) -> VideoProvider:
    """Devuelve el provider configurado según .env (cacheado).

    Args:
        force_reload: si True, reconstruye el cache (útil en tests).
    """
    global _provider_cache
    if _provider_cache is not None and not force_reload:
        return _provider_cache

    trinity_enabled = _read_env_flag("TRINITY_ENABLED", default=False)
    trinity_strict = _read_env_flag("TRINITY_STRICT", default=False)

    fal = FalProvider()

    if not trinity_enabled:
        log.info("provider_selected", extra={"provider": "fal", "trinity_enabled": False})
        _provider_cache = fal
        return fal

    trinity = TrinityProvider()

    if trinity_strict:
        log.info("provider_selected", extra={"provider": "trinity", "strict": True})
        _provider_cache = trinity
        return trinity

    # Default cuando Trinity está habilitado: chained (trinity → fal)
    chained = ChainedProvider(primary=trinity, fallback=fal)
    log.info("provider_selected", extra={"provider": "chained:trinity+fal"})
    _provider_cache = chained
    return chained


def resolve_provider_for_scene(veo_scene: dict) -> VideoProvider:
    """Respeta `preferred_backend` del director_flow para esta escena.

    Si el director emitió "preferred_backend: fal" y el global está en
    Trinity, esta función devuelve un FalProvider puro solo para esta
    escena — útil para escenas críticas que NO pueden fallar.

    Args:
        veo_scene: dict VeoPrompt (o master_stack del scene_plan).

    Returns:
        VideoProvider a usar para esta escena específica.
    """
    # Puede venir del VeoPrompt top-level o del master_stack del scene_plan.
    preferred = (
        veo_scene.get("preferred_backend")
        or (veo_scene.get("master_stack") or {}).get("preferred_backend")
        or "auto"
    ).lower()

    if preferred == "fal":
        return FalProvider()
    if preferred == "trinity":
        t = TrinityProvider()
        if not t.is_healthy():
            log.warning("scene_forced_trinity_but_unhealthy_falling_back_fal")
            return FalProvider()
        return t
    # auto → usar el provider global
    return get_provider()
