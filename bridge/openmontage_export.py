"""
Bridge Guion_expert → OpenMontage
==================================
Convierte la salida en español de Guion_expert (clasificación, concepto,
estructura, escaleta, escenas, prompts Veo/SD) en los artifacts oficiales
de OpenMontage (brief.json, script.json, scene_plan.json, checkpoint.json),
validados contra los JSON Schemas del repo OpenMontage.

Además genera un `remotion-cuts.json` listo para renderizar con Remotion
(zero-key) y lo copia automáticamente a `remotion-composer/public/demo-props/`
para que `python render_demo.py <slug>` lo levante sin más configuración.

Diseño:
- La conversión es 100% Python determinista — sin LLM.
- Soporta dos formatos de prompts Veo: el plano/flat `{plano, movimiento,
  iluminacion}` y el nested spec completo con `parametros_globales`,
  `tracking_entidades` y `secuencia_planos`.
- Selecciona automáticamente el style playbook y la pipeline de OpenMontage
  más apropiados en función del formato (REEL/TIKTOK/SHORT vs CORTO/MEDIO/LARGO).
- Tolera datos parciales o dañados (escenas con `[ERROR ...]`, conceptos
  vacíos) haciendo fallback a la escaleta y la idea original.

Uso:
    from bridge import export_project_to_openmontage
    paths = export_project_to_openmontage(
        project_dir=Path("output/20260416_123000"),
        openmontage_root=Path("/Users/leo/Desktop/ESCRIBE/OpenMontage"),
        idea="reel de instagram para 3SM",
        brief_hint={"formato": "REEL", "duration_seconds": 30},
    )
    # paths["project_root"]   → OpenMontage/projects/<id>
    # paths["brief"] / ["script"] / ["scene_plan"] / ["checkpoint"] / ["cuts"]
"""
from __future__ import annotations

import json
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# ───────────────────────── Constantes / mapeos ─────────────────────────────

FORMATO_A_PLATAFORMA: dict[str, str] = {
    "REEL": "instagram",
    "INSTAGRAM": "instagram",
    "TIKTOK": "tiktok",
    "SHORT": "youtube",
    "YOUTUBE_SHORT": "youtube",
    "YOUTUBE": "youtube",
    "VIDEOCLIP": "generic",
    "COMERCIAL": "generic",
    "CORTO": "youtube",
    "MEDIO": "youtube",
    "LARGO": "youtube",
}

# Duración por defecto (segundos) si la clasificación no la provee o es incoherente
FORMATO_A_DURACION_SEG: dict[str, float] = {
    "REEL": 30.0,
    "INSTAGRAM": 30.0,
    "TIKTOK": 30.0,
    "SHORT": 45.0,
    "YOUTUBE_SHORT": 45.0,
    "VIDEOCLIP": 180.0,
    "COMERCIAL": 30.0,
    "CORTO": 300.0,
    "MEDIO": 900.0,
    "LARGO": 3600.0,
}

# Pipeline recomendada en OpenMontage por formato
FORMATO_A_PIPELINE: dict[str, str] = {
    "REEL": "cinematic",
    "INSTAGRAM": "cinematic",
    "TIKTOK": "cinematic",
    "SHORT": "cinematic",
    "YOUTUBE_SHORT": "cinematic",
    "VIDEOCLIP": "cinematic",
    "COMERCIAL": "cinematic",
    "CORTO": "cinematic",
    "MEDIO": "cinematic",
    "LARGO": "cinematic",
}

# Playbooks que existen de fábrica en OpenMontage/styles/
DEFAULT_PLAYBOOKS: tuple[str, ...] = (
    "flat-motion-graphics",
    "clean-professional",
    "anime-ghibli",
    "minimalist-diagram",
)

# Heurística de playbook en función del formato
FORMATO_A_PLAYBOOK: dict[str, str] = {
    "REEL": "flat-motion-graphics",
    "INSTAGRAM": "flat-motion-graphics",
    "TIKTOK": "flat-motion-graphics",
    "SHORT": "flat-motion-graphics",
    "YOUTUBE_SHORT": "flat-motion-graphics",
    "VIDEOCLIP": "flat-motion-graphics",
    "COMERCIAL": "clean-professional",
    "CORTO": "clean-professional",
    "MEDIO": "clean-professional",
    "LARGO": "clean-professional",
}

# ES + EN → shot_size enum
SHOT_SIZE_SYNONYMS: dict[str, str] = {
    # Español
    "gran plano general": "extreme_wide",
    "plano general": "wide",
    "plano abierto": "wide",
    "plano americano": "medium_wide",
    "plano medio corto": "medium_close",
    "plano medio": "medium",
    "primerísimo primer plano": "extreme_close_up",
    "primer plano": "close_up",
    "detalle": "insert",
    "establecedor": "establishing",
    "over shoulder": "over_shoulder",
    "over-shoulder": "over_shoulder",
    "sobre el hombro": "over_shoulder",
    # English (usado por el prompt VEO en tipo_plano)
    "extreme wide": "extreme_wide",
    "extreme wide shot": "extreme_wide",
    "wide shot": "wide",
    "wide": "wide",
    "medium wide": "medium_wide",
    "medium shot": "medium",
    "medium close": "medium_close",
    "close-up": "close_up",
    "close up": "close_up",
    "extreme close-up": "extreme_close_up",
    "extreme close up": "extreme_close_up",
    "insert shot": "insert",
    "establishing shot": "establishing",
    "over the shoulder": "over_shoulder",
}

CAMERA_MOVEMENT_SYNONYMS: dict[str, str] = {
    # Master Stack v2 (underscore — match directo con el schema Pydantic)
    "dolly_in": "dolly_in",
    "dolly_out": "dolly_out",
    "tracking_left": "tracking_left",
    "tracking_right": "tracking_right",
    "pan_left": "pan_left",
    "pan_right": "pan_right",
    "tilt_up": "tilt_up",
    "tilt_down": "tilt_down",
    "zoom_in": "zoom_in",
    "zoom_out": "zoom_out",
    "whip_pan": "whip_pan",
    "crane_up": "crane_up",
    "crane_down": "crane_down",
    "rack_focus": "rack_focus",
    # Español
    "dolly in": "dolly_in",
    "dolly out": "dolly_out",
    "travelling derecha": "tracking_right",
    "travelling izquierda": "tracking_left",
    "travelling": "tracking_left",
    "tracking": "tracking_left",
    "paneo derecha": "pan_right",
    "paneo izquierda": "pan_left",
    "pan derecha": "pan_right",
    "pan izquierda": "pan_left",
    "paneo a la derecha": "pan_right",
    "paneo a la izquierda": "pan_left",
    "tilt up": "tilt_up",
    "tilt down": "tilt_down",
    "steadicam": "steadicam",
    "handheld": "handheld",
    "cámara en mano": "handheld",
    "zoom in": "zoom_in",
    "zoom out": "zoom_out",
    "whip pan": "whip_pan",
    "grúa arriba": "crane_up",
    "grúa abajo": "crane_down",
    "crane up": "crane_up",
    "crane down": "crane_down",
    "orbital": "orbital",
    "órbita": "orbital",
    "rack focus": "rack_focus",
    "cambio de foco": "rack_focus",
    "estático": "static",
    "fijo": "static",
    "static": "static",
}

LIGHTING_SYNONYMS: dict[str, str] = {
    "high key": "high_key",
    "low key": "low_key",
    "natural": "natural",
    "luz natural": "natural",
    "día": "natural",
    "dia": "natural",
    "golden hour": "golden_hour",
    "hora dorada": "golden_hour",
    "blue hour": "blue_hour",
    "hora azul": "blue_hour",
    "tungsteno": "tungsten_warm",
    "tungsten": "tungsten_warm",
    "cálida": "tungsten_warm",
    "calida": "tungsten_warm",
    "neón": "neon",
    "neon": "neon",
    "silueta": "silhouette",
    "silhouette": "silhouette",
    "contraluz": "rim_lit",
    "rim": "rim_lit",
    "volumétrica": "volumetric",
    "volumetric": "volumetric",
    "nublado": "overcast_soft",
    "overcast": "overcast_soft",
    "noche": "low_key",
}

