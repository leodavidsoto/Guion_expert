# I2V State of the Art — Guion_expert
> Referencia técnica para el pipeline i2v · Edición Abril 2026
> Fuente canónica para el Director Flow (Expert 7), el Bridge y el VeoPrompt schema.

---

## 1. Contexto en el pipeline

El pipeline de Guion_expert genera `VeoPrompt` objects para cada escena. Estos prompts son consumidos por modelos I2V (Image-to-Video) vía `VIDEO_MODEL_ROUTING_V2`. Este documento centraliza:

- Los modelos I2V disponibles y su routing determinístico
- El estado del arte en técnicas de montaje generativo aplicables
- Cómo integrar match-cuts IA, next-shot generation y coherencia de keyframes
- Referencias de benchmarks para evaluar comprensión cinematográfica en VLMs

---

## 2. VIDEO_MODEL_ROUTING_V2

Tabla de routing determinístico (no delegado al LLM). El LLM elige `subject_type`; la tabla hace el routing.

| subject_type | Modelo | Modalidad | Backend | Notas |
|---|---|---|---|---|
| `human_portrait` | `kling-v2-master` | i2v | fal.ai | Mejor coherencia facial multi-frame |
| `action_sequence` | `kling-v2-master` | i2v | fal.ai | Motion tracking superior |
| `environment_wide` | `wan-i2v` | i2v | fal.ai | Grandes planos con parallax natural |
| `abstract_motion` | `runway-gen4` | t2v | fal.ai | Fluidos, partículas, abstracción |
| `product_showcase` | `hunyuan-video` | t2v | trinity/Colab | Alta fidelidad de objeto |
| `skyline_timelapse` | `skyreels-v2` | t2v | fal.ai | Time-lapse urbano coherente |

**Regla:** si `subject_type` no está en la tabla → fallback a `wan-i2v`.  
**Implementación:** `webapp/schemas/cinematic.py` → `VIDEO_MODEL_ROUTING_V2` dict.

---

## 3. Match-Cut Generativo — MatchDiffusion (ICCV 2025)

### Qué es

Primer método **training-free** para generar match-cuts entre dos prompts textuales usando el proceso de difusión inversa.

### Arquitectura

```
Prompt A ──┐
           ├─ Joint Diffusion (primeros K pasos) ──► estructura compartida
Prompt B ──┘
           │
           ├─ Disjoint Diffusion (últimos pasos) ──► semánticas distintas
           │
        frames intermedios de transición morphing
```

- **Joint Diffusion (K=15):** las predicciones de ruido de ambos prompts se combinan → estructura visual compartida entre planos.
- **Disjoint Diffusion (10 pasos):** los caminos divergen → cada prompt mantiene su semántica.

### Cuándo usarlo en Guion_expert

El Director Flow puede solicitar match-cuts entre escenas con sujetos compositivamente similares **sin footage real**. MatchDiffusion genera los frames de transición.

```json
{
  "transition_type": "morph_match",
  "method": "match_diffusion",
  "source_prompt": "woman in red dress, backlit window, Rembrandt lighting",
  "target_prompt": "candle flame, same warm backlight, 3200K",
  "joint_steps": 15,
  "disjoint_steps": 10,
  "similarity_threshold": 0.78
}
```

**Umbral de similitud:** si el score de similitud composicional entre dos VeoPrompts supera `0.78`, el bridge puede proponer MatchDiffusion como transición automática.

### Integración en el Bridge

`bridge/openmontage_export.py` → campo `edit_decisions[].transition`:

```python
if similarity_score(prompt_a, prompt_b) >= MATCH_DIFFUSION_THRESHOLD:
    transition = {
        "type": "morph_match",
        "method": "match_diffusion",
        "source_prompt": prompt_a.visual_anchor,
        "target_prompt": prompt_b.visual_anchor,
        "joint_steps": 15,
        "disjoint_steps": 10,
    }
```

---

## 4. Next-Shot Generation — Cut2Next (2025)

### Qué es

Transformer de Difusión (DiT) + **Hierarchical Multi-Prompting** para generar el plano subsecuente respetando patrones de edición puros (shot/reverse-shot, cutaway) manteniendo coherencia cinematográfica.

### Cuándo usarlo en Guion_expert

