"""
providers/ — Abstracción de backends de generación de video.

Expone una única interfaz `VideoProvider` que master_orchestrator y el
asset_generator consumen sin saber qué hay del otro lado:

    from providers import get_provider
    provider = get_provider()                # elige fal o trinity por .env
    result = provider.generate_i2v(image_path, prompt, model="kling-2.5-pro")
    # ó
    result = provider.generate_t2v(prompt, model="skyreels-v1")

Implementaciones:
    - FalProvider       → fal.ai API (Kling, Runway, WAN, Veo, Hailuo)
    - TrinityProvider   → HTTP client al notebook Colab (Wan/SkyReels/Hunyuan)
    - ChainedProvider   → prueba Trinity; si falla, cae a fal (default "auto")

Lectura de config: .env (TRINITY_ENABLED, TRINITY_URL, TRINITY_TOKEN, ...).
"""
from .base import VideoProvider, GenerationResult, ProviderError
from .factory import get_provider, resolve_provider_for_scene

__all__ = [
    "VideoProvider",
    "GenerationResult",
    "ProviderError",
    "get_provider",
    "resolve_provider_for_scene",
]