COLOR_TEMP_HINTS: dict[str, str] = {
    "cálida": "warm",
    "calida": "warm",
    "warm": "warm",
    "cálido": "warm",
    "naranja": "warm",
    "dorad": "warm",
    "golden": "warm",
    "fría": "cool",
    "fria": "cool",
    "cool": "cool",
    "frío": "cool",
    "azul": "cool",
    "blue": "cool",
    "neutral": "neutral",
    "mixta": "mixed",
    "mixed": "mixed",
    "contrastad": "mixed",
}

DOF_HINTS: dict[str, str] = {
    "shallow": "shallow",
    "poca profundidad": "shallow",
    "bokeh": "shallow",
    "profundidad reducida": "shallow",
    "deep": "deep",
    "gran profundidad": "deep",
    "todo en foco": "deep",
    "focus stack": "deep",
}

TEXTURE_VOCAB: tuple[str, ...] = (
    "grain", "grano", "clean", "limpio", "anamorphic", "anamórfico",
    "gritty", "rugoso", "ethereal", "etéreo", "vintage", "retro",
    "neon", "neón", "soft", "suave", "harsh", "duro", "dreamy", "onírico",
    "documentary", "documental", "hyperrealistic", "hiperrealista",
)

ERROR_BODY_RE = re.compile(r"\[\s*ERROR[^\]]*\]", re.IGNORECASE)


# ───────────────────────── Utilidades base ─────────────────────────────────

def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:60] or "proyecto"


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _clean_text(txt: str) -> str:
    """Colapsa espacios en blanco y recorta."""
    return re.sub(r"\s+", " ", txt or "").strip()


def _first_nonempty(*values: Any) -> str:
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


# ───────────────────────── Parsers de Guion_expert ─────────────────────────

def _parse_classification_file(path: Path) -> dict:
    out = {"formato": "CORTO", "estructura": "THREE_ACT", "duracion_min": 0.0, "justificaciones": []}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip().replace("*", "")
        m = re.match(r"FORMATO\s*:\s*(.+)$", line, re.I)
        if m:
            out["formato"] = m.group(1).strip().upper()
            continue
        m = re.match(r"ESTRUCTURA_NARRATIVA\s*:\s*(.+)$", line, re.I)
        if m:
            out["estructura"] = m.group(1).strip().upper()
            continue
        m = re.match(r"DURACION_MINUTOS\s*:\s*([\d\.]+)", line, re.I)
        if m:
            try:
                out["duracion_min"] = float(m.group(1))
            except ValueError:
                pass
            continue
        if line.upper().startswith("JUSTIFICACION"):
            out["justificaciones"].append(line)
    return out


def _override_formato_from_idea(formato: str, idea: str) -> str:
    """
    Si el clasificador mandó algo incoherente (p. ej. 'CORTO' cuando la idea
    dice 'reel de instagram'), corrige en base a palabras clave de la idea.
    Es un último recurso: respeta la clasificación si parece coherente.
    """
    idea_low = (idea or "").lower()
    if not idea_low:
        return formato
    # orden importa: match más específico primero
    hints = [
        ("reel", "REEL"),
        ("instagram", "REEL"),
        ("tiktok", "TIKTOK"),
        ("short", "SHORT"),
        ("youtube short", "SHORT"),
        ("videoclip", "VIDEOCLIP"),
        ("comercial", "COMERCIAL"),
        ("spot", "COMERCIAL"),
    ]
    for needle, fmt in hints:
        if needle in idea_low:
            # Si la clasificación es "genérica grande" (CORTO/MEDIO/LARGO) y la
            # idea apunta a formato corto, pisamos.
            if formato in ("CORTO", "MEDIO", "LARGO", ""):
                return fmt
    return formato


def _extract_title_hook(concepto_text: str, idea: str) -> tuple[str, str, list[str], str]:
    """
    Devuelve (title, hook, key_points, core_message).
    Robusto ante conceptos vacíos o mal formateados.
    """
    title = ""
    hook = ""
    core_message = ""
    key_points: list[str] = []

    for raw in (concepto_text or "").splitlines():
        line = raw.strip().replace("*", "")
        m = re.match(r"(?:TITULO|TÍTULO|TITLE)\s*:\s*(.+)$", line, re.I)
        if m and not title:
            title = m.group(1).strip().strip('"')
            continue
        m = re.match(r"(?:HOOK|GANCHO|PREMISA)\s*:\s*(.+)$", line, re.I)
        if m and not hook:
            hook = m.group(1).strip().strip('"')
            continue
        m = re.match(r"(?:MENSAJE|CORE_MESSAGE|MENSAJE_CENTRAL)\s*:\s*(.+)$", line, re.I)
        if m and not core_message:
            core_message = m.group(1).strip().strip('"')
            continue
        m = re.match(r"^[-•\d\.\)]+\s*(.+)$", line)
        if m and len(m.group(1)) > 8 and len(key_points) < 5:
            key_points.append(m.group(1).strip())

    if not title:
        for raw in (concepto_text or "").splitlines():
            s = raw.strip()
            if s and not s.startswith(("#", "*", "-")):
                title = s[:80]
                break
    if not title:
        title = (idea or "Proyecto sin título")[:60]

    if not hook:
        parts = [p.strip() for p in (concepto_text or "").split("\n\n") if p.strip()]
        hook = (parts[0][:200] if parts else idea)[:200] or title

    if not key_points:
        key_points = [idea[:120] if idea else title]

    if not core_message:
        core_message = hook or key_points[0]

    return title[:120], hook[:280], key_points[:5], core_message[:200]


def _parse_scene_line(line: str) -> dict:
    m = re.match(r"^\s*(\d+)[\.\)]\s*(.*)$", line)
    if not m:
        return {"num": 0, "text": line.strip()}
    return {"num": int(m.group(1)), "text": m.group(2).strip()}


def _clean_scene_body(raw_body: str, fallback: str) -> str:
    """Detecta marcadores '[ERROR escena 001]' y hace fallback al texto dado."""
    body = (raw_body or "").strip()
    # Si el cuerpo entero es un ERROR marker
    if ERROR_BODY_RE.fullmatch(body or ""):
        return fallback.strip()
    # Si contiene ERROR marker pero también contenido útil, limpia el marker
    if ERROR_BODY_RE.search(body):
        body = ERROR_BODY_RE.sub("", body).strip()
    return body or fallback.strip()


