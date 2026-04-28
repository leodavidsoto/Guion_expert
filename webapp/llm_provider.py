"""
LLM Provider Adapter — Guion_expert
====================================
Adapter unificado: Claude Haiku 4.5 (default) o Ollama (fallback opcional).

M7 — Telemetría: cada llamada al LLM registra tokens consumidos, tokens de caché
     leídos/creados, tiempo de respuesta y costo estimado en USD. Accesible via
     get_session_metrics() y reset_session_metrics().

M8 — Prompt Caching: generate() y generate_structured() aceptan el parámetro
     `cache_system_prompt=True` para marcar el bloque de system prompt con
     cache_control ephemeral. El Story Bible y los prompts de sistema largos se
     pasan una vez y se leen desde caché VRAM en llamadas subsiguientes.
     Ahorro: hasta 60% en tokens de entrada, hasta 85% en TTFT.

Uso:
    from llm_provider import generate, get_session_metrics

    for chunk in generate(model="claude", prompt="...", stream=True,
                          system_prompt="...", cache_system_prompt=True):
        print(chunk, end="")

    metrics = get_session_metrics()
    print(metrics)

Configuración: toda vía `webapp/config.py` (pydantic-settings).
    - ANTHROPIC_API_KEY      (requerida si LLM_PROVIDER=claude)
    - LLM_PROVIDER           claude (default) | ollama
    - CLAUDE_MODEL           claude-haiku-4-5-20251001 (default)
    - CLAUDE_MAX_TOKENS      4096 (default)
    - CLAUDE_TEMPERATURE     0.7 (default)

Fail-fast: si falta la API key o config está mal, la app crashea al import.
"""
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from typing import Iterator, Optional

# Configuración centralizada (fail-fast con pydantic-settings).
from config import settings


# ============================================================
# Configuración global (alias retrocompatibles)
# ============================================================

PROVIDER: str = settings.llm_provider
ANTHROPIC_API_KEY: str = settings.anthropic_api_key.get_secret_value()
CLAUDE_MODEL: str = settings.claude_model
CLAUDE_MAX_TOKENS: int = settings.claude_max_tokens
CLAUDE_TEMPERATURE: float = settings.claude_temperature


# ============================================================
# M7 — Telemetría
# ============================================================

# Precios estimados Haiku 4.5 (USD por millón de tokens, abril 2026)
_PRICE_INPUT_PER_M    = 0.80   # $0.80 / M tokens input
_PRICE_OUTPUT_PER_M   = 4.00   # $4.00 / M tokens output
_PRICE_CACHE_WRITE    = 1.00   # $1.00 / M tokens cache write
_PRICE_CACHE_READ     = 0.08   # $0.08 / M tokens cache read


@dataclass
class ExpertMetrics:
    """Métricas por llamada de expert."""
    role: str
    elapsed_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    estimated_cost_usd: float = 0.0

    def cost_breakdown(self) -> str:
        return (
            f"in={self.input_tokens} out={self.output_tokens} "
            f"cache_w={self.cache_creation_tokens} cache_r={self.cache_read_tokens} "
            f"${self.estimated_cost_usd:.5f} ({self.elapsed_s:.1f}s)"
        )


@dataclass
class SessionMetrics:
    """Acumulado de la sesión completa."""
    calls: list[ExpertMetrics] = field(default_factory=list)

    @property
    def total_input(self) -> int:
        return sum(m.input_tokens for m in self.calls)

    @property
    def total_output(self) -> int:
        return sum(m.output_tokens for m in self.calls)

    @property
    def total_cache_read(self) -> int:
        return sum(m.cache_read_tokens for m in self.calls)

    @property
    def total_cache_write(self) -> int:
        return sum(m.cache_creation_tokens for m in self.calls)

    @property
    def total_cost_usd(self) -> float:
        return sum(m.estimated_cost_usd for m in self.calls)

    @property
    def total_elapsed_s(self) -> float:
        return sum(m.elapsed_s for m in self.calls)

    def summary(self) -> dict:
        return {
            "calls": len(self.calls),
            "total_input_tokens": self.total_input,
            "total_output_tokens": self.total_output,
            "total_cache_read_tokens": self.total_cache_read,
            "total_cache_write_tokens": self.total_cache_write,
            "total_cost_usd": round(self.total_cost_usd, 5),
            "total_elapsed_s": round(self.total_elapsed_s, 1),
            "per_expert": {m.role: m.cost_breakdown() for m in self.calls},
        }


