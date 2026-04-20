"""
Configuración centralizada con validación fail-fast — Guion_expert
====================================================================
Carga toda la configuración desde .env (raíz del proyecto) y variables
de entorno, validando con Pydantic v2 que todo esté bien al ARRANQUE.

Si algo falta o está mal (ej. falta ANTHROPIC_API_KEY cuando
LLM_PROVIDER=claude), la app crashea inmediatamente con un error claro
en vez de fallar en el primer request del usuario.

Uso:
    from config import settings

    print(settings.claude_model)
    print(settings.anthropic_api_key.get_secret_value())

Smoke test:
    python -m webapp.config
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, PrivateAttr, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


# Buscar .env en la raíz del proyecto (un nivel arriba de webapp/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
EXPERTS_YAML = PROJECT_ROOT / "config" / "llm_provider.yaml"


# ============================================================
# Config per-expert (overrides opcionales de Claude params)
# ============================================================


class ExpertConfig(BaseModel):
    """Params del LLM por expert. Todos opcionales — caen a globales."""

    description: str = ""
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=200_000)


def _load_experts_yaml() -> dict[str, ExpertConfig]:
    """Carga config/llm_provider.yaml. Si no existe o está vacío, devuelve {}."""
    if not EXPERTS_YAML.exists():
        return {}
    try:
        raw = yaml.safe_load(EXPERTS_YAML.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"YAML inválido en {EXPERTS_YAML}: {e}")
    experts_data = raw.get("experts", {}) or {}
    return {name: ExpertConfig(**cfg) for name, cfg in experts_data.items()}


class Settings(BaseSettings):
    """Configuración global de Guion_expert con validación fail-fast."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE.exists() else None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # ignora variables de entorno no declaradas
    )

    # --- LLM provider activo ---
    llm_provider: Literal["claude", "ollama"] = Field(
        default="claude",
        description="Provider del LLM: claude (Anthropic) u ollama (local).",
    )

    # --- Claude (Anthropic) ---
    anthropic_api_key: SecretStr = Field(
        default=SecretStr(""),
        description="API key de Anthropic. Requerida si llm_provider=claude.",
    )
    claude_model: str = Field(
        default="claude-haiku-4-5-20251001",
        description="ID del modelo de Claude a usar.",
    )
    claude_max_tokens: int = Field(default=4096, ge=1, le=200_000)
    claude_temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    # --- Ollama (fallback opcional) ---
    ollama_host: str = Field(
        default="http://localhost:11434",
        description="URL del servidor Ollama (solo si llm_provider=ollama).",
    )

    # --- fal.ai (FLUX / Kling / Runway / WAN / Real-ESRGAN / mmaudio / TTS) ---
    fal_api_key: SecretStr = Field(
        default=SecretStr(""),
        description="API key de fal.ai (formato key_id:key_secret). "
        "Requerida cuando se usa el asset_generator.",
    )
    fal_base_url: str = Field(
        default="https://queue.fal.run",
        description="Base URL de la queue API de fal.ai.",
    )
    fal_poll_interval_s: float = Field(
        default=2.0,
        ge=0.5,
        le=60.0,
        description="Intervalo de polling al queue de fal.ai (s).",
    )
    fal_poll_max_wait_s: float = Field(
        default=900.0,
        ge=30.0,
        description="Tope absoluto de espera para un job de fal (s). 15min default.",
    )

    # --- FLUX / LoRA ---
    flux_lora_trigger: str = Field(
        default="",
        description="Trigger word del LoRA de identidad (ej. 3SM_BAND).",
    )
    flux_lora_url: str = Field(
        default="",
        description="URL del .safetensors entrenado. Se completa tras el primer train.",
    )
    flux_model: str = Field(
        default="fal-ai/flux-lora",
        description="Modelo FLUX default (con LoRA). Override en call site si hace falta.",
    )
    flux_steps: int = Field(default=28, ge=1, le=100)
    flux_guidance: float = Field(default=3.5, ge=1.0, le=20.0)
    flux_image_size: str = Field(
        default="portrait_16_9",
        description="Preset de fal. Para reels (vertical): portrait_16_9. "
        "Otros: landscape_16_9, square_hd, portrait_4_3.",
    )

    # --- I2V defaults (routing real en VIDEO_MODEL_ROUTING; esto es fallback) ---
    i2v_default_model: str = Field(
        default="fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
        description="Modelo I2V por defecto si el routing no matchea.",
    )
    i2v_default_duration_s: int = Field(default=5, ge=1, le=30)

    # --- Post-producción ---
    real_esrgan_scale: int = Field(default=2, ge=1, le=4)
    rife_target_fps: int = Field(default=60, ge=24, le=120)

    # --- Suno (gcui-art/suno-api self-hosted) ---
    suno_cookie: SecretStr = Field(
        default=SecretStr(""),
        description="Cookie completa de suno.com (Premium). Pasada al "
        "container suno-api como env var. Se refresca cada ~24h según "
        "lo que dure la sesión.",
    )
    suno_api_url: str = Field(
        default="http://suno-api:3000",
        description="URL del servicio suno-api dentro de la red docker. "
        "Para dev local corriendo fuera de compose: http://localhost:3000.",
    )
    suno_model: str = Field(
        default="chirp-v3-5",
        description="Modelo de Suno. Opciones: chirp-v3-0, chirp-v3-5, "
        "chirp-v4. v3-5 = mejor balance calidad/velocidad.",
    )
    suno_poll_interval_s: float = Field(default=5.0, ge=1.0, le=60.0)
    suno_poll_max_wait_s: float = Field(
        default=600.0,
        ge=60.0,
        description="Cap de espera para Suno (s). 10min default; una canción "
        "de 3-4min típicamente termina en 60-120s.",
    )
    suno_default_instrumental: bool = Field(
        default=False,
        description="Si True, toda generación arranca en modo instrumental "
        "por default (useful para reels sin letra).",
    )

    # --- HTTP client (integrations/base.py) ---
    http_timeout_connect: float = Field(
        default=10.0,
        ge=0.1,
        description="Timeout (s) al abrir conexión HTTP a integrations (fal, suno).",
    )
    http_timeout_read: float = Field(
        default=300.0,
        ge=0.1,
        description="Timeout (s) leyendo response. I2V puede tardar minutos.",
    )
    http_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Reintentos en 5xx/429 con backoff exponencial.",
    )
    http_backoff_base: float = Field(
        default=1.5,
        ge=0.1,
        description="Base (s) del backoff: base**attempt (1.5, 2.25, 3.38, ...).",
    )

    # --- Cache interno: experts cargados del YAML ---
    _experts: dict[str, ExpertConfig] = PrivateAttr(default_factory=dict)

    # --- Validación cruzada + carga de experts (después de cargar campos) ---
    def model_post_init(self, __context) -> None:
        if self.llm_provider == "claude":
            key = self.anthropic_api_key.get_secret_value().strip()
            if not key:
                raise ValueError(
                    "ANTHROPIC_API_KEY es requerida cuando LLM_PROVIDER=claude. "
                    f"Definila en {ENV_FILE} o como variable de entorno."
                )
            if "REEMPLAZAR" in key.upper():
                raise ValueError(
                    "ANTHROPIC_API_KEY tiene el valor placeholder de .env.example. "
                    "Reemplazala con tu key real de https://console.anthropic.com/"
                )

        # Cargar experts YAML (opcional — si falta, usamos globales)
        self._experts = _load_experts_yaml()

    # --- Helpers ---
    def is_claude(self) -> bool:
        return self.llm_provider == "claude"

    def is_ollama(self) -> bool:
        return self.llm_provider == "ollama"

    def expert_config(self, role: str | None) -> ExpertConfig | None:
        """Devuelve la config declarada del expert, o None si no hay override."""
        if not role:
            return None
        return self._experts.get(role)

    def params_for(self, role: str | None) -> tuple[int, float]:
        """Devuelve (max_tokens, temperature) efectivos para un expert role.

        Hace merge: override del YAML por-expert, cae a globales si falta.
        Si role es None o no está en el YAML, usa globales.
        """
        cfg = self.expert_config(role)
        if cfg is None:
            return (self.claude_max_tokens, self.claude_temperature)
        max_tokens = cfg.max_tokens if cfg.max_tokens is not None else self.claude_max_tokens
        temperature = (
            cfg.temperature if cfg.temperature is not None else self.claude_temperature
        )
        return (max_tokens, temperature)

    def known_experts(self) -> list[str]:
        """Lista de experts declarados en el YAML."""
        return sorted(self._experts.keys())


