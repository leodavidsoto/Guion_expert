"""
LLM Provider Adapter — Guion_expert
====================================
Reemplaza las llamadas a Ollama por Claude 3.5 Haiku (Anthropic API).

Uso:
    from llm_provider import generate

    for chunk in generate(model="cualquier-modelo", prompt="...", stream=True):
        print(chunk, end="")

Variables de entorno (via .env):
    ANTHROPIC_API_KEY         (requerida)
    LLM_PROVIDER              claude (default) | ollama
    CLAUDE_MODEL              claude-haiku-4-5-20251001 (default)
    CLAUDE_MAX_TOKENS         4096 (default)
    CLAUDE_TEMPERATURE        0.7 (default)

Mantiene una API compatible con el patrón `ollama run model prompt`
para que webapp/server.py pueda reemplazar subprocess con una llamada
directa y seguir haciendo streaming por SocketIO.
"""
from __future__ import annotations

import os
import subprocess
from typing import Iterator, Optional

# Intento de cargar .env automáticamente si python-dotenv está disponible
try:
    from dotenv import load_dotenv  # type: ignore
    # Busca .env en la raíz del proyecto (un nivel arriba de webapp/)
    from pathlib import Path
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass  # si no está instalado, seguimos con variables de entorno del shell


# --- Configuración global ----------------------------------------------------

PROVIDER = os.getenv("LLM_PROVIDER", "claude").lower()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001").strip()
CLAUDE_MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", "4096"))
CLAUDE_TEMPERATURE = float(os.getenv("CLAUDE_TEMPERATURE", "0.7"))


# --- Estado del provider -----------------------------------------------------

_claude_client = None


def _get_claude_client():
    """Lazy init del cliente Anthropic."""
    global _claude_client
    if _claude_client is None:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError(
                "ANTHROPIC_API_KEY no está configurada. "
                "Agrega tu key al archivo .env en la raíz del proyecto."
            )
        try:
            from anthropic import Anthropic  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "El paquete 'anthropic' no está instalado. "
                "Ejecuta: pip install anthropic python-dotenv"
            ) from e
        _claude_client = Anthropic(api_key=ANTHROPIC_API_KEY)
    return _claude_client


# --- API pública -------------------------------------------------------------

def is_available() -> bool:
    """Retorna True si el provider activo está listo para usarse."""
    if PROVIDER == "claude":
        return bool(ANTHROPIC_API_KEY)
    if PROVIDER == "ollama":
        return _ollama_available()
    return False


def provider_status() -> dict:
    """Información de estado para /api/health."""
    return {
        "provider": PROVIDER,
        "available": is_available(),
        "model": CLAUDE_MODEL if PROVIDER == "claude" else "ollama",
        "has_api_key": bool(ANTHROPIC_API_KEY),
    }


def generate(model: str, prompt: str, stream: bool = True) -> Iterator[str]:
    """
    Generador que produce chunks de texto del LLM.

    Args:
        model: nombre de modelo. Si provider=claude se ignora y usa CLAUDE_MODEL.
        prompt: prompt completo a enviar.
        stream: si True, yield chunks incrementales; si False, yield una sola vez.

    Yields:
        str: chunks de la respuesta.
    """
    if PROVIDER == "claude":
        yield from _generate_claude(prompt, stream=stream)
    elif PROVIDER == "ollama":
        yield from _generate_ollama(model, prompt, stream=stream)
    else:
        raise RuntimeError(f"LLM_PROVIDER desconocido: {PROVIDER}")


# --- Claude backend ----------------------------------------------------------

def _generate_claude(prompt: str, stream: bool = True) -> Iterator[str]:
    client = _get_claude_client()

    if stream:
        with client.messages.stream(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            temperature=CLAUDE_TEMPERATURE,
            messages=[{"role": "user", "content": prompt}],
        ) as stream_resp:
            for text_chunk in stream_resp.text_stream:
                yield text_chunk
    else:
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            temperature=CLAUDE_TEMPERATURE,
            messages=[{"role": "user", "content": prompt}],
        )
        # Concatenar todos los bloques de texto
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )
        yield text


# --- Ollama backend (fallback, opcional) -------------------------------------

def _ollama_available() -> bool:
    try:
        r = subprocess.run(["pgrep", "ollama"], capture_output=True)
        return r.returncode == 0
    except Exception:
        return False


def _generate_ollama(model: str, prompt: str, stream: bool = True) -> Iterator[str]:
    cmd = ["ollama", "run", model, prompt]
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )
    try:
        if stream:
            for line in iter(process.stdout.readline, ""):
                if line:
                    yield line
        else:
            out, _ = process.communicate()
            yield out
    finally:
        process.wait()