_SESSION_METRICS = SessionMetrics()


def get_session_metrics() -> dict:
    """Devuelve el resumen de métricas de la sesión activa."""
    return _SESSION_METRICS.summary()


def reset_session_metrics() -> None:
    """Reinicia el contador de métricas (llamar al inicio de cada pipeline run)."""
    global _SESSION_METRICS
    _SESSION_METRICS = SessionMetrics()


def _compute_cost(
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int,
    cache_read_tokens: int,
) -> float:
    return (
        (input_tokens / 1_000_000) * _PRICE_INPUT_PER_M
        + (output_tokens / 1_000_000) * _PRICE_OUTPUT_PER_M
        + (cache_creation_tokens / 1_000_000) * _PRICE_CACHE_WRITE
        + (cache_read_tokens / 1_000_000) * _PRICE_CACHE_READ
    )


def _record_metrics(role: str, elapsed_s: float, usage) -> ExpertMetrics:
    """Extrae métricas del objeto usage de la API de Anthropic y las registra."""
    m = ExpertMetrics(
        role=role or "unknown",
        elapsed_s=elapsed_s,
        input_tokens=getattr(usage, "input_tokens", 0),
        output_tokens=getattr(usage, "output_tokens", 0),
        cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", 0),
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0),
    )
    m.estimated_cost_usd = _compute_cost(
        m.input_tokens, m.output_tokens, m.cache_creation_tokens, m.cache_read_tokens
    )
    _SESSION_METRICS.calls.append(m)
    return m


# ============================================================
# Estado del provider (lazy init)
# ============================================================

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
            from anthropic import Anthropic
        except ImportError as e:
            raise RuntimeError(
                "El paquete 'anthropic' no está instalado. "
                "Ejecuta: pip install anthropic python-dotenv"
            ) from e
        _claude_client = Anthropic(api_key=ANTHROPIC_API_KEY)
    return _claude_client


# ============================================================
# API pública
# ============================================================

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
        "session_metrics": get_session_metrics(),
    }


def generate(
    model: str,
    prompt: str,
    stream: bool = True,
    role: Optional[str] = None,
    system_prompt: str = "",
    cache_system_prompt: bool = False,
) -> Iterator[str]:
    """
    Generador que produce chunks de texto del LLM.

    Args:
        model: nombre de modelo (ignorado si provider=claude, usa CLAUDE_MODEL).
        prompt: prompt de usuario completo.
        stream: si True, yield chunks incrementales; si False, yield una sola vez.
        role: expert role para lookup per-expert en llm_provider.yaml.
        system_prompt: prompt de sistema. Si no vacío, se envía como `system`.
        cache_system_prompt: M8 — si True y system_prompt no vacío, marca el
            bloque de sistema con cache_control ephemeral. Ideal para Story Bible
            o prompts largos reutilizados en múltiples escenas.

    Yields:
        str: chunks de la respuesta.
    """
    if PROVIDER == "claude":
        max_tokens, temperature = settings.params_for(role)
        yield from _generate_claude(
            prompt,
            stream=stream,
            max_tokens=max_tokens,
            temperature=temperature,
            role=role or "unknown",
            system_prompt=system_prompt,
            cache_system_prompt=cache_system_prompt,
        )
    elif PROVIDER == "ollama":
        full = (system_prompt + "\n\n" + prompt).strip() if system_prompt else prompt
        yield from _generate_ollama(model, full, stream=stream)
    else:
        raise RuntimeError(f"LLM_PROVIDER desconocido: {PROVIDER}")


# ============================================================
# M8 — Structured output con prompt caching
# ============================================================