def _enumerate_scenes(project_dir: Path) -> list[dict]:
    """
    Combina escaleta/lista.txt + escenas/escena_NNN.txt + prompts_veo/veo_NNN.json
    + prompts_sd/prompt_NNN.txt. Robusto ante archivos faltantes o dañados.
    """
    lista_file = project_dir / "escaleta" / "lista.txt"
    lineas: list[str] = []
    if lista_file.exists():
        lineas = [l for l in lista_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    scenes: list[dict] = []
    for idx, line in enumerate(lineas, start=1):
        parsed = _parse_scene_line(line)
        num = parsed["num"] or idx
        num_str = f"{num:03d}"
        escena_path = project_dir / "escenas" / f"escena_{num_str}.txt"
        veo_path = project_dir / "prompts_veo" / f"veo_{num_str}.json"
        sd_path = project_dir / "prompts_sd" / f"prompt_{num_str}.txt"

        raw_body = escena_path.read_text(encoding="utf-8") if escena_path.exists() else ""
        body = _clean_scene_body(raw_body, fallback=parsed["text"])

        veo_raw: Any = {}
        if veo_path.exists():
            txt = veo_path.read_text(encoding="utf-8").strip()
            try:
                veo_raw = json.loads(txt) if txt else {}
            except Exception:
                veo_raw = {"_raw_text": txt}

        sd = sd_path.read_text(encoding="utf-8") if sd_path.exists() else ""

        scenes.append({
            "num": num,
            "num_str": num_str,
            "header": parsed["text"],
            "body": body,
            "veo_raw": veo_raw,
            "veo": _normalize_veo(veo_raw, fallback_desc=parsed["text"]),
            "sd_prompt": sd.strip(),
        })
    return scenes


# ───────────────────────── Normalización de VEO ────────────────────────────

# Routing determinístico: subject_type → modelo I2V.
# Espejo de webapp/schemas/cinematic.py::VIDEO_MODEL_ROUTING.
# Se duplica a propósito para mantener el bridge desacoplado de webapp/.
VIDEO_MODEL_ROUTING: dict[str, str] = {
    "human_gesture": "kling-2.5-pro",
    "human_performance": "kling-2.5-pro",
    "creature_animal": "kling-2.5-pro",
    "landscape_static": "runway-gen3-alpha-turbo",
    "landscape_dynamic": "runway-gen3-alpha-turbo",
    "drone_sweep": "runway-gen3-alpha-turbo",
    "subtle_slow_camera": "wan-2.1-14b",
    "object_reveal": "wan-2.1-14b",
    "vfx_heavy": "kling-2.5-pro",
}


def _normalize_veo(veo_raw: Any, fallback_desc: str = "") -> dict:
    """
    Normaliza cualquier forma del JSON de prompt Veo a un dict canónico:
        {
          "descripcion": str,
          "estilo_visual": str,
          "iluminacion": str,
          "locacion": str,
          "ritmo": str,
          "audio": str,
          "entidades": list[dict(id_entidad, descripcion)],
          "planos": list[{
              "plano_id", "descripcion_corta", "duracion_s",
              "tipo_plano", "angulo_lente", "movimiento_camara",
              "entidades_en_plano", "accion_continua", "dialogo_sfx",
              "prompt_veo": str
          }],
          # Si el veo_raw es Master Stack (v2), además:
          "_master_stack": True,
          "_camera": dict, "_visual_anchor": dict, "_motion_intent": dict,
          "_sonic": dict, "_post": dict,
          "_chosen_video_model": str, "_scene_id": str, "_narrative_beat": str,
        }
    Soporta tres formatos:
      1. Master Stack v2 (webapp/schemas/cinematic.py::VeoPrompt) — PREFERIDO
      2. Nested legacy ({parametros_globales, tracking_entidades, secuencia_planos})
      3. Plano legacy ({plano, movimiento, iluminacion})
    """
    empty = {
        "descripcion": "",
        "estilo_visual": "",
        "iluminacion": "",
        "locacion": "",
        "ritmo": "",
        "audio": "",
        "entidades": [],
        "planos": [],
    }
    if not isinstance(veo_raw, dict):
        empty["descripcion"] = fallback_desc
        return empty

    # v2 — Master Stack: detecta por presencia de los 3 bloques canónicos
    if "visual_anchor" in veo_raw and "motion_intent" in veo_raw and "camera" in veo_raw:
        return _normalize_master_stack(veo_raw, fallback_desc)

    pg = veo_raw.get("parametros_globales") or {}
    te = veo_raw.get("tracking_entidades") or {}
    planos_nested = veo_raw.get("secuencia_planos") or []

    # Caso A: formato nested completo
    if planos_nested or pg or te:
        entidades = []
        for bucket_key in ("personajes", "objetos_clave"):
            bucket = te.get(bucket_key) or []
            for item in bucket:
                if not isinstance(item, dict):
                    continue
                entidades.append({
                    "id_entidad": _first_nonempty(item.get("id_entidad"), item.get("id")),
                    "descripcion": _first_nonempty(item.get("descripcion"), item.get("description")),
                    "categoria": bucket_key,
                })
        planos = []
        for p in planos_nested:
            if not isinstance(p, dict):
                continue
            cine = p.get("cinematografia") or {}
            planos.append({
                "plano_id": _first_nonempty(p.get("plano_id"), p.get("id")),
                "descripcion_corta": _first_nonempty(p.get("descripcion_corta"), p.get("descripcion")),
                "duracion_s": _safe_float(p.get("duracion_aprox_seg") or p.get("duracion")),
                "tipo_plano": _first_nonempty(cine.get("tipo_plano"), p.get("plano")),
                "angulo_lente": _first_nonempty(cine.get("angulo_lente"), cine.get("lente")),
                "movimiento_camara": _first_nonempty(cine.get("movimiento_camara"), p.get("movimiento")),
                "entidades_en_plano": p.get("entidades_en_plano") or [],
                "accion_continua": _first_nonempty(p.get("accion_continua"), p.get("accion")),
                "dialogo_sfx": _first_nonempty(p.get("dialogo_sfx"), p.get("dialogo")),
                "prompt_veo": _first_nonempty(p.get("prompt_veo_sintetizado"), p.get("prompt_veo"), p.get("prompt")),
            })
        return {
            "descripcion": _first_nonempty(veo_raw.get("descripcion_escena"), veo_raw.get("descripcion"), fallback_desc),
            "estilo_visual": _first_nonempty(pg.get("estilo_visual"), veo_raw.get("estilo_visual")),
            "iluminacion": _first_nonempty(pg.get("iluminacion_general"), pg.get("iluminacion"), veo_raw.get("iluminacion")),
            "locacion": _first_nonempty(pg.get("locacion")),
            "ritmo": _first_nonempty(pg.get("ritmo")),
            "audio": _first_nonempty(pg.get("audio_ambiental"), pg.get("audio")),
            "entidades": entidades,
            "planos": planos,
        }

    # Caso B: formato plano {plano, movimiento, iluminacion} o mix
    single_plano = {
        "plano_id": "1A",
        "descripcion_corta": _first_nonempty(veo_raw.get("descripcion"), veo_raw.get("descripcion_corta"), fallback_desc),
        "duracion_s": _safe_float(veo_raw.get("duracion")),
        "tipo_plano": _first_nonempty(veo_raw.get("plano"), veo_raw.get("tipo_plano")),
        "angulo_lente": _first_nonempty(veo_raw.get("lente"), veo_raw.get("angulo_lente")),
        "movimiento_camara": _first_nonempty(veo_raw.get("movimiento"), veo_raw.get("movimiento_camara")),
        "entidades_en_plano": [],
        "accion_continua": _first_nonempty(veo_raw.get("accion"), veo_raw.get("accion_continua")),
        "dialogo_sfx": _first_nonempty(veo_raw.get("dialogo"), veo_raw.get("dialogo_sfx")),
        "prompt_veo": _first_nonempty(veo_raw.get("prompt"), veo_raw.get("prompt_veo"), veo_raw.get("raw"), veo_raw.get("_raw_text")),
    }
    has_content = any([
        single_plano["tipo_plano"], single_plano["movimiento_camara"],
        single_plano["prompt_veo"], single_plano["descripcion_corta"],
    ])
    return {
        "descripcion": _first_nonempty(veo_raw.get("descripcion"), fallback_desc),
        "estilo_visual": _first_nonempty(veo_raw.get("estilo_visual"), veo_raw.get("style")),
        "iluminacion": _first_nonempty(veo_raw.get("iluminacion"), veo_raw.get("luz")),
        "locacion": _first_nonempty(veo_raw.get("locacion"), veo_raw.get("lugar")),
        "ritmo": _first_nonempty(veo_raw.get("ritmo")),
        "audio": _first_nonempty(veo_raw.get("audio"), veo_raw.get("audio_ambiental")),
        "entidades": [],
        "planos": [single_plano] if has_content else [],
    }


def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


# ───────────────────────── Master Stack v2 ─────────────────────────────────

def _synthesize_flux_prompt(visual: dict, motion: dict) -> str:
    """
    Construye el prompt denso para FLUX.1 Pro (Fase 1 — Ancla Visual).

    El modelo I2V hereda la calidad del frame 0. Este prompt sintetiza
    los bloques `visual_anchor` y `motion_intent` en una única línea
    cinematográfica densa — no minimalista, para que el generador tenga
    anclas concretas de composición, paleta, lente y textura.
    """
    parts: list[str] = []

    subject = (visual.get("subject_description") or "").strip()
    if subject:
        parts.append(subject)

    env = (visual.get("environment") or "").strip()
    if env:
        parts.append(env)

    comp = (visual.get("composition") or "").strip()
    if comp:
        parts.append(comp)

    palette = visual.get("palette") or []
    if isinstance(palette, list) and palette:
        parts.append("palette: " + ", ".join(str(c) for c in palette if c))

    lighting = (visual.get("lighting") or "").strip()
    if lighting:
        parts.append("lighting: " + lighting)

    textures = (visual.get("textures") or "").strip()
    if textures:
        parts.append("textures: " + textures)

    style = (visual.get("style") or "").strip()
    if style:
        parts.append("style: " + style.replace("_", " "))

    action = (motion.get("action") or "").strip()
    if action:
        # Frame 0: la acción al inicio del plano, no su desarrollo
        parts.append("subject action at frame 0: " + action)

    return ". ".join(p for p in parts if p).strip()


def _normalize_master_stack(veo_raw: dict, fallback_desc: str) -> dict:
    """
    Mapea el schema Master Stack (v2) al dict canónico del bridge.

    Mantiene los campos clásicos (descripcion, estilo_visual, iluminacion,
    locacion, ritmo, audio, entidades, planos) para que el resto del
    pipeline OpenMontage siga funcionando sin tocar, y agrega passthrough
    con prefijo `_` que `_build_scene_plan` consume para enriquecer el
    scene_plan.json con metadata del Master Stack (chosen_video_model,
    visual_anchor para FLUX, motion_intent para routing I2V, sonic para
    Suno/mmaudio, post_production para Fase 3).
    """
    camera = veo_raw.get("camera") or {}
    visual = veo_raw.get("visual_anchor") or {}
    motion = veo_raw.get("motion_intent") or {}
    sonic = veo_raw.get("sonic") or {}
    post = veo_raw.get("post") or {}

    subject_type = motion.get("subject_type", "")
    chosen_model = VIDEO_MODEL_ROUTING.get(subject_type, "kling-2.5-pro")

    # Un único plano por escena — la filosofía Master Stack es:
    # "los I2V rinden mejor en 4-8s; divide escenas, no las estires".
    plano = {
        "plano_id": "1A",
        "descripcion_corta": _first_nonempty(
            motion.get("action"), visual.get("subject_description"), fallback_desc
        ),
        "duracion_s": _safe_float(camera.get("duration_seconds")),
        "tipo_plano": camera.get("shot_type", ""),
        "angulo_lente": f"{camera.get('lens_mm')}mm" if camera.get("lens_mm") else "",
        "movimiento_camara": camera.get("movement", "static"),
        "entidades_en_plano": [],
        "accion_continua": motion.get("action", ""),
        "dialogo_sfx": "; ".join(s for s in (sonic.get("sfx") or []) if s),
        "prompt_veo": _synthesize_flux_prompt(visual, motion),
    }

    # audio legible: diégesis + primer sfx si existe
    audio_bits = []
    if sonic.get("diegetic_sound"):
        audio_bits.append(sonic["diegetic_sound"])
    if sonic.get("music_brief"):
        audio_bits.append("music: " + sonic["music_brief"])
    audio_text = ". ".join(audio_bits)

    return {
        "descripcion": _first_nonempty(motion.get("action"), fallback_desc),
        "estilo_visual": (visual.get("style") or "").replace("_", " "),
        "iluminacion": visual.get("lighting", ""),
        "locacion": visual.get("environment", ""),
        "ritmo": motion.get("motion_intensity", "med"),
        "audio": audio_text,
        "entidades": [],
        "planos": [plano],
        # Passthrough del Master Stack — consumido por _build_scene_plan
        "_master_stack": True,
        "_camera": camera,
        "_visual_anchor": visual,
        "_motion_intent": motion,
        "_sonic": sonic,
        "_post": post,
        "_chosen_video_model": chosen_model,
        "_scene_id": veo_raw.get("scene_id", ""),
        "_scene_number": veo_raw.get("scene_number"),
        "_narrative_beat": veo_raw.get("narrative_beat", ""),
        "_text_on_screen": veo_raw.get("text_on_screen", ""),
        "_director_notes": veo_raw.get("director_notes", ""),
    }


# ───────────────────────── Extracción cinematográfica ──────────────────────

def _match_from_vocab(text: str, vocab: dict[str, str]) -> Optional[str]:
    """Busca la primera coincidencia (keys largas primero) del vocabulario."""
    if not text:
        return None
    low = text.lower()
    # ordenar por longitud descendente para priorizar matches más específicos
    for needle in sorted(vocab.keys(), key=len, reverse=True):
        if needle in low:
            return vocab[needle]
    return None


def _extract_lens_mm(text: str) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"(\d{2,3})\s*mm", text.lower())
    if not m:
        return None
    try:
        val = int(m.group(1))
    except ValueError:
        return None
    allowed = {14, 24, 35, 50, 85, 135, 200}
    if val in allowed:
        return val
    # snap al valor permitido más cercano
    return min(allowed, key=lambda x: abs(x - val))