Cuando el `asset_manifest` no tiene footage suficiente para cubrir una escena. Cut2Next genera el plano de cobertura necesario.

### Patrones de edición soportados

| Patrón | Descripción | Uso en pipeline |
|---|---|---|
| Shot/Reverse-Shot | Alternancia entre dos sujetos en diálogo | Escenas de diálogo (Expert 5 → Expert 7) |
| Cutaway | Plano de reacción o detalle mientras continúa audio | B-roll de contexto |
| Insert | Close-up de objeto relevante al plot | Beats de revelación |
| POV | Plano subjetivo del personaje | Momentos de tensión/descubrimiento |

### Parámetros para el VeoPrompt

```python
class Cut2NextRequest(BaseModel):
    preceding_shot_prompt: str          # VeoPrompt del plano anterior
    editing_pattern: Literal[
        "shot_reverse_shot",
        "cutaway",
        "insert",
        "pov"
    ]
    narrative_context: str              # Resumen de la escena (≤100 tokens)
    character_pov: Optional[str]        # ID del personaje si es POV
```

---

## 5. Coherencia de Keyframes — CineVerse (2025)

### Qué es

Síntesis de keyframes coherentes para storyboards secuenciales. Preserva personajes y geografía a través de múltiples ángulos **simultáneamente**.

### Por qué importa

Los VLMs actuales (según CineTechBench NeurIPS 2025) tienen deficiencias en razonamiento espacial de cámara complejo. CineVerse compensa esto generando frames de referencia consistentes que el Director Flow puede usar como `visual_anchor` en el VeoPrompt.

### Uso en el `scene_plan` stage

```python
# En _stage_prompts_sd() — después de generar visual_anchor por escena
# CineVerse asegura que personaje X en escena 3 es visualmente idéntico
# al personaje X en escena 15, aunque el ángulo sea distinto.

cineverse_request = {
    "character_id": bible.characters[0].character_id,
    "physical_signature": bible.characters[0].physical_signature,
    "scene_indices": [3, 7, 12, 15],     # escenas donde aparece
    "angles": ["frontal", "profile", "3/4", "back"],
    "lighting_base": bible.visual_dna.lighting_signature
}
```

### Integración con Story Bible

`physical_signature` del `CharacterProfile` (Story Bible) es el input de CineVerse. La coherencia visual entre escenas queda garantizada porque ambos sistemas usan la misma descripción inmutable del personaje.

---

## 6. Benchmarks de Evaluación — CineTechBench / ShotBench (NeurIPS 2025)

### Dimensiones evaluadas

| Dimensión | Descripción | Relevancia para Guion_expert |
|---|---|---|
| Shot scale | ELS / LS / MS / MCU / CU / ECU | Director Flow debe especificarlo en VeoPrompt |
| Camera angle | Normal / Low / High / Dutch / Overhead | Parte de `camera_physics` block |
| Composition | Rule of thirds / Golden ratio / Symmetry | `visual_anchor` block |
| Camera movement | Static / Pan / Tilt / Dolly / Zoom / Handheld | One Primary Motion Rule |
| Lighting | Tipo + motivación + ratio | `post_production` block con Kelvin |
| Color | Temperatura, paleta, contraste | Story Bible `visual_dna` |
| Focal length | Focal range + efecto psicológico | Lens library en Expert 7 |
| Continuity | Continuidad entre planos | Expert 8 (Continuity QA) |

### Conclusión de los benchmarks

> Los VLMs actuales aún tienen deficiencias en razonamiento espacial de cámara complejo.

**Implicación:** no delegar el routing I2V ni las decisiones de lens/lighting al LLM. Usar los Style Playbooks + VeoPrompt con restricciones duras como compensación. El Expert 8 (Continuity QA) existe precisamente porque los modelos fallen en esta dimensión.

---

## 7. Montaje Generativo End-to-End — AutoCut (2025)

### Qué es

Framework end-to-end para edición automatizada basado en **discretización multimodal (RQ-VAE)**:

```
script tokens + frame tokens + audio tokens → espacio unificado RQ-VAE → decisiones de edición
```

### Inspiración arquitectónica

La arquitectura de tokens unificados de AutoCut inspira el diseño del compositor de OpenMontage. En Guion_expert, el equivalente es la serialización del `edit_decisions` manifest en el bridge: texto + VeoPrompts + beat_timing convergen en un único JSON que OpenMontage consume.

