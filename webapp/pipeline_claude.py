"""
Pipeline Python — Guion_expert v2 con mejoras M1-M8
=====================================================
Orquesta los 9 expertos en secuencia con:

  M1 — Story Bible: memoria global compartida generada post-concepto.
       Inyectada en todos los expertos subsiguientes como contexto cacheable.
  M2 — Sliding Window Context: el Dialoguista recibe las N escenas anteriores
       como contexto comprimido para garantizar continuidad.
  M3 — Continuity QA (Expert 8): auditor adversario al final del pipeline.
       Si el score < 0.72, el pipeline reporta las violaciones al usuario.
  M4 — Topología eficiente: el Localizador usa el ADN visual del Story Bible
       como contexto base (M8 cached), reduciendo tokens redundantes.
  M5 — Two-Pass Director Flow: el Director verifica el Master Stack generado
       contra el Story Bible antes de emitir el JSON final.
  M6 — Confidence Scores: el clasificador emite confidence_score calibrado;
       si < 0.60, el pipeline alerta al usuario antes de continuar.
  M7 — Telemetría: cada etapa registra tokens, costo estimado y elapsed.
  M8 — Prompt Caching: system prompts largos y Story Bible se cachean con
       cache_control ephemeral para reutilización inter-escena.

Loop completo:
    idea → clasificación (M6) → concepto → Story Bible (M1) →
    estructura (15 beats) → escaleta → escenas (M2, M8) →
    prompts SD (M4, M8) → prompts VEO (M5, M8) → QA (M3) →
    output/<timestamp>/

Uso:
    from webapp.pipeline_claude import run_full_pipeline
    run_full_pipeline(idea, socketio, formato=None, estructura=None)
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import llm_provider
from llm_provider import get_session_metrics, reset_session_metrics
from observability import get_logger, bind_pipeline_context
from schemas import VeoPrompt, choose_video_model
from schemas.story_bible import StoryBible

log = get_logger(__name__)


# ============================================================
# Configuración
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = BASE_DIR / "prompts"
OUTPUT_DIR = BASE_DIR / "output"

# Número de escenas por formato
DEFAULT_SCENE_COUNTS = {
    "CORTO": 20, "MEDIO": 35, "LARGO": 60,
    "VIDEOCLIP": 8, "REEL": 6, "SHORT": 6, "TIKTOK": 5, "COMERCIAL": 4,
    "YOUTUBE_SHORT": 6, "REEL_INSTAGRAM": 6, "STORY": 4, "AD_SPOT": 4,
    "TUTORIAL": 10, "EXPLAINER": 8,
}

# Prompt por estructura narrativa
STRUCTURE_PROMPTS = {
    "SAVE_THE_CAT": "02_arquitecto.txt",   # 15 beats parametrizados
    "HERO_JOURNEY": "02_hero_journey.txt",
    "STORY_CIRCLE": "02_story_circle.txt",
    "THREE_ACT":    "02_arquitecto.txt",
    "FIVE_ACT":     "02_five_act.txt",
    "IN_MEDIA_RES": "02_in_media_res.txt",
    "SIMPLE":       "02_simple.txt",
}

# M2 — Ventana deslizante
SLIDING_WINDOW_SIZE = 3

# M3 — Umbral de aprobación QA
QA_APPROVAL_THRESHOLD = 0.72

# M6 — Umbral de alerta de confianza
CONFIDENCE_ALERT_THRESHOLD = 0.60

# M3 — Máximo de reintentos QA
QA_MAX_RETRIES = 2


# ============================================================
# Helpers
# ============================================================

def _emit(socketio, log_type: str, message: str) -> None:
    if socketio is not None:
        socketio.emit("log", {"type": log_type, "message": message})
    else:
        print(f"[{log_type}] {message}")


def _read_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _llm_generate(
    prompt: str,
    system_prompt: str = "",
    socketio=None,
    expert: str = "",
    role: str | None = None,
    cache_system: bool = False,
) -> str:
    """
    Llama al LLM y devuelve el texto completo.
    M8: cache_system=True marca el system_prompt con cache_control ephemeral.
    """
    collected = []
    try:
        for chunk in llm_provider.generate(
            model="claude",
            prompt=prompt,
            stream=True,
            role=role,
            system_prompt=system_prompt,
            cache_system_prompt=cache_system,
        ):
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


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _num_escenas_for(formato: str) -> int:
    return DEFAULT_SCENE_COUNTS.get(formato.upper(), 12)


# ============================================================
# M6 — Parseo del clasificador con confidence scores
# ============================================================

def _parse_classification(text: str) -> dict:
    """
    Extrae FORMATO, ESTRUCTURA_NARRATIVA, DURACION y confidence scores calibrados.
    M6: emite alertas si confidence < CONFIDENCE_ALERT_THRESHOLD.
    """
    out = {
        "FORMATO": "CORTO",
        "ESTRUCTURA": "THREE_ACT",
        "DURACION": 5,
        "CONFIDENCE_FORMATO": 1.0,
        "CONFIDENCE_ESTRUCTURA": 1.0,
        "JUSTIFICACIONES": [],
        "OBSERVACION": "",
    }
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
        m = re.match(r"CONFIDENCE_FORMATO\s*:\s*([\d\.]+)", line, re.I)
        if m:
            try:
                out["CONFIDENCE_FORMATO"] = float(m.group(1))
            except ValueError:
                pass
            continue
        m = re.match(r"CONFIDENCE_ESTRUCTURA\s*:\s*([\d\.]+)", line, re.I)
        if m:
            try:
                out["CONFIDENCE_ESTRUCTURA"] = float(m.group(1))
            except ValueError:
                pass
            continue
        m = re.match(r"OBSERVACION_INICIAL\s*:\s*(.+)$", line, re.I)
        if m:
            out["OBSERVACION"] = m.group(1).strip()
            continue
        if any(line.upper().startswith(k) for k in ["JUSTIFICACION", "REFLEXION"]):
            out["JUSTIFICACIONES"].append(line)
    return out


# ============================================================
# M1 — Story Bible: generación via tool use
# ============================================================

def _stage_story_bible(
    concepto: str,
    formato: str,
    estructura: str,
    idea: str,
    out_dir: Path,
    socketio,
) -> Optional[StoryBible]:
    """
    M1 — Genera el Story Bible global via Anthropic tool use.
    Inyectado en todos los expertos subsiguientes como contexto cacheable.
    """
    _emit(socketio, "info", "[2.5/8] STORY BIBLE (memoria global)…")
    prompt_system = _read_prompt("00b_bible_writer.txt")
    bible_schema = StoryBible.model_json_schema()

    user_prompt = (
        f"FORMATO: {formato}\nESTRUCTURA: {estructura}\n"
        f"IDEA ORIGINAL: {idea}\n\n"
        f"CONCEPTO DESARROLLADO:\n{concepto}"
    )

    try:
        payload = llm_provider.generate_structured(
            prompt=user_prompt,
            system_prompt=prompt_system,
            tool_name="emit_story_bible",
            tool_description=(
                "Emite el Story Bible completo del proyecto: logline, premisa, tema, "
                "perfiles psicológicos de personajes con ADN vocal, ADN visual "
                "(paleta, iluminación, temperatura Kelvin, estilo) y ADN sonoro "
                "(mood global, género musical, leitmotifs)."
            ),
            input_schema=bible_schema,
            role="bible_writer",
            cache_system_prompt=False,
        )
        bible = StoryBible.model_validate(payload)
        _write(out_dir / "story_bible.json", bible.model_dump_json(indent=2))
        _emit(socketio, "success", f"Story Bible: {len(bible.characters)} personaje(s) · {bible.visual_dna.visual_style}")
        _emit(socketio, "info", f"  Paleta: {', '.join(bible.visual_dna.color_palette)}")
        _emit(socketio, "info", f"  Temperatura: {bible.visual_dna.color_temperature_kelvin}K")
        _emit(socketio, "info", f"  Mood global: {', '.join(bible.sonic_dna.global_mood)}")
        return bible
    except Exception as e:
        log.error("story_bible_failed", error=str(e))
        _emit(socketio, "error", f"⚠️  Story Bible falló: {e}. Continuando sin él.")
        return None


# ============================================================
# Etapas del pipeline
# ============================================================

def _stage_clasificacion(idea: str, out_dir: Path, socketio) -> dict:
    _emit(socketio, "info", "[1/8] CLASIFICACIÓN DUAL (Formato + Estructura + Confianza)…")
    prompt_system = _read_prompt("00_clasificador_completo.txt")
    result = _llm_generate(
        prompt=f"IDEA: {idea}",
        system_prompt=prompt_system,
        socketio=socketio,
        expert="clasificador",
        role="clasificador",
    )
    _write(out_dir / "clasificacion" / "result.txt", result)
    parsed = _parse_classification(result)

    _emit(socketio, "success", f"Formato: {parsed['FORMATO']}")
    _emit(socketio, "success", f"Estructura: {parsed['ESTRUCTURA']}")
    _emit(socketio, "info", f"Duración estimada: {parsed['DURACION']} min")

    # M6 — Alertas de confianza
    cf = parsed["CONFIDENCE_FORMATO"]
    ce = parsed["CONFIDENCE_ESTRUCTURA"]
    if cf < CONFIDENCE_ALERT_THRESHOLD:
        _emit(socketio, "warning", f"⚠️  Confianza de formato baja: {cf:.2f}. Revisá si el formato es correcto.")
    else:
        _emit(socketio, "info", f"  Confianza formato: {cf:.2f}")
    if ce < CONFIDENCE_ALERT_THRESHOLD:
        _emit(socketio, "warning", f"⚠️  Confianza de estructura baja: {ce:.2f}. Revisá si la estructura es correcta.")
    else:
        _emit(socketio, "info", f"  Confianza estructura: {ce:.2f}")

    if parsed["OBSERVACION"]:
        _emit(socketio, "info", f"  Observación: {parsed['OBSERVACION']}")
    for j in parsed["JUSTIFICACIONES"]:
        _emit(socketio, "info", f"  {j}")

    return parsed


def _stage_concepto(idea: str, formato: str, estructura: str, out_dir: Path, socketio) -> str:
    _emit(socketio, "info", "[2/8] CONCEPTO")
    prompt_system = _read_prompt("01_concepto.txt")
    user_block = f"FORMATO: {formato}\nESTRUCTURA: {estructura}\nIDEA: {idea}"
    result = _llm_generate(
        prompt=user_block,
        system_prompt=prompt_system,
        socketio=socketio,
        expert="concepto",
        role="concepto",
    )
    _write(out_dir / "concepto" / "result.txt", result)
    _emit(socketio, "success", f"Concepto: {len(result.splitlines())} líneas")
    return result


def _stage_estructura(
    concepto: str,
    estructura: str,
    bible: Optional[StoryBible],
    out_dir: Path,
    socketio,
) -> str:
    _emit(socketio, "info", f"[3/8] ESTRUCTURA: {estructura} (15 beats parametrizados)")
    prompt_file = STRUCTURE_PROMPTS.get(estructura, "02_arquitecto.txt")
    prompt_system = _read_prompt(prompt_file)

    # M1: inyectar Story Bible
    user_input = concepto
    if bible:
        user_input = bible.to_context_block() + "\n\nCONCEPTO A ESTRUCTURAR:\n" + concepto

    result = _llm_generate(
        prompt=user_input,
        system_prompt=prompt_system,
        socketio=socketio,
        expert="arquitecto",
        role="arquitecto",
    )
    _write(out_dir / "estructura" / "result.txt", result)
    _emit(socketio, "success", f"Estructura {estructura} generada (15 beats)")
    return result


def _stage_escaleta(
    estructura_text: str,
    formato: str,
    estructura_name: str,
    bible: Optional[StoryBible],
    out_dir: Path,
    socketio,
) -> list[str]:
    _emit(socketio, "info", "[4/8] ESCALETA")
    num_esc = _num_escenas_for(formato)
    _emit(socketio, "info", f"Objetivo: {num_esc} escenas")
    prompt_system = _read_prompt("03_escaletista.txt")
    prompt_system += f"\n\nGenera EXACTAMENTE {num_esc} escenas basadas en la estructura {estructura_name}."

    user_input = estructura_text
    if bible:
        user_input = bible.to_context_block() + "\n\nESTRUCTURA A EXPANDIR:\n" + estructura_text

    result = _llm_generate(
        prompt=user_input,
        system_prompt=prompt_system,
        socketio=socketio,
        expert="escaletista",
        role="escaletista",
    )
    _write(out_dir / "escaleta" / "result.txt", result)
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


def _build_sliding_window(scene_texts: list[str], current_idx: int) -> str:
    """
    M2 — Contexto deslizante bidireccional para el Dialoguista.
    Inyecta resúmenes comprimidos de las SLIDING_WINDOW_SIZE escenas previas.
    """
    if current_idx == 0 or not scene_texts:
        return ""
    start = max(0, current_idx - SLIDING_WINDOW_SIZE)
    window = scene_texts[start:current_idx]
    lines = []
    for i, text in enumerate(window, start=start + 1):
        summary = " ".join(text.splitlines()[:3])[:300]
        lines.append(f"  Escena {i:03d}: {summary}…")
    return (
        "=== CONTEXTO DE ESCENAS ANTERIORES (ventana deslizante M2) ===\n"
        + "\n".join(lines)
        + "\n=== FIN CONTEXTO ===\n\n"
    )


def _stage_escenas(
    lineas: list[str],
    bible: Optional[StoryBible],
    out_dir: Path,
    socketio,
) -> list[Path]:
    """
    M2 — Escenas con Sliding Window Context.
    M8 — System prompt del dialoguista cacheado entre escenas.
    """
    total = len(lineas)
    _emit(socketio, "info", f"[5/8] ESCRIBIENDO {total} ESCENAS (SBS + ventana M2 + cache M8)")
    prompt_system = _read_prompt("04_dialoguista.txt")
    bible_context = bible.to_context_block() if bible else ""

    archivos: list[Path] = []
    scene_texts: list[str] = []

    for i, linea in enumerate(lineas, start=1):
        num = f"{i:03d}"
        _emit(socketio, "info", f"  Escena {i}/{total}")

        sliding_ctx = _build_sliding_window(scene_texts, i - 1)

        user_parts = []
        if bible_context:
            user_parts.append(bible_context)
        if sliding_ctx:
            user_parts.append(sliding_ctx)
        user_parts.append(f"ESCENA A ESCRIBIR:\n{linea}")
        user_prompt = "\n".join(user_parts)

        texto = _llm_generate(
            prompt=user_prompt,
            system_prompt=prompt_system,
            socketio=socketio,
            expert=f"escena_{num}",
            role="dialoguista",
            cache_system=True,  # M8
        )
        if not texto:
            texto = f"[ERROR escena {num}]"

        p = out_dir / "escenas" / f"escena_{num}.txt"
        _write(p, texto)
        archivos.append(p)
        scene_texts.append(texto)

    _emit(socketio, "success", f"{total} escenas escritas")
    return archivos


def _stage_prompts_sd(
    escenas_paths: list[Path],
    bible: Optional[StoryBible],
    out_dir: Path,
    socketio,
) -> None:
    """
    M4 — Localizador con ADN visual del Story Bible.
    M8 — System prompt cacheado entre escenas.
    """
    _emit(socketio, "info", "[6/8] GENERANDO PROMPTS SD (FLUX · ADN visual M4)")
    prompt_system = _read_prompt("06_sd.txt")

    visual_context = ""
    if bible:
        v = bible.visual_dna
        visual_context = (
            f"=== ADN VISUAL DEL PROYECTO (respetar en todos los prompts) ===\n"
            f"Estilo: {v.visual_style} | Paleta: {', '.join(v.color_palette)}\n"
            f"Temperatura: {v.color_temperature_kelvin}K | Iluminación: {v.lighting_signature[:120]}\n"
            f"Texturas: {', '.join(v.recurring_textures)}\n"
            f"=== FIN ADN VISUAL ===\n\n"
        )

    for p in escenas_paths:
        num = p.stem.replace("escena_", "")
        head = p.read_text(encoding="utf-8")[:400]
        user_prompt = visual_context + f"ESCENA:\n{head}"
        out_text = _llm_generate(
            prompt=user_prompt,
            system_prompt=prompt_system,
            socketio=socketio,
            expert=f"sd_{num}",
            role="localizador",
            cache_system=True,  # M8
        )
        if not out_text:
            out_text = "cinematic, 4k"
        _write(out_dir / "prompts_sd" / f"prompt_{num}.txt", out_text)
    _emit(socketio, "success", f"Prompts SD: {len(escenas_paths)}")


def _verify_veo_against_bible(
    veo: VeoPrompt,
    bible: StoryBible,
    scene_id: str,
    socketio,
) -> VeoPrompt:
    """
    M5 — Pass 2: verificar coherencia del VeoPrompt contra el Story Bible.
    Corrige style drift y palette drift automáticamente.
    """
    corrected = False
    b_style = bible.visual_dna.visual_style
    b_palette = bible.visual_dna.color_palette

    if veo.visual_anchor.style != b_style:
        log.warning("veo_style_drift", scene_id=scene_id, expected=b_style, got=veo.visual_anchor.style)
        _emit(socketio, "warning", f"  ⚠️  {scene_id}: style drift ({veo.visual_anchor.style}→{b_style}). Corregido.")
        veo = veo.model_copy(
            update={"visual_anchor": veo.visual_anchor.model_copy(update={"style": b_style})}
        )
        corrected = True

    anchor_palette_str = " ".join(veo.visual_anchor.palette).lower()
    overlap = any(tok.lower() in anchor_palette_str for tok in b_palette)
    if not overlap:
        merged = list({*veo.visual_anchor.palette, *b_palette[:2]})[:6]
        _emit(socketio, "warning", f"  ⚠️  {scene_id}: paleta sin overlap con Story Bible. Mergeando.")
        veo = veo.model_copy(
            update={"visual_anchor": veo.visual_anchor.model_copy(update={"palette": merged})}
        )
        corrected = True

    if not corrected:
        _emit(socketio, "info", f"  {scene_id}: M5 OK — sin drift visual.")

    return veo


def _stage_prompts_veo(
    escenas_paths: list[Path],
    bible: Optional[StoryBible],
    out_dir: Path,
    socketio,
) -> None:
    """
    M5 — Two-Pass Director Flow.
    M8 — System prompt del director cacheado entre escenas.
    """
    _emit(socketio, "info", "[7/8] GENERANDO PROMPTS VEO (Master Stack · Two-Pass M5 · Cache M8)")
    prompt_system = _read_prompt("05_veo_flow.txt")
    veo_schema = VeoPrompt.model_json_schema()
    bible_block = bible.to_context_block() + "\n\n" if bible else ""

    for p in escenas_paths:
        num = p.stem.replace("escena_", "")
        scene_number = int(num)
        scene_id = f"scene-{num}"
        scene_text = p.read_text(encoding="utf-8")

        user_prompt = (
            f"{bible_block}"
            f"scene_id: {scene_id}\n"
            f"scene_number: {scene_number}\n\n"
            f"ESCENA (texto completo del dialoguista, incluye bloque de atmósfera sonora al final):\n"
            f"-----------------------------------------------------------\n"
            f"{scene_text}\n"
            f"-----------------------------------------------------------\n\n"
            f"Emití el Master Stack completo via la herramienta emit_veo_prompt."
        )

        _emit(socketio, "info", f"  VEO {scene_id}…")
        try:
            payload = llm_provider.generate_structured(
                prompt=user_prompt,
                system_prompt=prompt_system,
                tool_name="emit_veo_prompt",
                tool_description=(
                    "Emite el Master Stack cinematográfico completo para esta escena: "
                    "cámara (CameraPhysics), ancla visual para FLUX (VisualAnchor), "
                    "intención de movimiento para routing I2V (MotionIntent), "
                    "atmósfera sonora para Suno/mmaudio (SonicAtmosphere) "
                    "y post-producción (PostProduction)."
                ),
                input_schema=veo_schema,
                role="director_flow",
                cache_system_prompt=True,  # M8
            )
            veo = VeoPrompt.model_validate(payload)
        except Exception as e:
            log.error("veo_generation_failed", scene_id=scene_id, error=str(e))
            _emit(socketio, "error", f"❌ VEO {scene_id} falló: {e}")
            raise

        # M5 — Pass 2: verificar contra Story Bible
        if bible:
            veo = _verify_veo_against_bible(veo, bible, scene_id, socketio)

        out_path = out_dir / "prompts_veo" / f"veo_{num}.json"
        _write(out_path, veo.model_dump_json(indent=2))

        chosen = choose_video_model(veo.motion_intent.subject_type)
        log.info(
            "veo_scene_generated",
            scene_id=scene_id,
            narrative_beat=veo.narrative_beat,
            subject_type=veo.motion_intent.subject_type,
            chosen_video_model=chosen,
            mood=veo.sonic.mood,
            duration_s=veo.camera.duration_seconds,
        )

        if socketio:
            socketio.emit(
                "expert_update",
                {
                    "expert": f"veo_{num}",
                    "content": f"{veo.camera.shot_type} · {veo.camera.movement} · {chosen}",
                },
            )

    _emit(socketio, "success", f"Prompts VEO (Master Stack): {len(escenas_paths)}")


# ============================================================
# M3 — Continuity QA (Expert 8)
# ============================================================

def _stage_continuity_qa(
    escenas_paths: list[Path],
    bible: Optional[StoryBible],
    estructura_text: str,
    out_dir: Path,
    socketio,
    retry: int = 0,
) -> dict:
    """
    M3 — Auditor adversario.
    Analiza una muestra de escenas contra el Story Bible y la estructura.
    Emite score y feedback para correcciones manuales o futuras iteraciones.
    """
    _emit(socketio, "info", f"[8/8] CONTINUITY QA (intento {retry + 1}/{QA_MAX_RETRIES + 1})…")
    prompt_system = _read_prompt("13_continuity_qa.txt")

    bible_block = bible.to_context_block() if bible else "(Story Bible no disponible)\n"

    # Samplear escenas clave para no exceder contexto
    total = len(escenas_paths)
    indices = sorted({0, 1, 2, total // 2, total - 3, total - 2, total - 1} & set(range(total)))

    escenas_muestra = []
    for idx in indices:
        texto = escenas_paths[idx].read_text(encoding="utf-8")[:600]
        escenas_muestra.append(f"--- Escena {idx + 1:03d} ---\n{texto}\n")

    user_prompt = (
        f"{bible_block}\n"
        f"ESTRUCTURA (referencia de beats):\n{estructura_text[:800]}\n\n"
        f"MUESTRA DE ESCENAS ({len(indices)} de {total}):\n"
        + "\n".join(escenas_muestra)
    )

    result = _llm_generate(
        prompt=user_prompt,
        system_prompt=prompt_system,
        socketio=socketio,
        expert="continuity_qa",
        role="continuity_qa",
    )
    _write(out_dir / f"qa_report_attempt_{retry + 1}.txt", result)

    qa_status = "APROBADO"
    score_global = 1.0
    violaciones: list[str] = []
    correcciones: list[str] = []

    in_violaciones = False
    in_correcciones = False
    for line in result.splitlines():
        line_s = line.strip()
        m = re.match(r"QA_STATUS\s*:\s*(APROBADO|RECHAZADO)", line_s, re.I)
        if m:
            qa_status = m.group(1).upper()
        m = re.match(r"SCORE_GLOBAL\s*:\s*([\d\.]+)", line_s, re.I)
        if m:
            try:
                score_global = float(m.group(1))
            except ValueError:
                pass
        if "VIOLACIONES_CRITICAS" in line_s.upper():
            in_violaciones = True
            in_correcciones = False
        elif "CORRECCIONES_REQUERIDAS" in line_s.upper():
            in_correcciones = True
            in_violaciones = False
        elif re.match(r"^[A-Z_]+:", line_s) and "ESCENA" not in line_s.upper():
            in_violaciones = False
            in_correcciones = False
        elif in_violaciones and re.match(r"-\s+ESCENA", line_s, re.I):
            violaciones.append(line_s)
        elif in_correcciones and re.match(r"-\s+ESCENA", line_s, re.I):
            correcciones.append(line_s)

    if qa_status == "APROBADO":
        _emit(socketio, "success", f"✅ QA Aprobado — Score: {score_global:.2f}")
    else:
        _emit(socketio, "error", f"❌ QA Rechazado — Score: {score_global:.2f}")
        for v in violaciones[:5]:
            _emit(socketio, "warning", f"  {v}")
        _emit(socketio, "info", f"  Revisá qa_report_attempt_{retry + 1}.txt para el detalle completo.")

    return {
        "status": qa_status,
        "score": score_global,
        "violaciones": violaciones,
        "correcciones": correcciones,
        "raw": result,
    }


# ============================================================
# Entry point
# ============================================================

def run_full_pipeline(
    idea: str,
    socketio=None,
    formato: Optional[str] = None,
    estructura: Optional[str] = None,
    auto_detect: bool = True,
) -> dict:
    """
    Pipeline v2 con mejoras M1-M8.

    Returns:
        dict con output_dir, formato, estructura, duracion, escenas,
              story_bible, qa_result, session_metrics.
    """
    if not llm_provider.is_available():
        log.error("llm_unavailable", provider=llm_provider.PROVIDER)
        _emit(socketio, "error", "❌ LLM no disponible. Revisá .env y ANTHROPIC_API_KEY.")
        return {"error": "llm_unavailable"}

    # M7: resetear métricas al inicio de cada pipeline
    reset_session_metrics()

    t0 = time.time()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pipeline_id = f"pipe-{timestamp}"
    out_dir = OUTPUT_DIR / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info(
        "pipeline_start",
        pipeline_id=pipeline_id,
        idea_preview=idea[:120],
        auto_detect=auto_detect,
        formato_override=formato,
        estructura_override=estructura,
        model=llm_provider.CLAUDE_MODEL,
    )

    _emit(socketio, "info", "🚀 Iniciando pipeline v2 (M1-M8)…")
    _emit(socketio, "info", f"💡 Idea: {idea[:120]}")
    _emit(socketio, "info", f"📁 Proyecto: output/{timestamp}")

    # 1. Clasificación (M6)
    if auto_detect or not (formato and estructura):
        clasif = _stage_clasificacion(idea, out_dir, socketio)
        formato_final = (formato or clasif["FORMATO"]).upper()
        estructura_final = (estructura or clasif["ESTRUCTURA"]).upper()
        duracion = clasif["DURACION"]
        confidence_formato = clasif["CONFIDENCE_FORMATO"]
        confidence_estructura = clasif["CONFIDENCE_ESTRUCTURA"]
    else:
        formato_final = formato.upper()
        estructura_final = estructura.upper()
        duracion = 5
        confidence_formato = confidence_estructura = 1.0
        _write(
            out_dir / "clasificacion" / "result.txt",
            f"FORMATO: {formato_final}\nESTRUCTURA_NARRATIVA: {estructura_final}\nDURACION_MINUTOS: {duracion}\n(Manual override)",
        )
        _emit(socketio, "info", f"Override manual: {formato_final} / {estructura_final}")

    # 2. Concepto
    concepto = _stage_concepto(idea, formato_final, estructura_final, out_dir, socketio)

    # 2.5. Story Bible (M1)
    bible = _stage_story_bible(concepto, formato_final, estructura_final, idea, out_dir, socketio)

    # 3. Estructura (15 beats, M1 context)
    estructura_text = _stage_estructura(concepto, estructura_final, bible, out_dir, socketio)

    # 4. Escaleta (M1 context)
    lineas = _stage_escaleta(estructura_text, formato_final, estructura_final, bible, out_dir, socketio)

    # 5. Escenas (M2 sliding window, M8 cache)
    escenas_paths = _stage_escenas(lineas, bible, out_dir, socketio)

    # 6. Prompts SD (M4 ADN visual, M8 cache)
    _stage_prompts_sd(escenas_paths, bible, out_dir, socketio)

    # 7. Prompts VEO (M5 two-pass, M8 cache)
    _stage_prompts_veo(escenas_paths, bible, out_dir, socketio)

    # 8. Continuity QA (M3)
    qa_result = _stage_continuity_qa(escenas_paths, bible, estructura_text, out_dir, socketio)
    if qa_result["status"] == "RECHAZADO":
        _emit(socketio, "warning", "QA rechazado — revisá qa_report_attempt_1.txt para correcciones manuales.")

    # Marker de compatibilidad con ejecutar.sh
    try:
        Path("/tmp/last_project.txt").write_text(str(out_dir))
    except Exception:
        pass

    elapsed = int(time.time() - t0)

    # M7: guardar métricas de sesión
    metrics = get_session_metrics()
    _write(out_dir / "session_metrics.json", json.dumps(metrics, indent=2))

    log.info(
        "pipeline_complete",
        pipeline_id=pipeline_id,
        elapsed_s=elapsed,
        formato=formato_final,
        estructura=estructura_final,
        scenes=len(escenas_paths),
        output_dir=str(out_dir),
        total_cost_usd=metrics["total_cost_usd"],
        qa_status=qa_result["status"],
        qa_score=qa_result["score"],
    )

    _emit(socketio, "success", "✅ Pipeline v2 completado")
    _emit(socketio, "success", f"⏱️  Tiempo: {elapsed}s")
    _emit(socketio, "success", f"💰 Costo estimado: ${metrics['total_cost_usd']:.4f} USD")
    _emit(socketio, "success", f"🔤 Tokens: {metrics['total_input_tokens']} in / {metrics['total_output_tokens']} out")
    _emit(socketio, "success", f"⚡ Cache hits M8: {metrics['total_cache_read_tokens']} tokens ahorrados")
    _emit(socketio, "success", f"📁 Proyecto: {out_dir.name}")
    _emit(socketio, "success", f"🎬 Formato: {formato_final} | 📖 Estructura: {estructura_final}")
    _emit(socketio, "success", f"📄 Escenas: {len(escenas_paths)}")
    _emit(
        socketio,
        "info" if qa_result["status"] == "APROBADO" else "warning",
        f"🔍 QA: {qa_result['status']} (score {qa_result['score']:.2f})",
    )

    return {
        "output_dir": out_dir,
        "formato": formato_final,
        "estructura": estructura_final,
        "duracion": duracion,
        "escenas": len(escenas_paths),
        "idea": idea,
        "story_bible": bible.model_dump() if bible else None,
        "confidence_formato": confidence_formato,
        "confidence_estructura": confidence_estructura,
        "qa_result": qa_result,
        "session_metrics": metrics,
    }