def _extract_textures(text: str) -> list[str]:
    if not text:
        return []
    low = text.lower()
    seen: list[str] = []
    for word in TEXTURE_VOCAB:
        if word.lower() in low and word not in seen:
            seen.append(word)
    return seen[:6]


def _shot_language_from_veo(veo: dict, header: str, body: str) -> dict:
    """Construye el objeto `shot_language` del schema de OpenMontage."""
    planos = veo.get("planos") or []
    first_plano = planos[0] if planos else {}

    haystack_bits = [
        header, body,
        veo.get("descripcion", ""),
        veo.get("estilo_visual", ""),
        veo.get("iluminacion", ""),
        first_plano.get("tipo_plano", ""),
        first_plano.get("angulo_lente", ""),
        first_plano.get("movimiento_camara", ""),
        first_plano.get("prompt_veo", ""),
        first_plano.get("accion_continua", ""),
    ]
    haystack = " ".join(s for s in haystack_bits if s)

    shot_lang: dict = {}

    shot_size = _match_from_vocab(first_plano.get("tipo_plano", ""), SHOT_SIZE_SYNONYMS) \
                or _match_from_vocab(haystack, SHOT_SIZE_SYNONYMS)
    if shot_size:
        shot_lang["shot_size"] = shot_size

    cam = _match_from_vocab(first_plano.get("movimiento_camara", ""), CAMERA_MOVEMENT_SYNONYMS) \
          or _match_from_vocab(haystack, CAMERA_MOVEMENT_SYNONYMS)
    shot_lang["camera_movement"] = cam or "static"

    lens = _extract_lens_mm(first_plano.get("angulo_lente", "") + " " + haystack)
    if lens:
        shot_lang["lens_mm"] = lens

    lighting = _match_from_vocab(veo.get("iluminacion", ""), LIGHTING_SYNONYMS) \
               or _match_from_vocab(haystack, LIGHTING_SYNONYMS)
    if lighting:
        shot_lang["lighting_key"] = lighting

    dof = _match_from_vocab(haystack, DOF_HINTS)
    if dof:
        shot_lang["depth_of_field"] = dof

    color_temp = _match_from_vocab(veo.get("estilo_visual", "") + " " + veo.get("iluminacion", ""),
                                   COLOR_TEMP_HINTS) \
                 or _match_from_vocab(haystack, COLOR_TEMP_HINTS)
    if color_temp:
        shot_lang["color_temperature"] = color_temp

    return shot_lang