---

## 8. VideoAgent — dos sistemas, un nombre

Existen dos frameworks independientes con el mismo nombre y propósitos distintos. Es importante no confundirlos:

| Aspecto | VideoAgent (PKU-YuanGroup, ECCV 2024) | VideoAgent (HKUDS) |
|---|---|---|
| Propósito | Responder preguntas sobre video (QA) | Entender y **editar** video |
| Arquitectura | Memoria multimodal aumentada + LLM agente | Dynamic Graph Workflow Orchestration |
| Mecanismo | Recuperación de frames relevantes via embeddings | Grafos de tareas dinámicos + reflexión iterativa |
| Relevancia para Guion_expert | Análisis de footage existente | Modelo de orquestación para el Edit Director |

El sistema HKUDS es el análogo arquitectónico de LangGraph aplicado a decisiones de montaje: descompone intenciones de edición en sub-tareas con bucles de reflexión, exactamente lo que hace OpenMontage con sus director skills.

---

## 10. Integración completa en el pipeline

```
[Expert 7 — Director Flow]
    │ genera VeoPrompt (Master Stack)
    │ One Primary Motion Rule
    │ Kelvin + Lens + Lighting taxonomy
    ▼
[_verify_veo_against_bible() — M5]
    │ detecta style drift
    │ corrige via model_copy()
    ▼
[Bridge — openmontage_export.py]
    │ similarity_check → MatchDiffusion si score >= 0.78
    │ coverage_check → Cut2Next si asset falta
    │ keyframe_coherence → CineVerse para personajes multi-escena
    │ beat_alignment → librosa beat_track (±50ms)
    ▼
[edit_decisions manifest]
    │ transición por par de clips
    │ beat_timing array
    │ subject_type → VIDEO_MODEL_ROUTING_V2
    ▼
[OpenMontage]
    │ playbook_cinematic_trailer.yaml
    │ RUDIMENTOS_MONTAJE.md como referencia canónica
    ▼
[Render — Remotion / Shotstack / Creatomate]
```

### Ejemplo de invocación end-to-end (Python)

```python
import yaml
from webapp.schemas import EditTransition

# 1. Cargar y validar playbook
playbook = yaml.safe_load(open("../OpenMontage/styles/playbook_cinematic_trailer.yaml"))
assert playbook["render"]["runtime"] == "remotion@4"  # locked — governance violation si cambia

# 2. Asset generation desde VeoPrompts del pipeline
shots = asset_gen_agent.generate_shots(
    script=script_brief,
    style=playbook["palette"] | playbook["motion"],
    n_shots=12
)

# 3. Análisis VLM + detección de match-cuts via SigLIP2 embeddings
embeddings = vl_analyst.embed_shots(shots, model="siglip2")
match_pairs = vl_analyst.find_match_cuts(embeddings, threshold=0.78)

# 4. Construcción del edit_decisions manifest con EditTransition
transitions = []
for i, (shot_a, shot_b) in enumerate(zip(shots[:-1], shots[1:])):
    score = match_pairs.get((i, i+1), {}).get("score", 0.0)
    if score >= 0.78:
        t = EditTransition(
            transition_type="morph_match",
            match_diffusion_source_prompt=shot_a.visual_anchor,
            match_diffusion_target_prompt=shot_b.visual_anchor,
            similarity_score=score,
        )
    else:
        t = EditTransition(transition_type="smash_cut", beat_aligned=True)
    transitions.append(t)

# 5. Quality gate assertion
for gate in playbook["quality_gates"]:
    assert eval(gate["metric"]), f"Gate '{gate['id']}' failed — severity: {gate['severity']}"
```

---

## 11. Beat Tracking para Cut-on-Beat

El pipeline usa `librosa` para edición beat-aligned:

```python
import librosa, numpy as np

y, sr = librosa.load("track.mp3")
# Separar componente percusiva para mejor detección
y_harm, y_perc = librosa.effects.hpss(y)
onset_env = librosa.onset.onset_strength(y=y_perc, sr=sr, aggregate=np.median)
tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
beat_times = librosa.frames_to_time(beat_frames, sr=sr)

# Generar puntos de corte como metadata
cut_points = [{"time_s": float(t), "type": "beat"} for t in beat_times]
```

