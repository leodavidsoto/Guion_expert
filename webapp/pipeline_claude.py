"""
Pipeline Python nativa para Guion_expert usando Claude Haiku 4.5.
===================================================================
Reemplaza ./ejecutar.sh (bash + Ollama) por un pipeline que corre 100%
en Python llamando directamente a llm_provider (Claude).

Produce la misma estructura de carpetas que scripts/pipeline.sh:
    output/YYYYMMDD_HHMMSS/
      clasificacion/result.txt
      concepto/result.txt
      estructura/result.txt
      escaleta/result.txt
      escaleta/lista.txt
      escenas/escena_NNN.txt
      prompts_sd/prompt_NNN.txt
      prompts_veo/veo_NNN.json

Además emite eventos SocketIO compatibles con la UI actual para que
el usuario vea el progreso en tiempo real.

Uso:
    from webapp.pipeline_claude import run_full_pipeline
    run_full_pipeline(idea, socketio, formato=None, estructura=None, auto_detect=True)
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import llm_provider  # webapp/llm_provider.py


# --- Configuración ----------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = BASE_DIR / "prompts"
OUTPUT_DIR = BASE_DIR / "output"

# Mapa de cuántas escenas corresponden a cada formato (reemplaza num_escenas() de lib.sh)
DEFAULT_SCENE_COUNTS = {
    "CORTO": 20,
    "MEDIO": 35,
    "LARGO": 60,
    "VIDEOCLIP": 8,
    "REEL": 6,
    "SHORT": 6,
    "TIKTOK": 5,
    "COMERCIAL": 4,
}

# Estructura narrativa -> prompt file (duplica selector_prompt_estructura.sh)
STRUCTURE_PROMPTS = {
    "SAVE_THE_CAT": "02_save_the_cat.txt",
    "HERO_JOURNEY": "02_hero_journey.txt",
    "STORY_CIRCLE": "02_story_circle.txt",
    "THREE_ACT": "02_arquitecto.txt",
    "FIVE_ACT": "02_five_act.txt",
    "IN_MEDIA_RES": "02_in_media_res.txt",
    "SIMPLE": "02_simple.txt",
}


# --- Helpers ----------------------------------------------------------------

def _emit(socketio, log_type: str, message: str) -> None:
    """Emite un log vía SocketIO o lo imprime si no hay UI conectada."""
    if socketio is not None:
        socketio.emit("log", {"type": log_type, "message": message})
    else:
        print(f"[{log_type}] {message}")


def _read_prompt(name: str) -> str:
    """Lee un archivo de prompt desde prompts/, con fallback amigable."""
    path = PROMPTS_DIR / name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _llm_generate(prompt: str, system_prompt: str = "", socketio=None, expert: str = "") -> str:
    """Llama a Claude y devuelve el texto completo, emitiendo chunks vía SocketIO."""
    full = (system_prompt + "\n\n" + prompt).strip() if system_prompt else prompt
    collected = []
    try:
        for chunk in llm_provider.generate(model="claude", prompt=full, stream=True):
            if chunk:
                collected.append(chunk)
                if socketio and expert:
                    socketio.emit(
                        "expert_update",
                        {"expert": expert, "content": "".join(collected)},
                    )
    except Exception as e:
        _emit(socketio, "error", f"Error LLM ({expert}): {e}")
        return ""
    return "".join(collected).strip()


def _parse_classification(text: str) -> dict:
    """Extrae FORMATO, ESTRUCTURA_NARRATIVA, DURACION_MINUTOS y justificaciones."""
    out = {"FORMATO": "CORTO", "ESTRUCTURA": "THREE_ACT", "DURACION": 5, "JUSTIFICACIONES": []}
    for raw_line in text.splitlines():
        line = raw_line.strip().replace("*", "")
        m = re.match(r"FORMATO\s*:\s*(.+)$", line, re.I)
        if m:
            out["FORMATO"] = m.group(1).strip().upper()
            continue
        m = re.match(r"ESTRUCTURA_NARRATIVA\s*:\s*(.+)$", line, re.I)
        if m:
            out["ESTRUCTURA"] = m.group(1).strip().upper()
            continue
        m = re.match(r"DURACION_MINUTOS\s*:\s*([\d\.]+)", line, re.I)
        if m:
            try:
                out["DURACION"] = float(m.group(1))
            except ValueError:
                pass
            continue
        if line.upper().startswith("JUSTIFICACION"):
            out["JUSTIFICACIONES"].append(line)
    return out


def _num_escenas_for(formato: str) -> int:
    return DEFAULT_SCENE_COUNTS.get(formato.upper(), 12)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# --- Etapas -----------------------------------------------------------------

def _stage_clasificacion(idea: str, out_dir: Path, socketio) -> dict:
    _emit(socketio, "info", "[1/7] CLASIFICACIÓN DUAL (Formato + Estructura)…")
    prompt_system = _read_prompt("00_clasificador_completo.txt")
    result = _llm_generate(
        prompt=f"IDEA: {idea}",
        system_prompt=prompt_system,
        socketio=socketio,
        expert="clasificador",
    )
    _write(out_dir / "clasificacion" / "result.txt", result)
    parsed = _parse_classification(result)
    _emit(socketio, "success", f"Formato: {parsed['FORMATO']}")
    _emit(socketio, "success", f"Estructura: {parsed['ESTRUCTURA']}")
    _emit(socketio, "info", f"Duración estimada: {parsed['DURACION']} min")
    for j in parsed["JUSTIFICACIONES"]:
        _emit(socketio, "info", f"  {j}")
    return parsed


def _stage_concepto(idea: str, formato: str, estructura: str, out_dir: Path, socketio) -> str:
    _emit(socketio, "info", "[2/7] CONCEPTO")
    prompt_system = _read_prompt("01_concepto.txt")
    user_block = f"FORMATO: {formato}\nESTRUCTURA: {estructura}\nIDEA: {idea}"
    result = _llm_generate(prompt=user_block, system_prompt=prompt_system, socketio=socketio, expert="concepto")
    _write(out_dir / "concepto" / "result.txt", result)
    _emit(socketio, "success", f"Concepto: {len(result.splitlines())} líneas")
    return result


def _stage_estructura(concepto: str, estructura: str, out_dir: Path, socketio) -> str:
    _emit(socketio, "info", f"[3/7] ESTRUCTURA: {estructura}")
    prompt_file = STRUCTURE_PROMPTS.get(estructura, "02_arquitecto.txt")
    prompt_system = _read_prompt(prompt_file)
    result = _llm_generate(prompt=concepto, system_prompt=prompt_system, socketio=socketio, expert="arquitecto")
    _write(out_dir / "estructura" / "result.txt", result)
    _emit(socketio, "success", f"Estructura {estructura} generada")
    return result


def _stage_escaleta(estructura_text: str, formato: str, estructura_name: str, out_dir: Path, socketio) -> list[str]:
    _emit(socketio, "info", "[4/7] ESCALETA")
    num_esc = _num_escenas_for(formato)
    _emit(socketio, "info", f"Objetivo: {num_esc} escenas")
    prompt_system = _read_prompt("03_escaletista.txt")
    prompt_system += f"\n\nGenera EXACTAMENTE {num_esc} escenas basadas en la estructura {estructura_name}."
    result = _llm_generate(prompt=estructura_text, system_prompt=prompt_system, socketio=socketio, expert="escaletista")
    _write(out_dir / "escaleta" / "result.txt", result)
    # Extraer lineas que empiecen con "N." o "N)"
    lineas = [
        l.strip()
        for l in result.splitlines()
        if re.match(r"^\s*\d+[\.\)]", l.strip())
    ]
    if not lineas:
        lineas = ["1. INT. LUGAR - DÍA - Acción."]
    _write(out_dir / "escaleta" / "lista.txt", "\n".join(lineas))
    _emit(socketio, "success", f"{len(lineas)} escenas generadas")
    return lineas


def _stage_escenas(lineas: list[str], out_dir: Path, socketio) -> list[Path]:
    total = len(lineas)
    _emit(socketio, "info", f"[5/7] ESCRIBIENDO {total} ESCENAS")
    prompt_system = _read_prompt("04_dialoguista.txt")
    archivos = []
    for i, linea in enumerate(lineas, start=1):
        num = f"{i:03d}"
        _emit(socketio, "info", f"  Escena {i}/{total}")
        texto = _llm_generate(
            prompt=linea,
            system_prompt=prompt_system,
            socketio=socketio,
            expert=f"escena_{num}",
        )
        if not texto:
            texto = f"[ERROR escena {num}]"
        p = out_dir / "escenas" / f"escena_{num}.txt"
        _write(p, texto)
        archivos.append(p)
    _emit(socketio, "success", f"{total} escenas escritas")
    return archivos


def _stage_prompts_sd(escenas_paths: list[Path], out_dir: Path, socketio) -> None:
    _emit(socketio, "info", "[6/7] GENERANDO PROMPTS SD")
    prompt_system = _read_prompt("06_sd.txt")
    for p in escenas_paths:
        num = p.stem.replace("escena_", "")
        head = p.read_text(encoding="utf-8")[:400]
        out_text = _llm_generate(prompt=head, system_prompt=prompt_system, socketio=socketio, expert=f"sd_{num}")
        if not out_text:
            out_text = "cinematic, 4k"
        _write(out_dir / "prompts_sd" / f"prompt_{num}.txt", out_text)
    _emit(socketio, "success", f"Prompts SD: {len(escenas_paths)}")


def _stage_prompts_veo(escenas_paths: list[Path], out_dir: Path, socketio) -> None:
    _emit(socketio, "info", "[7/7] GENERANDO PROMPTS VEO")
    prompt_system = _read_prompt("05_veo_flow.txt")
    for p in escenas_paths:
        num = p.stem.replace("escena_", "")
        full = p.read_text(encoding="utf-8")
        out_text = _llm_generate(prompt=full, system_prompt=prompt_system, socketio=socketio, expert=f"veo_{num}")
        # Best-effort: si el modelo devolvió JSON válido lo dejamos; si no, envolvemos.
        parsed = None
        try:
            # busca el primer bloque JSON
            m = re.search(r"\{[\s\S]*\}", out_text)
            if m:
                parsed = json.loads(m.group(0))
        except Exception:
            parsed = None
        if parsed is None:
            parsed = {"plano": "default", "raw": out_text}
        _write(out_dir / "prompts_veo" / f"veo_{num}.json", json.dumps(parsed, indent=2, ensure_ascii=False))
    _emit(socketio, "success", f"Prompts Veo: {len(escenas_paths)}")


# --- Entry point ------------------------------------------------------------

def run_full_pipeline(
    idea: str,
    socketio=None,
    formato: Optional[str] = None,
    estructura: Optional[str] = None,
    auto_detect: bool = True,
) -> dict:
    """
    Corre el pipeline entero en Python usando Claude.

    Returns:
        dict con 'output_dir' (Path), 'formato', 'estructura', 'duracion', 'escenas' (int).
    """
    if not llm_provider.is_available():
        _emit(socketio, "error", "❌ LLM no disponible. Revisá .env y ANTHROPIC_API_KEY.")
        return {"error": "llm_unavailable"}

    t0 = time.time()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUT_DIR / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    _emit(socketio, "info", "🚀 Iniciando pipeline (Claude Haiku 4.5)…")
    _emit(socketio, "info", f"💡 Idea: {idea[:120]}")
    _emit(socketio, "info", f"📁 Proyecto: output/{timestamp}")

    # 1. Clasificación (o manual)
    if auto_detect or not (formato and estructura):
        clasif = _stage_clasificacion(idea, out_dir, socketio)
        formato_final = (formato or clasif["FORMATO"]).upper()
        estructura_final = (estructura or clasif["ESTRUCTURA"]).upper()
        duracion = clasif["DURACION"]
    else:
        formato_final = formato.upper()
        estructura_final = estructura.upper()
        duracion = 5
        _write(out_dir / "clasificacion" / "result.txt", f"FORMATO: {formato_final}\nESTRUCTURA_NARRATIVA: {estructura_final}\nDURACION_MINUTOS: {duracion}\n(Manual override)")
        _emit(socketio, "info", f"Override manual: {formato_final} / {estructura_final}")

    # 2. Concepto
    concepto = _stage_concepto(idea, formato_final, estructura_final, out_dir, socketio)

    # 3. Estructura
    estructura_text = _stage_estructura(concepto, estructura_final, out_dir, socketio)

    # 4. Escaleta
    lineas = _stage_escaleta(estructura_text, formato_final, estructura_final, out_dir, socketio)

    # 5. Escenas
    escenas_paths = _stage_escenas(lineas, out_dir, socketio)

    # 6. Prompts SD
    _stage_prompts_sd(escenas_paths, out_dir, socketio)

    # 7. Prompts Veo
    _stage_prompts_veo(escenas_paths, out_dir, socketio)

    # Marker para compatibilidad con ejecutar.sh (/tmp/last_project.txt)
    try:
        Path("/tmp/last_project.txt").write_text(str(out_dir))
    except Exception:
        pass

    elapsed = int(time.time() - t0)
    _emit(socketio, "success", "✅ Pipeline completado")
    _emit(socketio, "success", f"⏱️  Tiempo: {elapsed}s")
    _emit(socketio, "success", f"📁 Proyecto: {out_dir.name}")
    _emit(socketio, "success", f"🎬 Formato: {formato_final}")
    _emit(socketio, "success", f"📖 Estructura: {estructura_final}")
    _emit(socketio, "success", f"📄 Escenas: {len(escenas_paths)}")

    return {
        "output_dir": out_dir,
        "formato": formato_final,
        "estructura": estructura_final,
        "duracion": duracion,
        "escenas": len(escenas_paths),
        "idea": idea,
    }