def _narrative_role(index: int, total: int, estructura: str) -> str:
    """
    Asigna narrative_role en base a la posición relativa en la secuencia.
    Respeta la estructura narrativa si viene (THREE_ACT, HERO_JOURNEY, etc.).
    """
    if total <= 1:
        return "deliver_payload"
    pos = (index - 1) / max(total - 1, 1)  # 0..1
    # Primer tercio: establecer / introducir
    if index == 1:
        return "establish_context"
    if pos < 0.15:
        return "introduce_subject"
    # Último 15%: cierre / call to action
    if index == total:
        return "call_to_action" if "CTA" in estructura.upper() else "resolution"
    if pos > 0.85:
        return "resolution"
    # Mitad exacta: hero/payload
    if 0.45 <= pos <= 0.65:
        return "deliver_payload"
    # Cuartos intermedios
    if pos < 0.45:
        return "build_tension"
    return "emotional_beat"


def _hero_moment_index(n_scenes: int) -> int:
    """Índice (1-based) de la escena marcada como hero. Suele ser ~60-70%."""
    if n_scenes <= 2:
        return n_scenes
    return max(1, min(n_scenes, round(n_scenes * 0.65)))


# ───────────────────────── Timestamps ──────────────────────────────────────

def _allocate_timestamps(scenes: list[dict], total_duration_seconds: float) -> list[dict]:
    """
    Distribuye la duración total entre escenas. Si cada escena tiene
    `duracion_aprox_seg` sumada desde sus planos VEO, respeta esas duraciones;
    si no, pondera por largo del cuerpo con mínimo de 2s.
    """
    if not scenes:
        return []

    # Sumar durations de cada escena (si el VEO las trae)
    veo_durations: list[Optional[float]] = []
    for s in scenes:
        planos = (s.get("veo") or {}).get("planos") or []
        total = sum(p.get("duracion_s") or 0 for p in planos)
        veo_durations.append(total if total > 0 else None)

    use_veo = all(d for d in veo_durations)
    if use_veo:
        raw = list(veo_durations)  # type: ignore[assignment]
    else:
        raw = [float(max(len(s["body"]), 20)) for s in scenes]

    w_sum = float(sum(raw))
    if w_sum <= 0:
        raw = [1.0] * len(scenes)
        w_sum = float(len(scenes))

    min_s = 2.0
    # Escalamos al total_duration_seconds
    scaled = [total_duration_seconds * (w / w_sum) for w in raw]
    adjusted = [max(r, min_s) for r in scaled]
    # Re-escalar por si los mínimos inflaron el total
    adj_sum = sum(adjusted)
    if adj_sum > 0:
        scale = total_duration_seconds / adj_sum
        adjusted = [a * scale for a in adjusted]

    out: list[dict] = []
    t = 0.0
    for s, dur in zip(scenes, adjusted):
        start = round(t, 2)
        end = round(t + dur, 2)
        out.append({**s, "start_seconds": start, "end_seconds": end})
        t = end
    # Ajuste final para que la última escena cierre exactamente en total
    if out:
        out[-1]["end_seconds"] = round(total_duration_seconds, 2)
    return out


# ───────────────────────── Builders de artifacts ───────────────────────────

def _select_playbook(formato: str, estilo_visual: str, available: list[str]) -> str:
    """Escoge el style playbook más apropiado y valida que exista."""
    low = (estilo_visual or "").lower()
    # Heurísticas por estilo
    if any(w in low for w in ("anime", "ghibli")):
        candidate = "anime-ghibli"
    elif any(w in low for w in ("minimal", "diagram", "esquem")):
        candidate = "minimalist-diagram"
    elif any(w in low for w in ("clean", "corporat", "profes", "minimal")):
        candidate = "clean-professional"
    else:
        candidate = FORMATO_A_PLAYBOOK.get(formato.upper(), "flat-motion-graphics")
    if candidate in available:
        return candidate
    # fallback al primero disponible, o al default
    return available[0] if available else "flat-motion-graphics"


def _discover_playbooks(openmontage_root: Path) -> list[str]:
    styles = openmontage_root / "styles"
    if not styles.exists():
        return list(DEFAULT_PLAYBOOKS)
    names = [p.stem for p in styles.glob("*.yaml") if p.stem != "playbook_loader"]
    return names or list(DEFAULT_PLAYBOOKS)


def _build_brief(idea: str, title: str, hook: str, key_points: list[str],
                 core_message: str, formato: str, duration_s: float,
                 estructura: str, playbook: str) -> dict:
    tone = "cinematográfico"
    est_upper = (estructura or "").upper()
    if "HERO" in est_upper:
        tone = "épico"
    elif "STORY_CIRCLE" in est_upper or "JOURNEY" in est_upper:
        tone = "emocional, narrativo"
    elif est_upper in ("THREE_ACT", "FIVE_ACT"):
        tone = "cinematográfico"

    return {
        "version": "1.0",
        "title": title,
        "hook": hook,
        "key_points": key_points,
        "core_message": core_message,
        "tone": tone,
        "style": playbook,
        "target_audience": "general",
        "target_platform": FORMATO_A_PLATAFORMA.get(formato.upper(), "generic"),
        "target_duration_seconds": round(float(duration_s), 2),
        "metadata": {
            "source": "Guion_expert",
            "formato_original": formato,
            "estructura_narrativa": estructura,
            "idea_original": idea,
            "generated_at": _now_iso(),
        },
    }


def _build_script(title: str, scenes_timed: list[dict], total_duration: float) -> dict:
    sections = []
    for i, s in enumerate(scenes_timed, start=1):
        body = (s.get("body") or s.get("header") or "").strip()
        if not body:
            body = f"Escena {i}"
        sec = {
            "id": f"sec-{i:03d}",
            "label": f"Escena {i}",
            "text": body[:2000],
            "start_seconds": s["start_seconds"],
            "end_seconds": s["end_seconds"],
        }
        if s.get("header"):
            sec["speaker_directions"] = s["header"][:500]
        sections.append(sec)

    return {
        "version": "1.0",
        "title": title,
        "total_duration_seconds": round(total_duration, 2),
        "sections": sections,
        "metadata": {
            "source": "Guion_expert",
            "generated_at": _now_iso(),
        },
    }


def _asset_description_image(s: dict) -> str:
    """Prompt legible para el generador de imágenes (Stable Diffusion / Flux)."""
    sd = _clean_text(s.get("sd_prompt", ""))
    if sd:
        return sd[:400]
    veo = s.get("veo") or {}
    pieces = []
    if veo.get("estilo_visual"):
        pieces.append(veo["estilo_visual"])
    if veo.get("locacion"):
        pieces.append(veo["locacion"])
    if veo.get("iluminacion"):
        pieces.append(f"{veo['iluminacion']} lighting")
    desc = _clean_text(", ".join(pieces))
    if desc:
        return desc[:400]
    return _clean_text(s.get("header") or s.get("body") or "scene still")[:400]


