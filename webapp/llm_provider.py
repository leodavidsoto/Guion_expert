"""
LLM Provider Adapter — Guion_expert
====================================
Adapter unificado: Claude Haiku 4.5 (default) o Ollama (fallback opcional).

Uso:
    from llm_provider import generate

    for chunk in generate(model="cualquier-modelo", prompt="...", stream=True):
        print(chunk, end="")

Configuración: toda vía `webapp/config.py` (pydantic-settings).
    - ANTHROPIC_API_KEY      (requerida si LLM_PROVIDER=claude)
    - LLM_PROVIDER           claude (default) | ollama
    - CLAUDE_MODEL           claude-haiku-4-5-20251001 (default)
    - CLAUDE_MAX_TOKENS      4096 (default)
    - CLAUDE_TEMPERATURE     0.7 (default)

Fail-fast: si falta la API key o config está mal, la app crashea
al import, no en runtime.

Mantiene una API compatible con el patrón `ollama run model prompt`
para que webapp/server.py pueda reemplazar subprocess con una llamada
directa y seguir haciendo streaming por SocketIO.
"""
from __future__ import annotations

import subprocess
from typing import Iterator, Optional

# Configuración centralizada (fail-fast con pydantic-settings).
# Si falta ANTHROPIC_API_KEY o algo está mal, el import crashea la app
# inmediatamente con un error claro — antes del primer request.
from config import settings


# --- Configuración global (alias retrocompatibles) ---------------------------
# Mantenemos estos nombres en módulo-level por si algo externo los importaba.

PROVIDER: str = settings.llm_provider
ANTHROPIC_API_KEY: str = settings.anthropic_api_key.get_secret_value()
CLAUDE_MODEL: str = settings.claude_model
CLAUDE_MAX_TOKENS: int = settings.claude_max_tokens
CLAUDE_TEMPERATURE: float = settings.claude_temperature


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


def generate(
    model: str,
    prompt: str,
    stream: bool = True,
    role: Optional[str] = None,
) -> Iterator[str]:
    """
    Generador que produce chunks de texto del LLM.

    Args:
        model: nombre de modelo. Si provider=claude se ignora y usa CLAUDE_MODEL.
        prompt: prompt completo a enviar.
        stream: si True, yield chunks incrementales; si False, yield una sola vez.
        role: expert role (ej. 'dialoguista'). Si está declarado en
            config/llm_provider.yaml, usa sus max_tokens/temperature específicos.
            Si es None o no está en el YAML, usa los defaults globales.

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
        )
    elif PROVIDER == "ollama":
        # Ollama no respeta per-expert params todavía — pasa derecho.
        yield from _generate_ollama(model, prompt, stream=stream)
    else:
        raise RuntimeError(f"LLM_PROVIDER desconocido: {PROVIDER}")


# --- Structured output (Anthropic tool use) ----------------------------------


def generate_structured(
    prompt: str,
    tool_name: str,
    tool_description: str,
    input_schema: dict,
    role: Optional[str] = None,
    system_prompt: str = "",
) -> dict:
    """Obtiene JSON tipado via Anthropic tool use — sin regex, sin fallback silencioso.

    Fuerza a Claude a invocar la herramienta declarada. Devuelve el dict exacto
    del `tool_use.input`, que Pydantic puede validar directo con model_validate().

    Args:
        prompt: mensaje del user (descripción de la tarea, datos de entrada).
        tool_name: nombre de la herramienta (ej. 'emit_veo_prompt').
        tool_description: descripción legible para Claude — clave para buen output.
        input_schema: JSON schema — pasá `MyModel.model_json_schema()` de Pydantic.
        role: expert role para lookup de max_tokens/temperature en settings.
        system_prompt: opcional, se manda como `system` (no concatenado al user).

    Returns:
        dict con los inputs que Claude le pasó al tool. Listo para `Model.model_validate(payload)`.

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
        # Forzamos el uso del tool — Claude no puede contestar en texto libre
        "tool_choice": {"type": "tool", "name": tool_name},
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_prompt:
        kwargs["system"] = system_prompt

    response = client.messages.create(**kwargs)

    # El response puede tener múltiples content blocks (thinking, text, tool_use).
    # Nos interesa solo el tool_use matching con tool_name.
    for block in response.content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            # block.input es el dict con las claves del schema — ya parseado por Anthropic.
            return block.input

    # Si llegamos acá, Claude ignoró el tool_choice (muy raro, pero posible si max_tokens
    # es demasiado bajo y el response se trunca antes del tool_use).
    stop_reason = getattr(response, "stop_reason", "unknown")
    raise RuntimeError(
        f"Claude no invocó la herramienta '{tool_name}'. "
        f"stop_reason={stop_reason}. "
        f"Subí max_tokens del expert '{role or 'default'}' en config/llm_provider.yaml."
    )


# --- Claude backend ----------------------------------------------------------

def _generate_claude(
    prompt: str,
    stream: bool = True,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> Iterator[str]:
    client = _get_claude_client()

    mt = max_tokens if max_tokens is not None else CLAUDE_MAX_TOKENS
    tp = temperature if temperature is not None else CLAUDE_TEMPERATURE

    if stream:
        with client.messages.stream(
            model=CLAUDE_MODEL,
            max_tokens=mt,
            temperature=tp,
            messages=[{"role": "user", "content": prompt}],
        ) as stream_resp:
            for text_chunk in stream_resp.text_stream:
                yield text_chunk
    else:
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=mt,
            temperature=tp,
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