Los `beat_times` alimentan el campo `beat_timing` del `edit_decisions` artifact.  
Tolerancia máxima: **±50ms** entre corte y beat.

---

## 12. Detección de Puntos para Invisible Cut

Heurística para encontrar frames ideales de juntura (oscuridad, blur, oclusión):

```python
def find_invisible_cut_points(frames, blur_threshold=85, black_threshold=10):
    points = []
    for i, frame in enumerate(frames):
        avg_luminance = frame.mean()
        blur_score = cv2.Laplacian(frame, cv2.CV_64F).var()
        if avg_luminance < black_threshold or blur_score < blur_threshold:
            points.append(i)
    return points
```

---

## 13. EditTransition schema (webapp/schemas/cinematic.py)

Agregar al schema existente para representar transiciones en el `edit_decisions` manifest:

```python
from typing import Literal, Optional
from pydantic import BaseModel, Field

class EditTransition(BaseModel):
    """Transición entre dos clips en el edit_decisions manifest."""
    transition_type: Literal[
        "smash_cut",
        "whip_pan",
        "invisible_cut",
        "cross_dissolve",
        "additive_dissolve",
        "film_dissolve",
        "dip_to_black",
        "dip_to_white",
        "dip_to_color",
        "iris_open",
        "iris_close",
        "wipe_horizontal",
        "wipe_vertical",
        "wipe_diagonal",
        "morph_match",
        "freeze_frame",
        "speed_ramp",
        "reverse_cut",
        "match_cut_graphic",
        "match_cut_eyeline",
        "match_cut_action",
        "match_cut_audio_j",     # J-cut: audio B antes de video B
        "match_cut_audio_l",     # L-cut: audio A sobre video B
    ]
    duration_s: float = Field(default=0.08, ge=0.0, le=2.0,
                               description="Duración de la transición en segundos")
    beat_aligned: bool = False
    beat_time_s: Optional[float] = None

    # Solo para morph_match / MatchDiffusion
    match_diffusion_source_prompt: Optional[str] = None
    match_diffusion_target_prompt: Optional[str] = None
    match_diffusion_joint_steps: int = 15
    match_diffusion_disjoint_steps: int = 10
    similarity_score: Optional[float] = None

    # Solo para speed_ramp
    speed_curve_bezier: Optional[tuple[float, float, float, float]] = (0.42, 0.0, 0.58, 1.0)
    speed_keyframes: Optional[list[dict]] = None
```

---

---

## 14. Benchmarks de Calidad de Vídeo — VBench / VBench++ / VBench-2.0

### VBench (2024) — 16 dimensiones jerárquicas

VBench evalúa generación de vídeo en **dos ejes**: calidad de vídeo y semántica de vídeo.

| Dimensión | Eje | Qué mide |
|---|---|---|
| subject_consistency | Semántica | Coherencia del sujeto frame a frame |
| background_consistency | Semántica | Estabilidad del fondo |
| temporal_flickering | Calidad | Ausencia de parpadeo inter-frame |
| motion_smoothness | Calidad | Continuidad de movimiento (sin saltos) |
| dynamic_degree | Calidad | Intensidad del movimiento — evitar vídeos estáticos |
| aesthetic_quality | Calidad | Puntuación LAION-Aesthetics |
| imaging_quality | Calidad | Nitidez y ausencia de artefactos CLIP/IQA |
| object_class | Semántica | Generación correcta de clase de objeto |
| multiple_objects | Semántica | Composición de múltiples entidades |
| human_action | Semántica | Fidelidad de acciones humanas |
| color | Semántica | Precisión del color descrito en el prompt |
| spatial_relationship | Semántica | Relaciones espaciales (izquierda/derecha/sobre) |
| scene | Semántica | Reconocimiento de escena/entorno |
| appearance_style | Semántica | Adherencia al estilo visual del prompt |
| temporal_style | Semántica | Consistencia del estilo en el tiempo |
| overall_consistency | Semántica | CLIP-T global entre prompt y vídeo |

### VBench++ — Extensión I2V