def _asset_description_video(s: dict) -> str:
    """Prompt legible para el generador de video (Veo / Runway / Pika)."""
    veo = s.get("veo") or {}
    planos = veo.get("planos") or []
    if planos and planos[0].get("prompt_veo"):
        return _clean_text(planos[0]["prompt_veo"])[:480]
    # Construir prompt desde los pedazos
    pieces = []
    if planos and planos[0].get("tipo_plano"):
        pieces.append(planos[0]["tipo_plano"])
    if planos and planos[0].get("movimiento_camara"):
        pieces.append(planos[0]["movimiento_camara"])
    if planos and planos[0].get("descripcion_corta"):
        pieces.append(planos[0]["descripcion_corta"])
    elif veo.get("descripcion"):
        pieces.append(veo["descripcion"])
    if veo.get("iluminacion"):
        pieces.append(f"lighting: {veo['iluminacion']}")
    if veo.get("estilo_visual"):
        pieces.append(f"style: {veo['estilo_visual']}")
    if not pieces:
        pieces.append(s.get("header") or s.get("body") or "scene")
    return _clean_text(". ".join(pieces))[:480]


def _build_scene_plan(scenes_timed: list[dict], estructura: str, playbook: str) -> dict:
    n = len(scenes_timed)
    hero_idx = _hero_moment_index(n)
    master_stack_count = 0

    scenes_out = []
    for i, s in enumerate(scenes_timed, start=1):
        veo = s.get("veo") or {}
        shot_lang = _shot_language_from_veo(veo, s.get("header", ""), s.get("body", ""))

        description = _first_nonempty(
            veo.get("descripcion"),
            s.get("header"),
            s.get("body")[:180] if s.get("body") else "",
        )

        # shot_intent: el "por qué" de este plano
        planos = veo.get("planos") or []
        first_plano = planos[0] if planos else {}
        shot_intent = _first_nonempty(
            first_plano.get("descripcion_corta"),
            veo.get("descripcion"),
            s.get("header"),
        )

        textures = _extract_textures(
            (veo.get("estilo_visual") or "") + " " + (first_plano.get("prompt_veo") or "")
        )

        scene: dict = {
            "id": f"scene-{i:03d}",
            "type": "generated",
            "description": description[:400] or f"Escena {i}",
            "start_seconds": s["start_seconds"],
            "end_seconds": s["end_seconds"],
            "script_section_id": f"sec-{i:03d}",
            "narrative_role": _narrative_role(i, n, estructura),
            "hero_moment": (i == hero_idx),
        }
        if shot_intent:
            scene["shot_intent"] = shot_intent[:300]
        if shot_lang:
            scene["shot_language"] = shot_lang
        if textures:
            scene["texture_keywords"] = textures

        # required_assets: un prompt de imagen (para still/preview) + uno de video
        required: list[dict] = [
            {
                "type": "image",
                "description": _asset_description_image(s),
                "source": "generate",
            },
            {
                "type": "video",
                "description": _asset_description_video(s),
                "source": "generate",
            },
        ]
        scene["required_assets"] = required

        # ─── Master Stack v2 passthrough ───────────────────────────────
        # Si el VEO fue emitido por el Director de Flow (tool use estructurado),
        # enriquecemos la escena con toda la metadata cinematográfica que
        # OpenMontage / fal.ai / Suno / RIFE consumen para producir el video.
        if veo.get("_master_stack"):
            master_stack_count += 1
            ms_camera = veo.get("_camera") or {}
            ms_visual = veo.get("_visual_anchor") or {}
            ms_motion = veo.get("_motion_intent") or {}
            ms_sonic = veo.get("_sonic") or {}
            ms_post = veo.get("_post") or {}

            scene["master_stack"] = {
                # Fase 2: routing determinístico a modelo I2V
                "chosen_video_model": veo.get("_chosen_video_model"),
                "subject_type": ms_motion.get("subject_type"),
                "narrative_beat": veo.get("_narrative_beat"),
                "source_scene_id": veo.get("_scene_id"),
                # Fase 1: ancla visual para FLUX.1 Pro
                "visual_anchor": {
                    "composition": ms_visual.get("composition"),
                    "palette": ms_visual.get("palette") or [],
                    "lighting": ms_visual.get("lighting"),
                    "textures": ms_visual.get("textures"),
                    "style": ms_visual.get("style"),
                    "subject_description": ms_visual.get("subject_description"),
                    "environment": ms_visual.get("environment"),
                    "flux_prompt": first_plano.get("prompt_veo", ""),
                },
                # Fase 2: parámetros de cámara e inyección de movimiento
                "camera": {
                    "shot_type": ms_camera.get("shot_type"),
                    "movement": ms_camera.get("movement"),
                    "lens_mm": ms_camera.get("lens_mm"),
                    "duration_seconds": ms_camera.get("duration_seconds"),
                },
                "motion_intent": {
                    "action": ms_motion.get("action"),
                    "motion_intensity": ms_motion.get("motion_intensity"),
                    "physics_notes": ms_motion.get("physics_notes"),
                },
                # Atmósfera sonora para Suno + mmaudio (SFX)
                "sonic": {
                    "mood": ms_sonic.get("mood") or [],
                    "music_brief": ms_sonic.get("music_brief"),
                    "music_reference_artists": ms_sonic.get("music_reference_artists") or [],
                    "sfx": ms_sonic.get("sfx") or [],
                    "diegetic_sound": ms_sonic.get("diegetic_sound"),
                    "silence_moments": ms_sonic.get("silence_moments"),
                },
                # Fase 3: post-producción (RIFE, Real-ESRGAN, Topaz)
                "post_production": {
                    "target_fps": ms_post.get("target_fps"),
                    "target_resolution": ms_post.get("target_resolution"),
                    "upscale_with": ms_post.get("upscale_with"),
                    "fps_interpolation": ms_post.get("fps_interpolation"),
                },
                # Extras narrativos
                "text_on_screen": veo.get("_text_on_screen") or "",
                "director_notes": veo.get("_director_notes") or "",
            }

            # Re-enriquecemos los required_assets cuando hay Master Stack:
            # el prompt de imagen es el flux_prompt denso, y el video apunta
            # al modelo I2V elegido por routing.
            flux_prompt = first_plano.get("prompt_veo", "")
            if flux_prompt:
                scene["required_assets"] = [
                    {
                        "type": "image",
                        "description": flux_prompt[:480],
                        "source": "generate",
                        "generator_hint": "flux-1.1-pro",
                    },
                    {
                        "type": "video",
                        "description": ms_motion.get("action") or flux_prompt[:480],
                        "source": "generate",
                        "generator_hint": veo.get("_chosen_video_model") or "kling-2.5-pro",
                    },
                ]

        scenes_out.append(scene)

    return {
        "version": "1.0",
        "style_playbook": playbook,
        "scenes": scenes_out,
        "metadata": {
            "source": "Guion_expert",
            "estructura_narrativa": estructura,
            "hero_scene_id": f"scene-{hero_idx:03d}" if n else None,
            "master_stack_scenes": master_stack_count,
            "master_stack_coverage": (master_stack_count / n) if n else 0.0,
            "generated_at": _now_iso(),
        },
    }


def _palette_for_playbook(playbook: str) -> tuple[str, str, str]:
    """Retorna (background, accent, subtitle_color) básicos por playbook."""
    # Valores alineados con /styles/*.yaml
    if playbook == "flat-motion-graphics":
        return "#0F172A", "#7C3AED", "#C4B5FD"
    if playbook == "clean-professional":
        return "#FFFFFF", "#1E40AF", "#64748B"
    if playbook == "anime-ghibli":
        return "#0E1B2B", "#F59E0B", "#FDE68A"
    if playbook == "minimalist-diagram":
        return "#111827", "#22D3EE", "#A5F3FC"
    return "#0F172A", "#7C3AED", "#C4B5FD"


