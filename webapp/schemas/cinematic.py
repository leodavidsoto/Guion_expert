"""
Master Stack cinematográfico — schema Pydantic para VEO prompts.
=================================================================
El director_flow expert emite una instancia de `VeoPrompt` por escena.
Este schema se usa como `input_schema` de un tool Anthropic
(tool use), eliminando regex + json.loads + fallbacks silenciosos.

Flujo:
    Escena (texto del dialoguista)
        ↓ Claude (tool use, force tool_choice)
    VeoPrompt (JSON validado por Pydantic)
        ├─ CameraPhysics     → metadata (shot, movement, lens, duration)
        ├─ VisualAnchor      → Fase 1: FLUX.1 Pro genera el frame 0 (solo I2V)
        ├─ MotionIntent      → Fase 2: routing multi-backend + modalidad
        │     ├─ human_*     → Kling (API) | SkyReels V1 (Trinity, T2V)
        │     ├─ landscape_* → Runway (API) | Wan 2.1 (Trinity, I2V)
        │     ├─ drone_*     → Runway (API) | Wan 2.1 (Trinity, I2V)
        │     ├─ subtle_*    → WAN 2.1 (API o Trinity, I2V)
        │     └─ vfx_heavy   → Kling (API) | Hunyuan 13B (Trinity, T2V)
        ├─ SonicAtmosphere   → Suno (música) + mmaudio (SFX)
        └─ PostProduction    → Fase 3: RIFE + Real-ESRGAN/Topaz

Trinity hybrid:
    Cada subject_type tiene un "preferido" por backend. El resolver
    (bridge._resolve_backend) lee .env TRINITY_ENABLED:
        - False → siempre usa la columna `api` (fal.ai)
        - True  → intenta `trinity` y si falla cae a `api`

El JSON se guarda en output/<timestamp>/prompts_veo/veo_NNN.json,
lo lee el bridge OpenMontage y se mapea al scene_plan.json.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ============================================================
# Tipos de routing — modalidad y backend
# ============================================================

VideoModality = Literal["i2v", "t2v"]
"""
i2v = Image-to-Video: primero genera imagen ancla (FLUX.1 Pro),
      luego la anima. Máximo control visual. Ideal para paisajes,
      planos cinemáticos lentos, drone shots, reveals.
t2v = Text-to-Video puro: el modelo genera frames + movimiento juntos.
      Mejor para expresiones humanas complejas (SkyReels) y física
      end-to-end como fuego/agua/colisiones (Hunyuan).
"""

Backend = Literal["fal", "trinity", "auto"]
"""
fal     = fal.ai API (Kling, Runway, WAN). Siempre online, $$$.
trinity = Colab self-hosted (Wan 2.1 / SkyReels / Hunyuan).
          $0 si hay GPU disponible, pero depende del notebook encendido.
auto    = el resolver elige según TRINITY_ENABLED del .env + salud del
          endpoint Trinity. Default recomendado.