VBench++ extiende VBench con dimensiones específicas para Image-to-Video:
- **I2V_subject**: coherencia del sujeto entre el frame de inicio y los frames generados.
- **I2V_background**: estabilidad del fondo con respecto a la imagen de entrada.
- **camera_motion**: calidad del movimiento de cámara (pan, tilt, dolly).

**Implicación para VIDEO_MODEL_ROUTING_V2:** usar las puntuaciones VBench++ de `I2V_subject` como criterio primario al comparar Kling-v2 vs. Wan 2.2 para `human_portrait` y `action_sequence`.

### VBench-2.0 — Faithfulness

VBench-2.0 (NeurIPS 2025) añade el eje de **faithfulness** — fidelidad entre el prompt y el vídeo generado más allá del texto:
- Compositional adherence: ¿el vídeo respeta la composición descrita?
- Negative prompts: ¿se evitan los elementos prohibidos?
- Temporal instruction following: ¿se ejecutan correctamente prompts secuenciales?

---

## 15. Modelos de Difusión de Vídeo 2026

Tabla de referencia actualizada para el routing y la selección de backend.

| Modelo | Params | Licencia | Backend | I2V / T2V | Fortaleza principal |
|---|---|---|---|---|---|
| CogVideoX-5B | 5B | Apache 2.0 | fal.ai / local | I2V + T2V | Open-source, coherencia temporal, backbone de MatchDiffusion |
| HunyuanVideo | 13B | Apache 2.0 | Colab / local | T2V | Movimiento fluido, alta resolución, estado del arte open 2025 |
| Wan 2.2 A14B | 14B (MoE) | Apache 2.0 | fal.ai | I2V + T2V | MoE — calidad de detalles, mejor que HunyuanVideo en VBench++ |
| LTX-Video 2.3 | ~2B | Apache 2.0 | fal.ai / local | T2V | Inferencia rápida, latencia baja — adecuado para previews |
| Mochi 1 | 10B | Apache 2.0 | local | T2V | Movimiento físicamente plausible |
| Runway Gen-4 | — | Propietario | API Runway | T2V + I2V | Mejor control de cámara, consistencia de personaje, motion brush |
| Veo 3 | — | Propietario | API Google | T2V + I2V | Síntesis de audio nativa + vídeo, estado del arte propietario |
| Kling 3.0 | — | Propietario | fal.ai / API | I2V | Coherencia facial multi-frame superior, portraits de alta fidelidad |

### VIDEO_MODEL_ROUTING_V2 — versión 2026

```python
VIDEO_MODEL_ROUTING_V2 = {
    # subject_type → (model_id, backend, modality)
    "human_portrait":    ("kling-3.0",          "fal.ai",  "i2v"),
    "action_sequence":   ("kling-3.0",           "fal.ai",  "i2v"),
    "environment_wide":  ("wan-2.2-a14b",        "fal.ai",  "i2v"),
    "abstract_motion":   ("runway-gen4",         "runway",  "t2v"),
    "product_showcase":  ("hunyuan-video",       "colab",   "t2v"),
    "skyline_timelapse": ("cogvideox-5b",        "fal.ai",  "i2v"),
    "dialogue_scene":    ("veo-3",               "google",  "i2v"),  # audio nativo
    # Fallback universal
    "_default":          ("wan-2.2-a14b",        "fal.ai",  "i2v"),
}
```

**Regla de upgrade:** si `veo-3` no está disponible por cuota → fallback a `kling-3.0` para portrait/dialogue, `wan-2.2-a14b` para resto.

---

## 16. VLMs para Análisis de Vídeo

### Modelos de Embedding: SigLIP 2 / DINOv2 / CLIP

| Modelo | Arquitectura | Fortaleza | Uso en pipeline |
|---|---|---|---|
| CLIP (OpenAI) | ViT + contrastive | Comprensión semántica texto-imagen general | Baseline — supersedido por SigLIP en la mayoría de tareas |
| SigLIP 2 (Google) | Sigmoid loss + ViT | Mejor separabilidad semántica que CLIP; más eficiente | `similarity_check` en bridge para match-cut detection (threshold 0.78) |
| DINOv2 (Meta) | Self-supervised ViT | Excelente para features estructurales / geométricas | Detección de invisible cut points — similitud de composición sin texto |