def generate_structured(
    prompt: str,
    tool_name: str,
    tool_description: str,
    input_schema: dict,
    role: Optional[str] = None,
    system_prompt: str = "",
    cache_system_prompt: bool = False,
) -> dict:
    """Obtiene JSON tipado via Anthropic tool use — sin regex, sin fallback silencioso.

    M8: si cache_system_prompt=True, el bloque de sistema se marca con
    cache_control ephemeral. Usar para el system_prompt del director_flow
    (05_veo_flow.txt es ~2000 tokens que se reutilizan por cada escena).

    Args:
        prompt: mensaje del user.
        tool_name: nombre de la herramienta.
        tool_description: descripción legible para Claude.
        input_schema: JSON schema (pasá MyModel.model_json_schema()).
        role: expert role para max_tokens/temperature.
        system_prompt: prompt de sistema.
        cache_system_prompt: M8 — marca el system con cache_control.

    Returns:
        dict con los inputs que Claude le pasó al tool.

    Raises:
        RuntimeError: si el provider no es claude, o si Claude no usa la tool.
    """
    if PROVIDER != "claude":
        raise RuntimeError(
            "generate_structured() solo funciona con LLM_PROVIDER=claude. "
            f"Actual: {PROVIDER}."
        )

    client = _get_claude_client()
    max_tokens, temperature = settings.params_for(role)

    # M8: construir el system como lista de bloques con cache_control opcional
    system_blocks = None
    if system_prompt:
        block = {"type": "text", "text": system_prompt}
        if cache_system_prompt:
            block["cache_control"] = {"type": "ephemeral"}
        system_blocks = [block]

    kwargs: dict = {
        "model": CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "tools": [
            {
                "name": tool_name,
                "description": tool_description,
                "input_schema": input_schema,
            }
        ],
        "tool_choice": {"type": "tool", "name": tool_name},
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_blocks:
        kwargs["system"] = system_blocks

    t0 = time.time()
    response = client.messages.create(**kwargs)
    elapsed = time.time() - t0

    # M7: registrar métricas
    if hasattr(response, "usage"):
        _record_metrics(role or tool_name, elapsed, response.usage)

    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            return block.input

    stop_reason = getattr(response, "stop_reason", "unknown")
    raise RuntimeError(
        f"Claude no invocó la herramienta '{tool_name}'. "
        f"stop_reason={stop_reason}. "
        f"Subí max_tokens del expert '{role or 'default'}' en config/llm_provider.yaml."
    )


# ============================================================
# Claude backend con M7 + M8
# ============================================================

def _generate_claude(
    prompt: str,
    stream: bool = True,
    max_tokens: int | None = None,
    temperature: float | None = None,
    role: str = "unknown",
    system_prompt: str = "",
    cache_system_prompt: bool = False,
) -> Iterator[str]:
    client = _get_claude_client()

    mt = max_tokens if max_tokens is not None else CLAUDE_MAX_TOKENS
    tp = temperature if temperature is not None else CLAUDE_TEMPERATURE

    # M8: system como lista de bloques con cache_control opcional
    system_arg = None
    if system_prompt:
        block = {"type": "text", "text": system_prompt}
        if cache_system_prompt:
            block["cache_control"] = {"type": "ephemeral"}
        system_arg = [block]

    kwargs: dict = {
        "model": CLAUDE_MODEL,
        "max_tokens": mt,
        "temperature": tp,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_arg:
        kwargs["system"] = system_arg

    t0 = time.time()

    if stream:
        collected_usage = None
        with client.messages.stream(**kwargs) as stream_resp:
            for text_chunk in stream_resp.text_stream:
                yield text_chunk
            # Intentar obtener usage del mensaje final
            try:
                final_msg = stream_resp.get_final_message()
                collected_usage = getattr(final_msg, "usage", None)
            except Exception:
                pass
        elapsed = time.time() - t0
        if collected_usage:
            _record_metrics(role, elapsed, collected_usage)
    else:
        resp = client.messages.create(**kwargs)
        elapsed = time.time() - t0
        if hasattr(resp, "usage"):
            _record_metrics(role, elapsed, resp.usage)
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", None) == "text"
        )
        yield text


# ============================================================
# Ollama backend (fallback, en deprecación)
# ============================================================

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