"""


# ============================================================
# Routing table: subject_type → especificación de ruteo
# ============================================================
# v2 — estructurado por backend + modalidad. Mantiene retrocompat:
# la clave "api_model" cumple la función del viejo VIDEO_MODEL_ROUTING.
# ============================================================

VIDEO_MODEL_ROUTING_V2: dict[str, dict] = {
    # Humanos — Kling (API) preserva rostros; SkyReels (Trinity) entiende
    # matices emocionales gracias a su entrenamiento con 10M de clips de cine.
    "human_gesture": {
        "api_model": "kling-2.5-pro",
        "trinity_model": "skyreels-v1",
        "modality": "t2v",  # SkyReels es T2V nativo; ignora imagen ancla
        "fal_modality": "i2v",  # Kling en fal usa I2V (imagen ancla FLUX)
        "reason": "Humanos necesitan rostros consistentes. SkyReels entrenado en cine/TV.",
    },
    "human_performance": {
        "api_model": "kling-2.5-pro",
        "trinity_model": "skyreels-v1",
        "modality": "t2v",
        "fal_modality": "i2v",
        "reason": "Performance compleja: SkyReels lee prompt emocional mejor sin ancla.",
    },
    "creature_animal": {
        "api_model": "kling-2.5-pro",
        "trinity_model": "skyreels-v1",
        "modality": "t2v",
        "fal_modality": "i2v",
        "reason": "Criaturas con física orgánica: SkyReels > ancla estática.",
    },
    # Landscapes y drones — I2V es oro: frame 0 de FLUX define composición.
    "landscape_static": {
        "api_model": "runway-gen3-alpha-turbo",
        "trinity_model": "wan-2.1-14b",
        "modality": "i2v",
        "fal_modality": "i2v",
        "reason": "Paisaje: composición exacta vía FLUX; modelo solo anima.",
    },
    "landscape_dynamic": {
        "api_model": "runway-gen3-alpha-turbo",
        "trinity_model": "wan-2.1-14b",
        "modality": "i2v",
        "fal_modality": "i2v",
        "reason": "Paisaje con movimiento: I2V mantiene look consistente.",
    },
    "drone_sweep": {
        "api_model": "runway-gen3-alpha-turbo",
        "trinity_model": "wan-2.1-14b",
        "modality": "i2v",
        "fal_modality": "i2v",
        "reason": "Drone shot: FLUX fija horizonte y paleta, Wan/Runway lo animan.",
    },
    # Planos sutiles, lentos y elegantes — WAN 2.1 domina en ambos backends.
    "subtle_slow_camera": {
        "api_model": "wan-2.1-14b",
        "trinity_model": "wan-2.1-14b",
        "modality": "i2v",
        "fal_modality": "i2v",
        "reason": "Plano sutil: el frame 0 manda; Wan 2.1 MoE respeta la imagen.",
    },
    "object_reveal": {
        "api_model": "wan-2.1-14b",
        "trinity_model": "wan-2.1-14b",
        "modality": "i2v",
        "fal_modality": "i2v",
        "reason": "Reveal de objeto: composición crítica en frame 0.",
    },
    # VFX pesado — Hunyuan aprendió física end-to-end, T2V puro es su fuerte.
    "vfx_heavy": {
        "api_model": "kling-2.5-pro",
        "trinity_model": "hunyuan-13b",
        "modality": "t2v",
        "fal_modality": "i2v",
        "reason": "Física compleja (fuego/agua/humo): Hunyuan T2V > Kling I2V.",
    },
}


# ============================================================
# Retrocompat: VIDEO_MODEL_ROUTING (v1, plano) mantenido como alias.
# ============================================================

VIDEO_MODEL_ROUTING: dict[str, str] = {
    k: v["api_model"] for k, v in VIDEO_MODEL_ROUTING_V2.items()
}


def choose_video_model(subject_type: str | None, backend: Backend = "fal") -> str:
    """Routing determinístico: dado el tipo de sujeto, devuelve el modelo recomendado.

    Args:
        subject_type: clave del routing (ej. 'human_gesture').
        backend: 'fal' (API) | 'trinity' (Colab self-hosted) | 'auto'.

    Fallback a kling-2.5-pro (fal) si el subject_type no está mapeado.
    """
    if not subject_type:
        return "kling-2.5-pro"
    spec = VIDEO_MODEL_ROUTING_V2.get(subject_type)
    if not spec:
        return "kling-2.5-pro"
    if backend == "trinity":
        return spec["trinity_model"]
    return spec["api_model"]


def choose_modality(subject_type: str | None, backend: Backend = "fal") -> VideoModality:
    """Dada la escena y el backend, retorna la modalidad óptima (i2v/t2v).

    Razonamiento:
      - En Trinity: cada modelo tiene su modalidad nativa (Wan=I2V, SkyReels/Hunyuan=T2V).
      - En fal.ai: todos los modelos soportan I2V vía imagen ancla FLUX; usamos esa ruta
        para máxima consistencia visual en los camino API-first.
    """
    if not subject_type:
        return "i2v"
    spec = VIDEO_MODEL_ROUTING_V2.get(subject_type)
    if not spec:
        return "i2v"
    if backend == "trinity":
        return spec["modality"]
    return spec.get("fal_modality", "i2v")


def routing_reason(subject_type: str | None) -> str:
    """Devuelve una descripción human-readable del por qué del ruteo."""
    if not subject_type:
        return "Fallback: subject_type ausente → kling-2.5-pro (fal) I2V."
    spec = VIDEO_MODEL_ROUTING_V2.get(subject_type)
    if not spec:
        return f"Fallback: subject_type '{subject_type}' no mapeado → kling."
    return spec["reason"]


# ============================================================
# Bloques del Master Stack
# ============================================================


class CameraPhysics(BaseModel):
    """Física de cámara: tipo de plano, movimiento, lente, duración."""

    shot_type: Literal[
        "extreme_wide",
        "wide",
        "medium_wide",
        "medium",
        "medium_close",
        "close_up",
        "extreme_close_up",
        "over_shoulder",
        "pov",
        "dutch_angle",
        "aerial",
        "drone_top_down",
    ] = Field(description="Tipo de plano (framing).")

    movement: Literal[
        "static",
        "dolly_in",
        "dolly_out",
        "truck_left",
        "truck_right",
        "pan_left",
        "pan_right",
        "tilt_up",
        "tilt_down",
        "tracking",
        "handheld",
        "crane_up",
        "crane_down",
        "orbit_left",
        "orbit_right",
    ] = Field(description="Movimiento de cámara. 'static' para planos fijos.")

    lens_mm: Literal[14, 24, 35, 50, 85, 135] = Field(
        default=35,
        description="Focal del lente en mm. 24=wide, 35=estándar, 50=normal, 85=retrato, 135=tele.",
    )

    duration_seconds: float = Field(
        ge=1.0,
        le=15.0,
        description="Duración del plano en segundos (1-15). Los modelos I2V rinden mejor en 4-8s.",
    )


class VisualAnchor(BaseModel):
    """Fase 1 — Ancla visual. Alimenta FLUX.1 Pro para generar el frame 0.

    Si la imagen base es 10/10, el video hereda ese 10/10.
    Nunca dejar que el modelo de video aluciana la composición.
    """

    composition: str = Field(
        min_length=10,
        description="Regla de composición: tercios, golden ratio, centrado, simetría, leading lines, profundidad de campo.",
    )
    palette: list[str] = Field(
        min_length=1,
        max_length=6,
        description="Paleta cromática en 2-6 tokens. Ej: ['amber warm key', 'deep teal shadows', 'rim orange'].",
    )
    lighting: str = Field(
        min_length=10,
        description="Setup de iluminación técnico: key/fill/rim, motivación narrativa, calidad (dura/suave), dirección.",
    )
    textures: list[str] = Field(
        default_factory=list,
        description="Texturas distintivas que FLUX debe preservar: 'grano 35mm fino', 'flare anamórfico', 'piel porosa'.",
    )
    style: Literal[
        "photoreal_8k",
        "cinematic_35mm_kodak",
        "cinematic_35mm_fuji",
        "editorial_fashion",
        "documentary_handheld",
        "dystopian_graded",
        "anime_still",
        "noir_bw",
        "vintage_70s",
        "y2k_digital",
        "indie_a24",
    ] = Field(
        default="cinematic_35mm_kodak",
        description="Estilo visual global. Determina grading, grano y vibe fotográfico.",
    )
    subject_description: str = Field(
        min_length=10,
        description="Descripción precisa del sujeto visible: edad, físico, vestimenta, expresión, pose exacta.",
    )
    environment: str = Field(
        min_length=5,
        description="Set/locación: elementos clave del fondo, clima, hora del día, weather.",
    )


class MotionIntent(BaseModel):
    """Fase 2 — Intención de movimiento. Alimenta el router I2V.

    El `subject_type` es el driver del routing automático a Kling/Runway/WAN.
    """

    subject_type: Literal[
        "human_gesture",
        "human_performance",
        "landscape_static",
        "landscape_dynamic",
        "drone_sweep",
        "subtle_slow_camera",
        "vfx_heavy",
        "object_reveal",
        "creature_animal",
    ] = Field(
        description=(
            "Tipo de sujeto/plano — driver del routing. "
            "human_* → Kling (mejor para rostros). "
            "landscape_* y drone_* → Runway (mejor físicas de mundo). "
            "subtle_slow_camera y object_reveal → WAN 2.1 (sutileza). "
            "vfx_heavy → Kling."
        )
    )
    action: str = Field(
        min_length=10,
        description="Acción específica del plano en 1-2 frases. Qué se mueve, en qué dirección, a qué velocidad.",
    )
    motion_intensity: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Intensidad global del movimiento. Low = casi estático, High = cámara/sujeto muy dinámicos.",
    )
    physics_notes: str = Field(
        default="",
        description="Físicas a preservar: 'cabello sigue viento derecha', 'polvo suspendido en rayos de sol', 'agua cámara lenta'.",
    )


class SonicAtmosphere(BaseModel):
    """Brief sonoro rico. Alimenta Suno (música) + mmaudio/stable-audio (SFX/foley).

    Nace del dialoguista (que describe atmósfera al final de cada escena)
    y se estructura acá por el director_flow.
    """

    mood: list[str] = Field(
        min_length=1,
        max_length=5,
        description="Tono emocional en 1-5 keywords. Ej: ['melancólico', 'tensión ascendente', 'esperanza velada'].",
    )
    music_brief: str = Field(
        min_length=20,
        description=(
            "Prompt completo para Suno: género, instrumentación, BPM, tonalidad, dinámicas. "
            "Ej: 'cinematic orchestral, cuerdas suspendidas con piano minimalista, 70bpm, "
            "Am menor, crescendo suave hacia el beat final'."
        ),
    )
    music_reference_artists: list[str] = Field(
        default_factory=list,
        description="Artistas/scores de referencia: 'Hans Zimmer late career', 'Jóhann Jóhannsson', 'Max Richter'.",
    )
    sfx: list[str] = Field(
        default_factory=list,
        description="Efectos de sonido específicos: 'viento lejano entre hojas', 'pasos sobre grava mojada', 'reloj distante tictac'.",
    )
    diegetic_sound: str = Field(
        default="",
        description="Sonido que existe dentro del mundo (lo que los personajes oyen en la escena).",
    )
    silence_moments: list[str] = Field(
        default_factory=list,
        description="Momentos donde el silencio narra: 'silencio absoluto durante el beat del reconocimiento, 2s'.",
    )


class PostProduction(BaseModel):
    """Fase 3 — Post-producción. Indica la finish line."""

    target_fps: Literal[24, 30, 60] = Field(
        default=24,
        description="FPS final. 24=cinematográfico, 60=cámara lenta/hyperreal.",
    )
    target_resolution: Literal["1080p", "4k"] = Field(
        default="1080p",
        description="Resolución final entregable.",
    )
    upscale_with: Literal["real_esrgan", "topaz", "none"] = Field(
        default="none",
        description="Pipeline de upscaling. real_esrgan corre via fal.ai; topaz es offline.",
    )
    fps_interpolation: Literal["rife", "none"] = Field(
        default="none",
        description="Interpolación de frames. RIFE sube 24→60fps para slo-mo ultra suave.",
    )


# ============================================================
# Top-level: VeoPrompt (lo que Claude emite por escena)
# ============================================================


class VeoPrompt(BaseModel):
    """Master Stack completo de una escena. Consumible por OpenMontage.

    Producido por el expert `director_flow` via Anthropic tool use.
    Se persiste en `output/<timestamp>/prompts_veo/veo_NNN.json`.
    """

    scene_id: str = Field(
        pattern=r"^scene-\d{3}$",
        description="ID canónico de la escena. Formato: 'scene-001', 'scene-002'.",
    )
    scene_number: int = Field(ge=1, description="Número de escena (1-based).")
    narrative_beat: Literal[
        "setup",
        "inciting_incident",
        "rising_action",
        "midpoint",
        "crisis",
        "climax",
        "falling_action",
        "resolution",
        "epilogue",
    ] = Field(
        default="rising_action",
        description="Rol narrativo de la escena en la estructura global.",
    )

    camera: CameraPhysics
    visual_anchor: VisualAnchor
    motion_intent: MotionIntent
    sonic: SonicAtmosphere
    post: PostProduction = Field(default_factory=PostProduction)

    text_on_screen: str = Field(
        default="",
        description="Texto superpuesto (subtítulos, títulos, lower thirds). Vacío si no hay.",
    )
    director_notes: str = Field(
        default="",
        description="Notas libres del director para el equipo o el operador de OpenMontage.",
    )

    # ─────────────────── Trinity hybrid routing (v2) ───────────────────
    preferred_backend: Backend = Field(
        default="auto",
        description=(
            "Preferencia de backend para esta escena. "
            "'auto' = el resolver decide según TRINITY_ENABLED + salud del endpoint. "
            "'fal' = forzar API (fal.ai) — usar si la escena es crítica y necesita cero latencia. "
            "'trinity' = forzar Colab self-hosted — usar si el notebook está corriendo y hay presupuesto de GPU."
        ),
    )
    modality_override: Optional[VideoModality] = Field(
        default=None,
        description=(
            "Opcional. Fuerza I2V o T2V ignorando el default del subject_type. "
            "Dejá en null para que el resolver use la modalidad recomendada. "
            "Usá 'i2v' si querés FLUX ancla aunque el modelo soporte T2V."
        ),
    )
    routing_reason: str = Field(
        default="",
        description=(
            "Razón en una frase de por qué elegiste este subject_type / modalidad / backend. "
            "Auditable — se guarda en el scene_plan y sirve para debuggear elecciones del director."
        ),
    )

    def chosen_video_model(self, backend: Backend = "fal") -> str:
        """Modelo recomendado para esta escena (routing determinístico).

        Args:
            backend: 'fal' (API) | 'trinity' (Colab). El resolver final lo pasa
                según TRINITY_ENABLED y la elección explícita del director.
        """
        return choose_video_model(self.motion_intent.subject_type, backend)

    def chosen_modality(self, backend: Backend = "fal") -> VideoModality:
        """Modalidad recomendada (I2V vs T2V). Respeta modality_override si viene."""
        if self.modality_override is not None:
            return self.modality_override
        return choose_modality(self.motion_intent.subject_type, backend)


# ============================================================
# Smoke test
# ============================================================

if __name__ == "__main__":
    import json as _json

    example = VeoPrompt(
        scene_id="scene-007",
        scene_number=7,
        narrative_beat="crisis",
        camera=CameraPhysics(
            shot_type="close_up",
            movement="dolly_in",
            lens_mm=85,
            duration_seconds=5.5,
        ),
        visual_anchor=VisualAnchor(
            composition="Sujeto en tercio izquierdo, ventana a contraluz en tercio derecho, profundidad de campo marcada.",
            palette=["amber warm key", "deep teal shadows", "rim orange suave"],
            lighting="Key motivada desde ventana (golden hour lateral 45°). Fill mínimo. Rim trasero orange para separar del fondo.",
            textures=["grano 35mm Kodak fino", "leve flare anamórfico", "textura de piel porosa"],
            style="cinematic_35mm_kodak",
            subject_description="María, 40s, cubierta de grasa del motor, mirada baja. Vestido con overol gris gastado. Expresión de vergüenza contenida.",
            environment="Garaje rural, luz de ventana al atardecer, motor desarmado al fondo, polvo suspendido en los rayos.",
        ),
        motion_intent=MotionIntent(
            subject_type="human_performance",
            action="María lentamente levanta la mirada hacia la cámara, entreabriendo los labios como si fuera a hablar y luego se detiene.",
            motion_intensity="low",
            physics_notes="Polvo suspendido en los rayos de sol, cabello suelto sigue ligeramente una brisa izquierda-derecha.",
        ),
        sonic=SonicAtmosphere(
            mood=["melancólico", "tensión contenida", "intimidad confesional"],
            music_brief=(
                "Piano minimalista solo, 60bpm, Am menor. Notas largas y sostenidas con silencios "
                "entre frase y frase. Sin percusión. Volumen bajo. Termina en decrescendo."
            ),
            music_reference_artists=["Jóhann Jóhannsson", "Max Richter (Songs from Before)"],
            sfx=["tictac lejano de un reloj", "crujido sutil del overol al moverse", "viento leve entrando por ventana"],
            diegetic_sound="El motor está apagado. Solo sonidos de la casa vacía.",
            silence_moments=["1.5s de silencio absoluto cuando María entreabre los labios, antes de decidir no hablar"],
        ),
        post=PostProduction(
            target_fps=24,
            target_resolution="4k",
            upscale_with="real_esrgan",
            fps_interpolation="none",
        ),
        text_on_screen="",
        director_notes="Plano clave de la crisis del acto 2. El subtexto es todo.",
        preferred_backend="auto",
        modality_override=None,
        routing_reason="human_performance íntimo: Kling (fal) o SkyReels (trinity) T2V por matiz emocional.",
    )

    print("✅ VeoPrompt instanciado correctamente\n")
    print(f"  scene_id:                   {example.scene_id}")
    print(f"  narrative_beat:             {example.narrative_beat}")
    print(f"  shot_type:                  {example.camera.shot_type}")
    print(f"  movement:                   {example.camera.movement}")
    print(f"  lens:                       {example.camera.lens_mm}mm")
    print(f"  duration:                   {example.camera.duration_seconds}s")
    print(f"  subject_type:               {example.motion_intent.subject_type}")
    print(f"  preferred_backend:          {example.preferred_backend}")
    print(f"  → chosen_model (fal):       {example.chosen_video_model('fal')}")
    print(f"  → chosen_model (trinity):   {example.chosen_video_model('trinity')}")
    print(f"  → chosen_modality (fal):    {example.chosen_modality('fal')}")
    print(f"  → chosen_modality (trinity):{example.chosen_modality('trinity')}")
    print(f"  routing_reason:             {example.routing_reason}")
    print(f"  style:                      {example.visual_anchor.style}")
    print(f"  mood:                       {example.sonic.mood}")
    print(f"  upscale:                    {example.post.upscale_with}")
    print(f"\n  JSON schema fields: {len(VeoPrompt.model_json_schema()['properties'])}")
    print(f"  Routing table v2 size: {len(VIDEO_MODEL_ROUTING_V2)}")
    print(f"  Routing table v1 (alias): {len(VIDEO_MODEL_ROUTING)}")

    # Verificar que el JSON schema sea válido para Anthropic tool use
    schema = VeoPrompt.model_json_schema()
    print(f"\n  JSON schema exportable: type={schema['type']}, required={len(schema.get('required', []))} fields")

    # Sanity: serialize → deserialize round-trip
    payload = _json.loads(example.model_dump_json())
    roundtrip = VeoPrompt.model_validate(payload)
    assert roundtrip.scene_id == example.scene_id
    assert roundtrip.chosen_video_model() == example.chosen_video_model()
    print("  Round-trip JSON ↔ Pydantic: OK")

    # Retrocompat: VeoPrompt sin los nuevos campos aún debe validar.
    legacy_payload = {k: v for k, v in payload.items()
                      if k not in {"preferred_backend", "modality_override", "routing_reason"}}
    legacy_roundtrip = VeoPrompt.model_validate(legacy_payload)
    assert legacy_roundtrip.preferred_backend == "auto"  # default
    assert legacy_roundtrip.modality_override is None
    print("  Retrocompat (JSON viejo sin campos nuevos): OK")