def _build_remotion_cuts(title: str, scenes_timed: list[dict], brief: dict, playbook: str) -> dict:
    """
    Construye cuts.json compatible con render_demo.py (zero-key).
    La duración total del conjunto de cuts coincide EXACTAMENTE con
    brief.target_duration_seconds (no se suma el hero, se asigna dentro).
    """
    total = float(brief["target_duration_seconds"])
    bg, accent, subtitle_color = _palette_for_playbook(playbook)

    # Hero: hasta 3.5s o 12% del total, lo que sea menor (mínimo 2s)
    hero_dur = min(3.5, max(2.0, total * 0.12))
    hero_dur = min(hero_dur, total / 2)  # nunca más de la mitad

    cuts: list[dict] = []
    cuts.append({
        "id": "hero",
        "source": "",
        "type": "hero_title",
        "in_seconds": 0,
        "out_seconds": round(hero_dur, 2),
        "text": title[:80] or "Sin título",
        "subtitle": (brief.get("hook") or "")[:120],
        "backgroundColor": bg,
    })

    # Las escenas comparten (total - hero_dur) escaladas proporcionalmente
    budget = max(total - hero_dur, 2.0)
    if scenes_timed:
        raw_durs = [max(s["end_seconds"] - s["start_seconds"], 0.1) for s in scenes_timed]
        ssum = sum(raw_durs) or 1.0
        scene_durs = [d * (budget / ssum) for d in raw_durs]
    else:
        scene_durs = []

    offset = hero_dur
    for i, (s, dur) in enumerate(zip(scenes_timed, scene_durs), start=1):
        body_text = _clean_text(s.get("body") or s.get("header") or f"Escena {i}")[:240]
        cuts.append({
            "id": f"scene-{i:03d}",
            "source": "",
            "type": "text_card",
            "in_seconds": round(offset, 2),
            "out_seconds": round(offset + dur, 2),
            "text": body_text or f"Escena {i}",
            "backgroundColor": bg,
        })
        offset += dur

    # Ajustar último cut para cerrar exactamente en total (evita derivas)
    if len(cuts) > 1:
        cuts[-1]["out_seconds"] = round(total, 2)

    return {
        "theme": playbook,
        "cuts": cuts,
        "metadata": {
            "source": "Guion_expert → OpenMontage bridge",
            "title": title,
            "total_duration_seconds": round(total, 2),
            "playbook": playbook,
            "generated_at": _now_iso(),
        },
    }


def _build_checkpoint(project_id: str, pipeline: str, playbook: str) -> dict:
    """Paths en `artifacts` son relativos al `project_root` para portabilidad."""
    return {
        "version": "1.0",
        "project_id": project_id,
        "pipeline_type": pipeline,
        "stage": "scene_plan",
        "status": "completed",
        "timestamp": _now_iso(),
        "style_playbook": playbook,
        "checkpoint_policy": "guided",
        "human_approval_required": True,
        "human_approved": True,
        "artifacts": {
            "brief": "stages/brief.json",
            "script": "stages/script.json",
            "scene_plan": "stages/scene_plan.json",
        },
        "metadata": {
            "source": "Guion_expert",
            "next_stage": "assets",
            "note": "Brief, script y scene_plan producidos por Guion_expert. "
                    "El agente de OpenMontage debe iniciar desde la etapa `assets`.",
        },
    }


# ───────────────────────── Validación ──────────────────────────────────────

def _validate_artifacts(openmontage_root: Path, artifacts: dict[str, Any]) -> list[str]:
    """Valida contra JSON Schemas oficiales. Devuelve lista de warnings."""
    warnings: list[str] = []
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return warnings
    schema_map = {
        "brief": openmontage_root / "schemas" / "artifacts" / "brief.schema.json",
        "script": openmontage_root / "schemas" / "artifacts" / "script.schema.json",
        "scene_plan": openmontage_root / "schemas" / "artifacts" / "scene_plan.schema.json",
        "checkpoint": openmontage_root / "schemas" / "checkpoints" / "checkpoint.schema.json",
    }
    for name, data in artifacts.items():
        schema_path = schema_map.get(name)
        if not schema_path or not schema_path.exists():
            continue
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            jsonschema.validate(instance=data, schema=schema)
        except jsonschema.ValidationError as e:
            warnings.append(f"{name}: {e.message}")
        except Exception as e:  # noqa: BLE001
            warnings.append(f"{name}: validación fallida: {e}")
    return warnings


# ───────────────────────── Copia a demo-props ──────────────────────────────

def _copy_cuts_to_demo_props(cuts_path: Path, slug: str, openmontage_root: Path) -> Optional[Path]:
    """
    Copia el cuts.json al directorio de demo-props de Remotion para que
    `python render_demo.py <slug>` funcione directamente.
    """
    demo_props_dir = openmontage_root / "remotion-composer" / "public" / "demo-props"
    if not demo_props_dir.exists():
        return None
    target = demo_props_dir / f"{slug}.json"
    try:
        shutil.copyfile(cuts_path, target)
        return target
    except OSError:
        return None


# ───────────────────────── Entrada principal ───────────────────────────────