**Elección canónica:** SigLIP 2 para match-cut detection (threshold 0.78). DINOv2 como complemento para similaridad composicional cuando el sujeto semántico varía pero la geometría es equivalente.

### LLaVA-Video (2025)

- **Arquitectura:** SigLIP (visual encoder) + Qwen2 (LLM) con adaptador de video
- **Entrada:** hasta 64 frames muestreados del clip
- **Fortalezas:** comprensión de acciones, relaciones temporales, descripción de escenas
- **Limitación VBench-CineTechBench:** puntaje ≤ 60% en razonamiento espacial de cámara complejo (ángulo, eje de 180°, continuidad de raccord)
- **Uso en pipeline:** análisis de footage existente en el `asset_manifest`; generación de `visual_anchor` descriptivo para VeoPrompts

```python
# Uso en stage_assets()
from i2v_api.vlm import LLaVAVideoAnalyzer

analyzer = LLaVAVideoAnalyzer(max_frames=64)
for clip_path in asset_manifest.clips:
    description = await analyzer.describe(clip_path)
    # → "medium shot, woman in red coat, push-in motion, warm tungsten light"
    scene.visual_anchor = description
```

### Qwen2.5-VL (2025)

- **Especialidad:** codificación temporal densa — no trata frames como bag-of-images sino como secuencia temporal
- **Absolute Time Encoding:** cada frame recibe un timestamp absoluto; el modelo razona sobre "qué pasa en el segundo 3.2"
- **Fortaleza frente a LLaVA-Video:** mejor en questions temporales de precisión (cuándo empieza una acción, duración de un movimiento)
- **Uso:** cuando el orchestrator necesita localizar beats específicos dentro de un clip de footage para alinearlos con el beat_timing del audio

---

## 17. Detección de Copia y Similitud de Vídeo — VSC2022

### Meta AI Video Similarity Challenge (VSC2022)

Benchmark para detección de vídeos modificados (recortados, acelerados, con filtros) publicado por Meta AI.

**Dos pistas:**
- **Descriptor Track:** embeds cada vídeo en un vector; similitud = distancia coseno.
- **Matching Track:** localiza los segmentos temporales coincidentes entre dos vídeos.

### Temporal Networks

Los modelos ganadores usan **Temporal Networks** — grafos donde los nodos son frames y las aristas codifican transiciones temporales. Superan a los enfoques frame-by-frame porque capturan la secuencia de movimiento, no solo el contenido individual de cada frame.

```python
# Pseudocódigo para copy detection en asset_manifest
def detect_duplicate_clips(clips: list[Path], threshold: float = 0.92) -> list[tuple]:
    """
    Detecta clips duplicados o casi-duplicados usando embeddings temporales.
    threshold=0.92 → alta precisión, evita falsos positivos en escenas similares pero distintas.
    """
    embeddings = []
    for clip in clips:
        frames = sample_frames(clip, n=32)          # muestreo uniforme
        emb = temporal_network.embed(frames)        # Temporal Network → vector 512D
        embeddings.append((clip, emb))
    
    duplicates = []
    for i, (clip_a, emb_a) in enumerate(embeddings):
        for clip_b, emb_b in embeddings[i+1:]:
            sim = cosine_similarity(emb_a, emb_b)
            if sim >= threshold:
                duplicates.append((clip_a, clip_b, sim))
    return duplicates
```

**Uso en pipeline:** antes de generar nuevos clips con I2V, el `asset_manifest` se filtra eliminando duplicados → reduce costos de generación y evita repetición visual en el montaje.

---

## 18. ControlNet para Vídeo / AnimateDiff / Control de Cámara

| Técnica | Qué controla | Input de control | Uso en pipeline |
|---|---|---|---|
| ControlNet (imagen) | Estructura espacial (edges, pose, depth) | Mapa de bordes / esqueleto humano / mapa de profundidad | Anclar composición de frame keyframe |
| AnimateDiff | Movimiento — convierte modelo imagen en modelo vídeo | Motion Module + LoRA de movimiento | Animación consistente desde imagen de referencia |
| SparseCtrl | Control disperso de frames | 1-N frames de referencia (no todos) | Coherencia entre keyframes distantes sin procesar frames intermedios |
| CameraCtrl | Movimiento de cámara parametrizado | Secuencia de poses de cámara (rotación + traslación) | Pan/dolly/tilt determinístico en T2V |
| MotionCtrl (CVPR 2024) | Trayectoria de cámara + objeto | Matrices RT de cámara + trayectoria de objeto | Control preciso para shot con movimiento de personaje + cámara simultáneo |

