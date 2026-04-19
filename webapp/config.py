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

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


# Buscar .env en la raíz del proyecto (un nivel arriba de webapp/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


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

    # --- Validación cruzada (después de cargar todos los campos) ---
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

    # --- Helpers ---
    def is_claude(self) -> bool:
        return self.llm_provider == "claude"

    def is_ollama(self) -> bool:
        return self.llm_provider == "ollama"


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