def export_project_to_openmontage(
    project_dir: Path,
    openmontage_root: Path,
    idea: str = "",
    brief_hint: Optional[dict] = None,
) -> dict:
    """
    Convierte un proyecto Guion_expert en artifacts OpenMontage listos para
    que el agente continúe desde la etapa `assets`.

    Emite en OpenMontage/projects/<timestamp>-<slug>/:
        stages/brief.json
        stages/script.json
        stages/scene_plan.json
        stages/checkpoint.json
        remotion-cuts.json
        README.md
    Y copia el cuts.json a remotion-composer/public/demo-props/<slug>.json.

    Args:
        project_dir:     ruta a output/YYYYMMDD_HHMMSS dentro de Guion_expert.
        openmontage_root: ruta al clon de OpenMontage (la que contiene schemas/).
        idea:            idea original del usuario (para fallback del brief).
        brief_hint:      overrides opcionales con keys:
                           - idea, formato, title, duration_seconds.

    Returns:
        dict con paths escritos y metadatos (title, num_scenes, pipeline, …).
    """
    project_dir = Path(project_dir)
    openmontage_root = Path(openmontage_root)
    brief_hint = brief_hint or {}

    if not project_dir.exists():
        raise FileNotFoundError(f"No existe project_dir: {project_dir}")
    if not openmontage_root.exists():
        raise FileNotFoundError(f"No existe openmontage_root: {openmontage_root}")

    # 1. Clasificación + idea effective
    clasif = _parse_classification_file(project_dir / "clasificacion" / "result.txt")
    idea_eff = idea or brief_hint.get("idea") or ""
    formato = (brief_hint.get("formato") or clasif["formato"] or "CORTO").upper()
    formato = _override_formato_from_idea(formato, idea_eff)
    estructura = clasif.get("estructura") or "THREE_ACT"

    # 2. Concepto → title/hook/key_points/core_message
    concepto_path = project_dir / "concepto" / "result.txt"
    concepto_text = concepto_path.read_text(encoding="utf-8") if concepto_path.exists() else ""
    title, hook, key_points, core_message = _extract_title_hook(concepto_text, idea_eff)
    if brief_hint.get("title"):
        title = brief_hint["title"]

    # 3. Duración
    if brief_hint.get("duration_seconds"):
        total_duration = float(brief_hint["duration_seconds"])
    elif clasif["duracion_min"] and clasif["duracion_min"] > 0:
        total_duration = float(clasif["duracion_min"]) * 60.0
    else:
        total_duration = float(FORMATO_A_DURACION_SEG.get(formato, 60.0))
    # Sanidad: si el formato es corto pero la duración explotó (>120s), corrige
    if formato in ("REEL", "INSTAGRAM", "TIKTOK", "SHORT", "YOUTUBE_SHORT") and total_duration > 120:
        total_duration = FORMATO_A_DURACION_SEG[formato]

    # 4. Escenas + timestamps
    scenes = _enumerate_scenes(project_dir)
    if not scenes:
        raise ValueError(f"Proyecto sin escenas en {project_dir}. ¿La pipeline corrió completa?")
    scenes_timed = _allocate_timestamps(scenes, total_duration)

    # 5. Style playbook
    available_playbooks = _discover_playbooks(openmontage_root)
    estilo_visual = next((s["veo"].get("estilo_visual") for s in scenes if s["veo"].get("estilo_visual")), "")
    playbook = _select_playbook(formato, estilo_visual, available_playbooks)

    # 6. Pipeline recomendada
    pipeline = FORMATO_A_PIPELINE.get(formato, "cinematic")

    # 7. Build artifacts
    brief = _build_brief(idea_eff, title, hook, key_points, core_message,
                         formato, total_duration, estructura, playbook)
    script = _build_script(title, scenes_timed, total_duration)
    scene_plan = _build_scene_plan(scenes_timed, estructura, playbook)
    cuts = _build_remotion_cuts(title, scenes_timed, brief, playbook)

    # 8. Paths
    slug = _slugify(title)
    timestamp_tag = project_dir.name  # YYYYMMDD_HHMMSS
    project_id = f"{timestamp_tag}-{slug}"
    proj_root = openmontage_root / "projects" / project_id
    stages_dir = proj_root / "stages"
    stages_dir.mkdir(parents=True, exist_ok=True)

    brief_path = stages_dir / "brief.json"
    script_path = stages_dir / "script.json"
    scene_plan_path = stages_dir / "scene_plan.json"
    checkpoint_path = stages_dir / "checkpoint.json"
    cuts_path = proj_root / "remotion-cuts.json"
    readme_path = proj_root / "README.md"

    checkpoint = _build_checkpoint(project_id, pipeline, playbook)

    # 9. Validar
    validation_warnings = _validate_artifacts(openmontage_root, {
        "brief": brief,
        "script": script,
        "scene_plan": scene_plan,
        "checkpoint": checkpoint,
    })
    for w in validation_warnings:
        print(f"[bridge] WARN: {w}")

    # 10. Escribir a disco
    brief_path.write_text(json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8")
    script_path.write_text(json.dumps(script, indent=2, ensure_ascii=False), encoding="utf-8")
    scene_plan_path.write_text(json.dumps(scene_plan, indent=2, ensure_ascii=False), encoding="utf-8")
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2, ensure_ascii=False), encoding="utf-8")
    cuts_path.write_text(json.dumps(cuts, indent=2, ensure_ascii=False), encoding="utf-8")

    # 11. Copiar cuts a demo-props (zero-friction render)
    demo_props_target = _copy_cuts_to_demo_props(cuts_path, slug, openmontage_root)

    # 12. README
    readme_path.write_text(
        _render_project_readme(
            title=title,
            project_id=project_id,
            slug=slug,
            guion_project_dir=project_dir,
            cuts_path=cuts_path,
            demo_props_target=demo_props_target,
            pipeline=pipeline,
            playbook=playbook,
            num_scenes=len(scenes_timed),
            total_duration=total_duration,
            formato=formato,
            validation_warnings=validation_warnings,
        ),
        encoding="utf-8",
    )

    return {
        "project_root": proj_root,
        "project_id": project_id,
        "brief": brief_path,
        "script": script_path,
        "scene_plan": scene_plan_path,
        "checkpoint": checkpoint_path,
        "cuts": cuts_path,
        "readme": readme_path,
        "demo_props_target": demo_props_target,
        "title": title,
        "total_duration_seconds": total_duration,
        "num_scenes": len(scenes_timed),
        "pipeline": pipeline,
        "playbook": playbook,
        "formato": formato,
        "validation_warnings": validation_warnings,
    }


# ───────────────────────── README ──────────────────────────────────────────

def _render_project_readme(
    *,
    title: str,
    project_id: str,
    slug: str,
    guion_project_dir: Path,
    cuts_path: Path,
    demo_props_target: Optional[Path],
    pipeline: str,
    playbook: str,
    num_scenes: int,
    total_duration: float,
    formato: str,
    validation_warnings: list[str],
) -> str:
    warn_block = ""
    if validation_warnings:
        warn_lines = "\n".join(f"- {w}" for w in validation_warnings)
        warn_block = f"\n## ⚠️ Warnings de validación\n\n{warn_lines}\n"

    if demo_props_target:
        render_cmd = f"python render_demo.py {slug}"
        render_note = (
            f"El `cuts.json` ya fue copiado a "
            f"`remotion-composer/public/demo-props/{slug}.json`, "
            f"así que `python render_demo.py {slug}` lo levanta directamente."
        )
    else:
        render_cmd = (
            f"cd remotion-composer && npx remotion render src/index.tsx Explainer "
            f"../projects/{project_id}/render.mp4 --props ../projects/{project_id}/remotion-cuts.json"
        )
        render_note = (
            "No encontré `remotion-composer/public/demo-props/`, así que hay "
            "que llamar a `npx remotion render` directamente (requiere Node + ffmpeg)."
        )

    return f"""# {title}

Proyecto generado por **Guion_expert** y exportado al contrato de **OpenMontage**.

| Campo | Valor |
|-------|-------|
| ID | `{project_id}` |
| Formato original (Guion) | `{formato}` |
| Duración objetivo | `{total_duration:.1f}s` |
| Escenas | `{num_scenes}` |
| Playbook | `{playbook}` |
| Pipeline recomendada | `{pipeline}` |
| Origen | `{guion_project_dir}` |
| Generado | {_now_iso()} |

## Artifacts (contrato OpenMontage)

| Stage | Archivo | Schema |
|-------|---------|--------|
| Brief | `stages/brief.json` | `schemas/artifacts/brief.schema.json` |
| Script | `stages/script.json` | `schemas/artifacts/script.schema.json` |
| Scene Plan | `stages/scene_plan.json` | `schemas/artifacts/scene_plan.schema.json` |
| Checkpoint | `stages/checkpoint.json` | `schemas/checkpoints/checkpoint.schema.json` |

El checkpoint marca `stage=scene_plan`, `status=completed`, `human_approved=true`
y `next_stage=assets`, así que el agente de OpenMontage sabe que puede saltar
las tres primeras etapas del pipeline `{pipeline}` y empezar a generar assets.

## Render rápido (zero-key, solo Remotion)

Desde la raíz de OpenMontage:

```bash
{render_cmd}
```

{render_note}

## Producción completa (con agente OpenMontage)

Abrí el repo `OpenMontage` en Claude Code / Cursor y pedile:

> "Continuá el pipeline `{pipeline}` a partir de
> `projects/{project_id}/stages/`.
> El brief, script, scene_plan y checkpoint ya están listos. Empezá desde la
> etapa `assets`, respetando el `style_playbook={playbook}` del scene_plan."

El agente:
1. Lee `pipeline_defs/{pipeline}.yaml`.
2. Carga el checkpoint → confirma que el scene_plan está aprobado.
3. Genera assets (imágenes / video) siguiendo los `required_assets` de cada
   escena y la gramática cinematográfica del `shot_language`.
4. Compone con Remotion + FFmpeg (o el renderer que fije en proposal).
5. Publica con post-review automático.

## Notas

- La estructura narrativa, el tono y los planos vienen fijados desde
  Guion_expert. El agente de OpenMontage **no debe re-escribir el guion**,
  solo producir el video.
- Si necesitás cambios narrativos, regenerá desde Guion_expert y re-exportá.
- Los `narrative_role`, `hero_moment` y `texture_keywords` del scene_plan
  fueron inferidos automáticamente — reviselos si el resultado se siente
  descompensado.
{warn_block}"""