# Singleton — fail-fast: si algo está mal, crashea ACÁ al importar.
try:
    settings = Settings()
except Exception as exc:
    print("\n" + "=" * 60, file=sys.stderr)
    print("❌ ERROR DE CONFIGURACIÓN AL ARRANQUE", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"\n  {exc}\n", file=sys.stderr)
    print(f"  Archivo .env esperado en: {ENV_FILE}", file=sys.stderr)
    print(f"  Existe? {'sí' if ENV_FILE.exists() else 'NO'}", file=sys.stderr)
    print("\n  Pasos para arreglarlo:", file=sys.stderr)
    print("    1. cp .env.example .env", file=sys.stderr)
    print("    2. Editá .env y pegá tu ANTHROPIC_API_KEY", file=sys.stderr)
    print("    3. Reintentá", file=sys.stderr)
    print("=" * 60 + "\n", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    # Smoke test: python -m webapp.config
    key_len = len(settings.anthropic_api_key.get_secret_value())
    key_preview = (
        settings.anthropic_api_key.get_secret_value()[:12] + "..."
        if key_len > 0 else "(vacía)"
    )
    print("✅ Configuración cargada correctamente\n")
    print(f"  LLM_PROVIDER:        {settings.llm_provider}")
    print(f"  CLAUDE_MODEL:        {settings.claude_model}")
    print(f"  CLAUDE_MAX_TOKENS:   {settings.claude_max_tokens}")
    print(f"  CLAUDE_TEMPERATURE:  {settings.claude_temperature}")
    print(f"  OLLAMA_HOST:         {settings.ollama_host}")
    print(f"  API key:             {key_preview} ({key_len} chars)")

    experts = settings.known_experts()
    print(f"\n  Experts YAML: {EXPERTS_YAML}")
    print(f"  Cargados: {len(experts)}")
    for role in experts:
        mt, tp = settings.params_for(role)
        cfg = settings.expert_config(role)
        desc = (cfg.description[:40] + "…") if cfg and len(cfg.description) > 40 else (cfg.description if cfg else "")
        print(f"    - {role:<15} tokens={mt:<5} temp={tp:<4}  {desc}")
    # Sanity: expert desconocido cae a defaults
    mt, tp = settings.params_for("no_existe")
    print(f"\n  Fallback (role desconocido): tokens={mt} temp={tp}")