### Integración en el Director Flow

Cuando el VeoPrompt especifica `camera_physics.primary_motion = "push_in"` y el modelo I2V no soporta control explícito de cámara, el pipeline puede usar CameraCtrl para inyectar la trayectoria:

```python
from bridge.camera_control import CameraCtrlAdapter

if veo_prompt.camera_physics.primary_motion not in model.native_camera_controls:
    adapter = CameraCtrlAdapter(model=model_id)
    camera_traj = adapter.motion_to_trajectory(
        motion=veo_prompt.camera_physics.primary_motion,  # "push_in"
        duration_s=veo_prompt.duration_seconds,
        focal_length_mm=veo_prompt.lens.focal_length_mm,
    )
    clip = await adapter.generate(prompt=veo_prompt, trajectory=camera_traj)
else:
    clip = await model.generate(prompt=veo_prompt)
```

---

## 19. Agentes de Edición — LAVE / ChunkyEdit / Jockey

| Sistema | Tipo | Capacidad | Relevancia |
|---|---|---|---|
| LAVE (Language-driven Video Editing) | Agente LLM | Edición de vídeo dirigida por lenguaje natural — describe el cambio, el agente ejecuta las operaciones de timeline | Modelo de referencia para la interfaz del Edit Director en OpenMontage |
| ChunkyEdit | Agente | Edición por chunks — divide el vídeo en segmentos semánticos y los reordena | Inspiración para el `_split_into_chunks()` en el compositing pipeline |
| Jockey (2025) | Multi-agente | Orquestador de vídeo con sub-agentes especializados: retriever + editor + renderer | Análogo arquitectónico del ghost-agent en i2V: 7-step orchestrator con roles separados |

**Distinción importante:** AutoCut (framework académico, RQ-VAE) ≠ AutoCut (producto comercial de edición de podcasts). El framework académico es el que inspira la arquitectura de tokens unificados de OpenMontage.

---

## 20. Apéndice — Referencias y Repositorios

### Papers clave

| Paper | Año | Aporte |
|---|---|---|
| MatchDiffusion | ICCV 2025 | Match-cuts training-free via joint diffusion |
| Cut2Next | 2025 | Next-shot generation con DiT + CACI + HAM |
| CineVerse | 2025 | Coherent keyframe synthesis para storyboards |
| CineTechBench / ShotBench | NeurIPS 2025 | Benchmark cinematográfico para VLMs |
| VBench | NeurIPS 2024 | 16-dimension video generation quality evaluation |
| VBench++ | 2025 | Extensión I2V + camera motion dimensions |
| VBench-2.0 | NeurIPS 2025 | Faithfulness axis — compositional adherence |
| MotionCtrl | CVPR 2024 | Control de cámara + objeto en T2V |
| VideoAgent (PKU) | ECCV 2024 | Video QA con memoria multimodal aumentada |
| VideoAgent (HKUDS) | 2024 | Edición de vídeo con Dynamic Graph Workflow |
| AutoCut | 2025 | Edición end-to-end con RQ-VAE multimodal |
| VSC2022 | 2022 | Video Similarity Challenge — Temporal Networks |

### Repositorios de referencia

- `THUDM/CogVideoX` — backbone de MatchDiffusion y modelo T2V/I2V open-source
- `Wan-AI/Wan2.2` — Wan 2.2 MoE, estado del arte open I2V
- `huggingface/diffusers` — AnimateDiff, ControlNet, SparseCtrl integrations
- `google-research/siglip` — SigLIP 2 embeddings
- `facebookresearch/DINOv2` — features estructurales para invisible-cut detection
- `librosa/librosa` — beat tracking y análisis de audio
- `JDAI-CV/LLaVA-Video` — VLM para comprensión de vídeo
- `QwenLM/Qwen2.5-VL` — temporal video understanding

---

*Referencia: Cinematografía Algorítmica y Manifiestos JSON · Edición Definitiva Abril 2026*  
*Maintainer: Guion_expert + OpenMontage Cinematic Pipeline Team*
