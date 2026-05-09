# Informe de Handoff — Guion_expert → OpenMontage

**Fecha**: 2026-04-21
**Audiencia**: Dev handoff (ingeniería + agente de OpenMontage)
**Alcance**: Qué archivos entrega Guion_expert, cómo los recibe OpenMontage, y cómo se ejecuta el pipeline hasta producir el MP4 final.

Este documento es complementario a `INFORME_GUION_EXPERT.md` (que cubre la arquitectura interna del repo Guion_expert). Aquí la cámara se corre un paso hacia la derecha: **el contrato del bridge y la lógica de ejecución río abajo**.

---

## Índice

1. Resumen ejecutivo
2. Diagrama del handoff
3. Contrato formal: los 6 archivos que entrega Guion_expert
4. Deep-dive por archivo (brief · script · scene_plan · checkpoint · remotion-cuts · README)
5. La capa traductora: `bridge/openmontage_export.py` paso a paso
6. Layout que el bridge deja en disco dentro de OpenMontage
7. Cómo OpenMontage ingesta y re-arranca el pipeline
8. Ejecución del pipeline (dos modos: agentic vs driver-scripts)
9. El camino zero-key Remotion (render sin API keys)
10. End-to-end real: el reel 3SM que sí se renderizó
11. Mapa de correspondencias Guion_expert → OpenMontage
12. Validación y ciclo de vida (checkpoint.status, human_approval)
13. Gaps conocidos y deuda del contrato
14. Roadmap del handoff (cerrar el loop con `bridge.asset_generator`)
15. Apéndices (comandos, env vars, paths)

---

## 1. Resumen ejecutivo

Guion_expert opera hasta producir **scene_plan con Master Stack v2**. No renderiza video. En lugar de eso, `bridge.openmontage_export.export_project_to_openmontage()` toma el proyecto en español (`output/YYYYMMDD_HHMMSS/`) y lo traduce a **4 artifacts JSON oficiales de OpenMontage** (brief, script, scene_plan, checkpoint) + **remotion-cuts.json** (zero-key preview) + **README.md** humano. Todo queda dentro de `OpenMontage/projects/<timestamp>-<slug>/`.

El `checkpoint.json` es el "token de entrada" para OpenMontage: declara `stage=scene_plan`, `status=completed`, `source=Guion_expert`, `next_stage=assets`. A partir de ese handoff, el Executive Producer de OpenMontage carga `pipeline_defs/cinematic.yaml` y reanuda desde **asset-director** — no vuelve a correr research/proposal/script/scene_plan.

En la práctica (el proyecto 3SM real), la ejecución se hizo con **drivers Python one-off** (`run_asset_director.py`, `train_lora.py`, `run_audio_director.py`, `run_edit_director.py`) que consumieron `scene_plan.json` directamente, disparando FLUX → Kling v3 → MMAudio v2 → moviepy concat, y produjeron `renders/FINAL_3SM_REEL.mp4` (9.4 MB, 1080×1920, h264/aac).

---

## 2. Diagrama del handoff

```
┌─────────────────────── Guion_expert (es-ES) ───────────────────────┐
│                                                                    │
│   output/20260420_034929/                                          │
│     ├── clasificacion/result.txt        (formato, estructura, dur.)│
│     ├── concepto/result.txt             (title, hook, key_points)  │
│     ├── escaleta/result.txt             (beat map)                 │
│     ├── escenas/scene_NN.txt            (prosa de cada escena)     │
│     └── prompts/                        (Veo / SD / Master Stack)  │
│                                                                    │
│   ╔══════════════════════════════════════════════════════════════╗ │
│   ║  bridge/openmontage_export.py                                ║ │
│   ║   • parse clasificación → formato canónico                   ║ │
│   ║   • extract concept → title/hook/key_points                  ║ │
│   ║   • enumerate scenes → normaliza Veo/Master Stack            ║ │
│   ║   • allocate timestamps (duración proporcional)              ║ │
│   ║   • select style playbook + pipeline                         ║ │
│   ║   • build brief/script/scene_plan/checkpoint/cuts            ║ │
│   ║   • validate contra JSON Schemas de OpenMontage              ║ │
│   ║   • write atomically + copy to remotion demo-props           ║ │
│   ╚══════════════════════════════════════════════════════════════╝ │
└──────────────────────────────────┬─────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────── OpenMontage (en-US) ────────────────────────┐
│                                                                    │
│   projects/20260420_034929-reel-de-instagram-sobre-banda-…/        │
│     ├── stages/                                                    │
│     │   ├── brief.json            ✅ v1.0 válido                    │
│     │   ├── script.json           ✅ v1.0 válido                    │
│     │   ├── scene_plan.json       ✅ v1.0 + master_stack v2        │
│     │   └── checkpoint.json       ✅ stage=scene_plan, status=done │
│     ├── remotion-cuts.json        (zero-key rough cuts)            │
│     └── README.md                                                  │
│                                                                    │
│   remotion-composer/public/demo-props/<slug>.json  ← mirror       │
│                                                                    │
│   ╔══════════════════════════════════════════════════════════════╗ │
│   ║  Executive Producer (cinematic.yaml) resumes from: assets    ║ │
│   ║                                                              ║ │
│   ║   assets  → asset-director    (FLUX + I2V + music + SFX)     ║ │
│   ║   edit    → edit-director     (timeline, ducking)            ║ │
│   ║   compose → compose-director  (ffmpeg/Remotion render)       ║ │
│   ║   publish → publish-director  (SEO, export packaging)        ║ │
│   ╚══════════════════════════════════════════════════════════════╝ │
│                                                                    │
│                              ▼                                     │
│                       renders/FINAL.mp4                            │
└────────────────────────────────────────────────────────────────────┘
```

El bridge es 100 % Python determinista — no hay LLM en esta capa.

---

## 3. Contrato formal: los 6 archivos que entrega Guion_expert

Ubicación absoluta (respecto a `OpenMontage/`):

```
projects/<timestamp>-<slug>/
├── stages/
│   ├── brief.json              # Creative brief (esquema brief.schema.json)
│   ├── script.json             # Beat map + secciones (script.schema.json)
│   ├── scene_plan.json         # Plan de escenas + master_stack (scene_plan.schema.json)
│   └── checkpoint.json         # Estado del pipeline (checkpoint.schema.json)
├── remotion-cuts.json          # Rough cuts listos para render zero-key
└── README.md                   # Guía humana (cómo continuar, paths, comandos)
```

Y un mirror:

```
remotion-composer/public/demo-props/<slug>.json
```

(copia del `remotion-cuts.json` para que `python render_demo.py <slug>` lo levante sin configuración).

### Versionado

- Los 4 artifacts de `stages/` declaran `"version": "1.0"` y validan contra los JSON Schemas en `OpenMontage/schemas/artifacts/*.schema.json`.
- El bloque `master_stack` dentro de cada escena usa **v2** (Master Stack 2026, Pydantic del repo Guion_expert) — el schema upstream lo permite con `additionalProperties: true` para no acoplar versiones.

### Source of truth

El `checkpoint.json.metadata.source` vale siempre `"Guion_expert"` cuando el bridge emite el handoff, y `next_stage = "assets"` (puerta de entrada al agente de OpenMontage).

---

## 4. Deep-dive por archivo

### 4.1 `stages/brief.json` — Creative brief (24 líneas)

Traduce la **clasificación + concepto** de Guion_expert al esquema oficial `brief.schema.json`:

```jsonc
{
  "version": "1.0",
  "title": "reel de instagram sobre banda cover 3SM, una historia intrig",
  "hook": "# 🎬 REEL INSTAGRAM — 3SM \"LA VERDAD DETRÁS DEL TELÓN\"",
  "key_points": [
    "Formato: Reel Instagram (15-60 seg)",
    "Estructura: Simple con Giro/Revelación",
    "Plataforma: Instagram Reels",
    "Objetivo: Engagement + Intriga + Identidad de Marca",
    "Público: Fans de rock vintage, cabaret, bandas cover cult"
  ],
  "core_message": "...",
  "tone": "cinematográfico",
  "style": "flat-motion-graphics",              // playbook name
  "target_audience": "general",
  "target_platform": "generic",                  // mapeado de REEL_INSTAGRAM
  "target_duration_seconds": 60.0,
  "metadata": {
    "source": "Guion_expert",
    "formato_original": "REEL_INSTAGRAM",
    "estructura_narrativa": "SIMPLE (CON GIRO/REVELACIÓN)",
    "idea_original": "reel de instagram sobre banda cover 3SM, una historia intrigante",
    "generated_at": "2026-04-20T07:56:24Z"
  }
}
```

Campos que el bridge infiere y no salen directo de Guion_expert:

- `target_platform` ← `FORMATO_A_PLATAFORMA[formato]` (REEL_INSTAGRAM → "instagram", etc.)
- `target_duration_seconds` ← clasificación > brief_hint > tabla `FORMATO_A_DURACION_SEG`
- `style` ← heurística `_select_playbook(formato, estilo_visual, available_playbooks)`
- `tone` ← detectado de concepto o default por formato

### 4.2 `stages/script.json` — Beat map con secciones (58 líneas)

Lista ordenada de `sections[]` derivada de la escaleta. Cada sección tiene:

```jsonc
{
  "id": "sec-001",
  "heading": "Acto I — El bajista afina",
  "intent": "establish",
  "start_seconds": 0.0,
  "end_seconds": 9.14,
  "beats": ["Bajista afina", "Se quita Ray-Ban", "Se levanta"],
  "dialogue": "",      // opcional
  "notes": ""          // opcional
}
```

Los timestamps se **asignan proporcionalmente** por `_allocate_timestamps()` a partir del peso narrativo de cada escena (función determinista, no LLM).

### 4.3 `stages/scene_plan.json` — **El archivo estrella** (673 líneas para 6 escenas)

Estructura del schema oficial (`scene_plan.schema.json`):

```jsonc
{
  "version": "1.0",
  "style_playbook": "flat-motion-graphics",
  "scenes": [ /* 1..N escenas */ ]
}
```

Cada escena cumple el contrato upstream:

| Campo | Tipo | Origen |
|---|---|---|
| `id` | `"scene-NNN"` | Enumeración determinista |
| `type` | enum OpenMontage: `generated` / `broll` / `text_card` / ... | Por default `generated` |
| `description` | string | Prosa de la escena (escaleta) |
| `start_seconds` / `end_seconds` | number | `_allocate_timestamps` |
| `script_section_id` | string | Match con sections del script |
| `narrative_role` | enum (establish_context / build_tension / deliver_payload / ...) | `_narrative_role(i, total, estructura)` |
| `hero_moment` | bool | `i == _hero_moment_index(n)` (climax detectado) |
| `shot_language` | object | `_shot_language_from_veo(veo, header, body)` — vocabulario enum de OM |
| `texture_keywords` | array | `_extract_textures(text)` |
| `required_assets[]` | array | Un `image` (generator_hint=flux-1.1-pro) + un `video` (hint=kling/runway/wan) |

**Lo que Guion_expert agrega y el schema upstream NO exige** — el bloque `master_stack`:

```jsonc
"master_stack": {
  "chosen_video_model": "kling-2.5-pro",       // routing determinista por subject_type
  "subject_type": "human_performance",          // Literal enum del schema Pydantic v2
  "narrative_beat": "setup",
  "source_scene_id": "scene-001",

  "visual_anchor": {                            // → FLUX.1 Pro (frame 0)
    "composition": "...",
    "palette": ["warm amber key light", ...],
    "lighting": "Golden hour lateral 45° ...",
    "textures": [...],                          // lista de materiales/detalles
    "style": "cinematic_35mm_kodak",
    "subject_description": "Bajista veterano de 62 años ...",
    "environment": "Camerino trasero bohemio ...",
    "flux_prompt": "<síntesis determinista>"    // _synthesize_flux_prompt()
  },
  "camera": {                                   // física del plano
    "shot_type": "medium_close",
    "movement": "subtle_slow_camera",
    "lens_mm": 85,
    "duration_seconds": 8.0
  },
  "motion_intent": {                            // → I2V prompt (Kling/Runway/WAN)
    "action": "El bajista toca notas individuales ...",
    "motion_intensity": "low",                  // low | medium | high
    "physics_notes": "Movimientos lentos, ..."
  },
  "sonic": {                                    // → Suno + MMAudio
    "mood": ["ritual sagrado", "precisión melancólica", ...],
    "music_brief": "Bajo solo minimalista en Mi menor, 55 BPM ...",
    "music_reference_artists": ["Jóhann Jóhannsson", "Max Richter"],
    "sfx": ["Crujido de silla", "Chasquido de clavijas", ...],
    "diegetic_sound": "El bajo que afina es sonido del mundo ...",
    "silence_moments": ["2s de silencio después del acorde ..."]
  },
  "post_production": {                          // → Real-ESRGAN opcional
    "target_fps": null,
    "target_resolution": null,
    "upscale_with": null,
    "fps_interpolation": null
  },
  "text_on_screen": "",
  "director_notes": "Esta es la escena de apertura. El bajista es el corazón ..."
}
```

**Por qué el upstream lo acepta**: el schema declara `master_stack` como `{"type": "object", "additionalProperties": true}`. El bridge lo deja pasar tal cual — _no_ lo normaliza al vocabulario OM. El contrato es: "OpenMontage puede o no mirar master_stack; si lo mira, está ahí en forma pura".

El `asset-director` cinematic **debe** consumir `master_stack` para cada escena en vez de regenerar prompts propios (ver § 7).

### 4.4 `stages/checkpoint.json` — El token de resumption (21 líneas)

```jsonc
{
  "version": "1.0",
  "project_id": "20260420_034929-reel-de-instagram-sobre-banda-cover-3sm-una-historia-intrig",
  "pipeline_type": "cinematic",
  "stage": "scene_plan",               // último stage completado
  "status": "completed",
  "timestamp": "2026-04-20T07:56:24Z",
  "style_playbook": "flat-motion-graphics",
  "checkpoint_policy": "guided",
  "human_approval_required": true,
  "human_approved": true,              // el bridge asume aprobación humana off-line
  "artifacts": {
    "brief": "stages/brief.json",
    "script": "stages/script.json",
    "scene_plan": "stages/scene_plan.json"
  },
  "metadata": {
    "source": "Guion_expert",
    "next_stage": "assets",            // ← CLAVE para el EP de OpenMontage
    "note": "Brief, script y scene_plan producidos por Guion_expert. El agente de OpenMontage debe iniciar desde la etapa `assets`."
  }
}
```

Tres cosas que debe leer el EP de OpenMontage:

1. `pipeline_type: cinematic` → carga `pipeline_defs/cinematic.yaml` (266 líneas, 7 stages + sub-stages).
2. `stage + status` → valida dónde quedó la tarea anterior.
3. `metadata.next_stage: assets` → salta research/proposal/script/scene_plan y arranca en `assets`.

### 4.5 `remotion-cuts.json` — Camino zero-key

Formato pensado para el renderizador Remotion (JS) sin depender de APIs pagas:

```jsonc
{
  "theme": "flat-motion-graphics",
  "cuts": [
    { "id": "hero",      "type": "hero_title", "in_seconds": 0,    "out_seconds": 3.5,  "text": "...", "subtitle": "..." },
    { "id": "scene-001", "type": "text_card",  "in_seconds": 3.5,  "out_seconds": 12.11, "text": "...", "backgroundColor": "#0F172A" },
    ...
  ]
}
```

Se consume desde `OpenMontage/render_demo.py`:

```bash
cd OpenMontage
python render_demo.py <slug>   # ejecuta `npx remotion render` contra el cuts.json
```

### 4.6 `README.md` — Onboarding humano

Narra en texto cómo retomar el proyecto, con secciones típicas:

```
# <Title>
- idea original
- pipeline recomendada: cinematic
- playbook: flat-motion-graphics
- duración: 60.0s
- # escenas: 6

## Cómo continuar
- Opción A (agente): spawnea el EP cinematic sobre este project_id.
- Opción B (zero-key preview): `python render_demo.py <slug>`.
- Opción C (drivers Python): ver `run_asset_director.py`, etc.

## Validation warnings
- <si alguna apareció durante el export>
```

---

## 5. La capa traductora: `bridge/openmontage_export.py` paso a paso

Función entry-point: `export_project_to_openmontage(project_dir, openmontage_root, idea, brief_hint)` en la línea 1439 del archivo. 12 pasos, todos deterministas:

```
 1. Parse clasificación           → _parse_classification_file()   # formato, estructura, duración
 2. Concept → title/hook/points   → _extract_title_hook()
 3. Resolve duración              → brief_hint > clasif > FORMATO_A_DURACION_SEG
 4. Enumerate + timestamp escenas → _enumerate_scenes() + _allocate_timestamps()
 5. Select style playbook         → _select_playbook(formato, estilo_visual, available)
 6. Resolve pipeline              → FORMATO_A_PIPELINE[formato]  (REEL → cinematic)
 7. Build artifacts               → _build_brief / _build_script / _build_scene_plan / _build_remotion_cuts
 8. Compute paths (project_id)    → "<timestamp>-<slug>"
 9. Validate contra schemas       → jsonschema.validate() con warnings no-fatales
10. Write artifacts a disco       → json.dumps(indent=2, ensure_ascii=False)
11. Copy cuts a demo-props        → _copy_cuts_to_demo_props()
12. Render README                 → _render_project_readme()
```

Puntos no triviales:

### 5.1 Normalización Veo → Master Stack

El prompt `11_director_flow.txt` (Guion_expert) produce **dos variantes** de Veo: flat (`{plano, movimiento, iluminacion}`) y nested spec completo con `parametros_globales` y `secuencia_planos`. `_normalize_veo()` (línea 555) y `_normalize_master_stack()` (línea 736) absorben ambos formatos y devuelven el bloque estable que se inyecta en `scene_plan.scenes[].master_stack`.

### 5.2 Síntesis del `flux_prompt`

`_synthesize_flux_prompt(visual, motion)` concatena determinísticamente (sin LLM) `subject + environment + composition + palette + lighting + textures + style + subject_action_at_frame_0`. Es el string que `asset-director` debe mandar **tal cual** a FLUX.1 Pro — no hay que re-prompt-engineering río abajo.

### 5.3 Selección de style playbook

`_discover_playbooks(openmontage_root)` lista `styles/*.yaml` y `_select_playbook()` matchea por:

1. `estilo_visual` textual (heurística keyword → playbook).
2. Fallback por `formato`: REEL/SHORT → `flat-motion-graphics`, CORTO → `clean-professional`, largo/docu → `minimalist-diagram`.

### 5.4 Validación

Cada artifact se valida contra su `.schema.json` pero los errores se registran como **warnings** no-fatales (`print("[bridge] WARN: ...")`). El bridge emite el handoff igual — OpenMontage decide si aborta o arregla in-place.

### 5.5 Atomicidad

Los writes NO son atómicos tradicionales (tmp + rename). Pero como todo el export es idempotente y el directorio destino es único por `project_id`, reescribir no destruye estado previo fuera de sus propios archivos.

---

## 6. Layout que el bridge deja en disco

Árbol minimalista (inmediatamente tras el export, antes de que OpenMontage toque nada):

```
OpenMontage/
├── projects/
│   └── 20260420_034929-reel-de-instagram-sobre-banda-cover-3sm-una-historia-intrig/
│       ├── stages/
│       │   ├── brief.json           (1.3 KB, v1.0)
│       │   ├── script.json          (~2 KB)
│       │   ├── scene_plan.json      (~40 KB, 6 scenes x master_stack)
│       │   └── checkpoint.json      (0.9 KB)
│       ├── remotion-cuts.json       (~2 KB)
│       └── README.md
└── remotion-composer/
    └── public/
        └── demo-props/
            └── reel-de-instagram-sobre-banda-cover-3sm-una-historia-intrig.json  ← mirror
```

Después de la ejecución (lo que hoy existe en el filesystem para el reel 3SM) se suman:

```
        ├── assets/                  ← creado por asset-director/drivers
        │   ├── scene-001-flux.jpg
        │   ├── scene-001-flux-lora.jpg
        │   ├── scene-001-video.mp4
        │   ├── scene-001-video-lora.mp4
        │   ├── scene-001-foley.mp3
        │   ├── ... (6 escenas × 5 artifacts cada una)
        │   └── mylist.txt          ← concat list de moviepy/ffmpeg
        ├── renders/
        │   └── FINAL_3SM_REEL.mp4  (9.4 MB, 1080x1920, h264/aac)
        ├── stages/
        │   ├── lora_models.json    ← output de train_lora.py
        │   └── asset_plan.json     ← output de run_asset_director.py
        ├── run_asset_director.py       ← drivers Python ad-hoc
        ├── run_asset_director_lora.py
        ├── run_audio_director.py
        ├── run_edit_director.py
        ├── train_lora.py
        └── AGENT_PROMPT.md         ← prompt listo para el EP de OpenMontage
```

---

## 7. Cómo OpenMontage ingesta y re-arranca el pipeline

El componente clave es `OpenMontage/lib/checkpoint.py`. Fragmentos relevantes:

```python
CANONICAL_STAGE_ARTIFACTS = {
    "research":   "research_brief",
    "proposal":   "proposal_packet",
    "idea":       "brief",
    "script":     "script",
    "scene_plan": "scene_plan",
    "assets":     "asset_manifest",
    "edit":       "edit_decisions",
    "compose":    "render_report",
    "publish":    "publish_log",
}

def get_pipeline_stages(pipeline_type):
    manifest = load_pipeline(pipeline_type)     # lee pipeline_defs/<type>.yaml
    return get_stage_order(manifest)             # orden declarado en el YAML
```

Flujo de arranque del Executive Producer (EP) de OpenMontage cuando entra al `project_id`:

```
1. Descubre el proyecto: projects/<id>/stages/checkpoint.json existe
2. Lee checkpoint.pipeline_type → "cinematic"
3. Carga pipeline_defs/cinematic.yaml  (lib/pipeline_loader.py)
4. Lee checkpoint.stage + status     → "scene_plan" + "completed"
5. Lee checkpoint.metadata.next_stage → "assets"
6. Avanza el puntero al siguiente stage de cinematic.yaml: assets
7. Skipea research / proposal / script / scene_plan — sus artifacts ya están y ya validaron
8. Inicializa EP_STATE (ver § 7.1) y spawnea el director correspondiente
```

### 7.1 EP_STATE que carga el agente

Del skill `skills/pipelines/cinematic/executive-producer.md`:

```yaml
EP_STATE:
  pipeline: cinematic
  playbook: flat-motion-graphics
  target_duration_seconds: 60.0
  budget_total_usd: 10.00           # de config.yaml global
  budget_spent_usd: 0.0
  emotional_arc: null               # se deriva del proposal_packet; aquí es null
  delivery_promise:
    motion_required: true           # inferido porque required_assets incluyen type=video
    tone_mode: cinematic
  renderer_family: kling-2.5-pro    # inferido del master_stack.chosen_video_model
  artifacts:
    brief:        stages/brief.json
    script:       stages/script.json
    scene_plan:   stages/scene_plan.json
    asset_manifest: null            # ← a producir por asset-director
```

### 7.2 Validación en el arranque

`checkpoint.py::_validate_artifacts_for_stage()` corre jsonschema sobre los 3 artifacts declarados en `checkpoint.artifacts` contra los schemas de `OpenMontage/schemas/artifacts/`. Si la validación falla, el EP aborta con `CheckpointValidationError` y no avanza al siguiente stage.

Como el bridge ya validó al emitir (§ 5.4), esta segunda validación debería pasar siempre; sirve de red de seguridad ante ediciones manuales del JSON.

---

## 8. Ejecución del pipeline (dos modos)

### Modo A — Agentic (diseño oficial, `cinematic.yaml`)

Secuencia declarada en `pipeline_defs/cinematic.yaml`:

| Stage | Skill | Required in | Produces | Tools |
|---|---|---|---|---|
| research | research-director | — | research_brief | web_search |
| proposal | proposal-director | research_brief | proposal_packet, decision_log | — |
| script | script-director | proposal_packet | script | transcriber, scene_detect |
| **scene_plan** | scene-director | script | scene_plan | frame_sampler |
| **assets** | asset-director | scene_plan | **asset_manifest** | subtitle_gen, audio_enhance, image_selector, video_selector, music_gen |
| edit | edit-director | scene_plan + asset_manifest | edit_decisions | — |
| compose | compose-director | edit_decisions + asset_manifest | render_report, final_review | video_compose, audio_mixer, video_stitch, video_trimmer, color_grade |
| publish | publish-director | render_report + final_review | publish_log | — |

Para el handoff de Guion_expert: los 4 primeros se marcan como "done" vía checkpoint y el EP arranca en **assets**.

Flujo por stage:

```
PREPARE         → carga inputs + playbook + skill Markdown
SPAWN DIRECTOR  → subagente con el skill montado
REVIEW          → meta/reviewer valida contra success_criteria + review_focus
GATE DECISION   → pass (next) / revise (re-run max 3×) / send-back (to prior stage, max 3×)
CHECKPOINT      → escribe stages/<stage_artifact>.json + actualiza checkpoint.json
```

**Gap real**: los skills `asset-director.md` del pipeline cinematic todavía **no están actualizados para consumir el bloque `master_stack` v2** emitido por Guion_expert. Hoy el director cinematic hablaría de "image_selector"/"video_selector" agnósticos y recrearía prompts desde el scene_plan. Ver deuda § 13.

### Modo B — Drivers Python one-off (lo que SÍ produjo el MP4)

Para el reel 3SM real, Leo (o un ejecutor humano) corrió **5 scripts Python planos** que consumieron `scene_plan.json` directamente. No pasó por el EP. Orden cronológico (por mtime):

```
04:27  run_asset_director.py        ← FLUX 1.1 Pro + Kling 3.0 (6 escenas en ThreadPool)
04:33  train_lora.py                ← fal-ai/flux-lora-fast-training, trigger 3SM_BAND
04:44  run_asset_director_lora.py   ← re-genera imágenes con LoRA aplicado
05:18  run_audio_director.py        ← fal-ai/mmaudio-v2 (foley diegético por escena)
05:21  run_edit_director.py         ← moviepy concat + libx264/aac @ 1080x1920
05:22  renders/FINAL_3SM_REEL.mp4   ← 9.4 MB
```

Ejemplo del corazón de `run_asset_director.py` (línea 45):

```python
flux_res = flux.execute({
    "prompt": visual_anchor["flux_prompt"],       # del master_stack
    "model": "flux-pro/v1.1",
    "width": 1080,
    "height": 1920,
    "output_path": img_path
})
...
kling_res = kling.execute({
    "operation": "image_to_video",
    "prompt": motion_intent["action"],            # del master_stack
    "model_variant": "v3/standard",
    "duration": str(int(master_stack["camera"]["duration_seconds"])),  # del master_stack
    "aspect_ratio": "9:16",
    "image_url": data_uri,                        # FLUX output → base64 data URI
    "output_path": vid_path
})
```

`run_audio_director.py` (línea 42):

```python
res = fal_client.subscribe(
    "fal-ai/mmaudio-v2",
    arguments={
        "video_url": vid_url,
        "prompt": sound_intent,                   # master_stack.sonic.diegetic_sound
        "duration": 5.0
    }
)
```

`run_edit_director.py` (línea 20):

```python
for scene in scene_plan["scenes"]:
    scene_id = scene["id"]
    duration = float(scene["master_stack"]["camera"]["duration_seconds"])
    vid_path = f"{ASSETS_DIR}/{scene_id}-video-lora.mp4"
    audio_path = f"{ASSETS_DIR}/{scene_id}-foley.mp3"
    vid_clip = VideoFileClip(vid_path).with_audio(AudioFileClip(audio_path))
    clips.append(vid_clip)

final_clip = concatenate_videoclips(clips, method="compose")
final_clip.write_videofile(OUTPUT_PATH, codec="libx264", audio_codec="aac", fps=24)
```

Lo relevante: **todos los drivers leen del mismo `scene_plan.json` que emitió el bridge**. El contrato se mantiene; lo que cambia es quién lo orquesta.

### 8.1 ¿Por qué drivers Python y no EP agentic?

- **Velocidad**: para validar end-to-end, un script con `ThreadPoolExecutor(max_workers=6)` es más rápido y debuggable que orquestación agentic + quality gates.
- **LoRA**: el flujo LoRA (train una vez, aplicar a todas las escenas) no estaba previsto en el skill `asset-director.md` vanilla — se implementó artesanal.
- **`bridge.asset_generator`**: el orquestador production-grade (commit 11 de Guion_expert) todavía no se había cableado al proyecto 3SM. La próxima generación reemplazará estos scripts (ver § 14).

---

## 9. El camino zero-key Remotion (render sin API keys)

Paralelo al pipeline de generación, el bridge siempre emite `remotion-cuts.json` + mirror en `demo-props/`. Para ver un preview sin pagar un centavo:

```bash
cd OpenMontage
python render_demo.py <slug>
```

`render_demo.py` (133 líneas):

1. Verifica que Node y npm están en PATH.
2. `npm install` dentro de `remotion-composer/` si falta `node_modules/`.
3. Valida el props file (`cuts[]` no vacío).
4. `npx remotion render src/index.tsx Explainer <output>.mp4 --props <demo-props>.json --codec h264`.
5. Output a `projects/demos/renders/<slug>.mp4`.

Usa los cuts como **text_card** overlays con fondo sólido — no renderiza video generativo, solo tarjetas animadas con Remotion. Sirve como:

- **Rough cut instantáneo** para validar pacing y beats antes de gastar en FLUX/Kling.
- **Fallback** cuando no hay keys de fal.ai.
- **Referencia visual** para el director humano.

---

## 10. End-to-end real: el reel 3SM que sí se renderizó

Proyecto: `20260420_034929-reel-de-instagram-sobre-banda-cover-3sm-una-historia-intrig`

### Numeros reales

- **Escenas**: 6 (IDs scene-001 .. scene-006)
- **Duración total**: 52s (scene_plan suma esto; target brief dice 60s)
- **Hero moment**: scene-004
- **Playbook**: `flat-motion-graphics`
- **Pipeline**: `cinematic`

### Assets producidos (en `assets/`)

Por escena se generaron 5 variantes:

| Sufijo | Descripción | Herramienta | Fase |
|---|---|---|---|
| `-flux.jpg` | Frame 0 FLUX 1.1 Pro (baseline, sin LoRA) | `tools.graphics.flux_image` | FLUX |
| `-flux-lora.jpg` | Frame 0 FLUX + LoRA `3SM_BAND` | fal-ai/flux-lora | FLUX (con caracter consistency) |
| `-video.mp4` | I2V Kling 3.0 standard @ 9:16 desde `-flux.jpg` | `tools.video.kling_video` | I2V |
| `-video-lora.mp4` | I2V Kling desde `-flux-lora.jpg` | idem | I2V (final usado en edit) |
| `-foley.mp3` | Foley diegético MMAudio v2 | fal-ai/mmaudio-v2 | SFX |

LoRA training (`train_lora.py`):

```python
fal_client.subscribe("fal-ai/flux-lora-fast-training", arguments={
    "images_data_url": "...3SM_dataset.zip",
    "trigger_word": "3SM_BAND",
    "steps": 1000
})
```

Output en `stages/lora_models.json`:

```json
{
  "3sm_band": {
    "url": "https://v3b.fal.media/files/b/0a96fd5d/3S5NlHZcGMqoAg0_zRamU_pytorch_lora_weights.safetensors",
    "trigger": "3SM_BAND"
  }
}
```

### Costo total

Per `stages/asset_plan.json`:

```json
{
  "budget": 3.00,
  "total_cost": 0.6,
  "scenes": {
    "scene-001": { "flux_image": "...", "kling_video": "...", "cost": 0.1 },
    "scene-002": { ..., "cost": 0.1 },
    ...
    "scene-006": { ..., "cost": 0.1 }
  }
}
```

6 escenas × $0.10 = **$0.60** en FLUX + Kling. Más ~$0.12 en MMAudio (6 × $0.02) + ~$0.25 en LoRA training = **~$0.97 total** para el render completo.

### Render final

```
renders/FINAL_3SM_REEL.mp4
  codec:  h264 (libx264)
  audio:  aac
  fps:    24
  size:   1080 x 1920 (9:16)
  weight: 9,390,956 bytes (9.4 MB)
  mtime:  2026-04-20 05:22
```

---

## 11. Mapa de correspondencias Guion_expert → OpenMontage

Referencia rápida para el director/EP que lee `scene_plan.json`:

| Master Stack v2 (Guion_expert)              | Consumidor OpenMontage                      | Herramienta                     |
|---------------------------------------------|---------------------------------------------|---------------------------------|
| `visual_anchor.flux_prompt`                 | asset-director · FLUX                       | `image_selector` / `flux_image` |
| `visual_anchor.subject_description`         | LoRA trigger contextual                     | `flux-lora-fast-training`       |
| `camera.duration_seconds`                   | asset-director · I2V param `duration`       | `video_selector` / `kling_video`|
| `camera.shot_type`, `movement`, `lens_mm`   | edit-director · composition guidance        | (ninguna — informativo)         |
| `motion_intent.action`                      | asset-director · I2V prompt                 | `kling_video` / `runway_video`  |
| `motion_intent.motion_intensity`            | routing kling / runway / wan                | `chosen_video_model`            |
| `chosen_video_model`                        | override del router (wins sobre intensity)  | asset-director                  |
| `sonic.music_brief` + `music_reference_artists` | asset-director · hero music track       | `music_gen` (Suno)              |
| `sonic.sfx` + `sonic.diegetic_sound`        | asset-director · foley por escena           | fal-ai/mmaudio-v2               |
| `sonic.silence_moments`                     | edit-director · audio ducking timing        | `audio_mixer`                   |
| `post_production.upscale_with`              | compose-director · upscale final            | Real-ESRGAN                     |
| `post_production.target_fps` / `_resolution`| compose-director · render params            | ffmpeg                          |
| `text_on_screen`                            | edit-director · overlay                     | Remotion / ffmpeg               |
| `director_notes`                            | EP + reviewer · contexto narrativo          | (humano/LLM)                    |

Campos top-level de escena que siguen el vocab canónico OM:

| scene_plan.json                             | OpenMontage schema validation               |
|---------------------------------------------|---------------------------------------------|
| `id`, `type`, `description`                 | required                                    |
| `start_seconds`, `end_seconds`              | required, minimum: 0                        |
| `shot_language.*` (enums)                   | validated contra enums del schema           |
| `narrative_role`                            | enum: establish_context / build_tension / ... |
| `hero_moment`                               | boolean                                     |
| `texture_keywords[]`                        | array of strings                            |
| `required_assets[]`                         | array con `{type, description, source, generator_hint}` |

---

## 12. Validación y ciclo de vida

### 12.1 Schemas que validan el handoff

En `OpenMontage/schemas/artifacts/`:

| Schema | Líneas | Valida |
|---|---|---|
| `brief.schema.json` | 49 | version, title, hook, key_points, tone, style, target_platform (enum), target_duration_seconds ≥ 1 |
| `script.schema.json` | — | sections[] con start/end seconds, intents |
| `scene_plan.schema.json` | 102 | scenes[] con id, type (enum), description, start/end seconds, shot_language, narrative_role (enum), master_stack (additionalProperties: true) |
| `checkpoint.schema.json` | — | project_id, pipeline_type, stage, status, artifacts, human_approval_required |

Todos usan Draft 2020-12.

### 12.2 Estados del checkpoint

Del schema:

| Campo | Valores |
|---|---|
| `stage` | `research` \| `proposal` \| `idea` \| `script` \| `scene_plan` \| `assets` \| `edit` \| `compose` \| `publish` |
| `status` | `in_progress` \| `completed` \| `needs_revision` \| `sent_back` \| `failed` |
| `human_approval_required` | bool (default true para stages creativos) |
| `human_approved` | bool (el EP bloquea hasta que sea true si required=true) |

El bridge siempre escribe `status=completed`, `human_approved=true` porque el proyecto ya fue revisado off-line en Guion_expert antes de exportar.

### 12.3 Checkpoint policies

Del `config.yaml` de OpenMontage (línea 18):

```yaml
checkpoint:
  policy: guided          # guided | manual_all | auto_noncreative
```

- `guided`: el EP pausa sólo en stages creativos (proposal, script, scene_plan, publish).
- `manual_all`: pausa en cada stage.
- `auto_noncreative`: pasa todo lo no-creativo sin preguntar.

Como el handoff Guion_expert ya quemó los stages creativos hasta scene_plan, `guided` en la práctica solo pausa en `publish` al final.

---

## 13. Gaps conocidos y deuda del contrato

### 13.1 Rutas macOS hardcodeadas en los drivers

`run_asset_director.py`, `run_edit_director.py`, etc. tienen:

```python
os.chdir("/Users/mac/Desktop/ESCRIBE/OpenMontage/OpenMontage")
sys.path.append("/Users/mac/Desktop/ESCRIBE/OpenMontage/OpenMontage")
```

No corren en otra máquina. Son scripts exploratorios, no infra.

### 13.2 `asset_plan.json` vs `asset_manifest.json` — nombres divergentes

El driver `run_asset_director.py` escribe `stages/asset_plan.json` con estructura propia:

```json
{ "scenes": { "scene-001": { "flux_image": "...", "kling_video": "...", "cost": 0.1 } } }
```

Pero el schema oficial `asset_manifest.schema.json` exige:

```json
{ "version": "1.0", "assets": [ { "id": "...", "type": "image", "path": "...", "scene_id": "...", "source_tool": "..." } ] }
```

El EP agentic no podría continuar desde el estado actual del proyecto 3SM — necesitaría un normalizador o volver a correr el stage `assets` con el asset-director oficial (o con `bridge.asset_generator` que sí emite schema-válido).

### 13.3 Skill `asset-director.md` cinematic no conoce `master_stack` v2

El markdown actual del skill habla de `image_selector`/`video_selector` genéricos y recrea prompts. No pattern-matchea `scene.master_stack.visual_anchor.flux_prompt` para pasarlo tal cual. Hay que **actualizar el skill** para respetar el contrato Guion_expert.

### 13.4 Duración desalineada (52s real vs 60s brief)

El brief declara `target_duration_seconds: 60.0` pero el scene_plan suma 52s. El edit-director tendría que decidir si estira (no disponible en I2V) o rellena con hero_title adicional. Hoy lo resuelve el driver humano.

### 13.5 No hay rotación de proyectos ni lockfile

Si dos procesos corren `export_project_to_openmontage()` sobre el mismo project_id, sobreescriben. No hay lockfile ni detección de concurrencia.

### 13.6 `remotion-cuts.json` es solo text cards

No integra los videos generados. Es un camino paralelo (rough cut) más que una alternativa de render con los assets reales.

### 13.7 Validación warnings-only

Si `brief.json` no valida, el bridge imprime `WARN` pero sigue escribiendo. Idealmente el caller debería poder elevar a error con un flag `strict=True`.

---

## 14. Roadmap del handoff

### Corto plazo — cerrar el loop con `bridge.asset_generator`

El commit 11 (Guion_expert) ya entrega `bridge/asset_generator.py` que produce un `asset_manifest` schema-válido y maneja:

- FLUX 1.1 Pro por escena (con/sin LoRA)
- Routing determinista I2V (kling / runway / wan) vía `VIDEO_MODEL_ROUTING[subject_type]`
- MMAudio v2 por escena
- Suno (música hero) en paralelo vía docker-compose side-car
- Real-ESRGAN opcional si `post_production.upscale_with` está seteado
- Budget tracker con lock + reservas pre-submit
- Atomic write (`.tmp` → `os.replace`)
- CLI: `python -m bridge.asset_generator <scene_plan.json> --budget 3.00 --concurrency 2`

**Acción**: ejecutar `asset_generator` sobre el `scene_plan.json` del proyecto 3SM y comparar su output con el `asset_plan.json` actual. Verificar schema compliance.

### Medio plazo — cableo agentic oficial

1. Actualizar `skills/pipelines/cinematic/asset-director.md` para consumir `master_stack` v2 (prompts pre-sintetizados).
2. Asegurar que `asset-director` oficial llama a `bridge.asset_generator` vía subproceso o import.
3. Extender `edit-director.md` para respetar `sonic.silence_moments` y `director_notes`.
4. Extender `compose-director.md` para honrar `post_production.target_fps`/`_resolution`/`upscale_with`.

### Largo plazo — unificar en un servicio

- Empaquetar Guion_expert + OpenMontage en un solo `docker-compose` con dos servicios (`guion_expert` FastAPI + `openmontage` EP).
- Webhook desde Guion_expert al completar scene_plan → disparo automático del EP sobre el project_id.
- Un único frontend que muestre los dos dashboards + estado de render en tiempo real.

### Deuda explícita a priorizar

- [ ] Normalizar nombre y esquema: renombrar `asset_plan.json` (driver-style) a `asset_manifest.json` (schema-válido).
- [ ] Borrar drivers `run_*_director.py` una vez que `bridge.asset_generator` los reemplace.
- [ ] Tests end-to-end: mock de fal/Suno + scene_plan fixture → asset_manifest + render final.
- [ ] Env path en drivers: parametrizar vía `ENV['OPENMONTAGE_ROOT']` en vez de hardcode.
- [ ] Flag `strict=True` en `export_project_to_openmontage` para elevar warnings a errores.

---

## 15. Apéndices

### 15.1 Comandos clave

**Generar y exportar proyecto Guion_expert → OpenMontage**:

```bash
# 1. Correr pipeline de Guion_expert (crea output/YYYYMMDD_HHMMSS/)
cd Guion_expert
./ejecutar.sh "reel de instagram sobre banda cover 3SM, una historia intrigante"

# 2. Exportar al formato OpenMontage (vía helper o CLI)
python -c "
from bridge import export_project_to_openmontage
from pathlib import Path
export_project_to_openmontage(
    project_dir=Path('output/20260420_034929'),
    openmontage_root=Path('../OpenMontage/OpenMontage'),
    idea='reel de instagram sobre banda cover 3SM, una historia intrigante',
)"
```

**Renderizar zero-key (Remotion, sin keys)**:

```bash
cd OpenMontage
python render_demo.py reel-de-instagram-sobre-banda-cover-3sm-una-historia-intrig
```

**Generar assets via `bridge.asset_generator`** (production-grade, reemplaza drivers one-off):

```bash
cd Guion_expert
python -m bridge.asset_generator \
    ../OpenMontage/OpenMontage/projects/<project_id>/stages/scene_plan.json \
    --budget 3.00 \
    --concurrency 2 \
    --lora-images https://v3b.fal.media/files/.../3SM_dataset.zip
```

**Ejecución agentic (EP)**:

```
Usar el prompt en projects/<id>/AGENT_PROMPT.md
→ spawnear agente en OpenMontage con pipeline_defs/cinematic.yaml
→ el EP reanuda desde `assets`
```

### 15.2 Variables de entorno (en `OpenMontage/.env` y `Guion_expert/.env`)

```bash
# fal.ai (FLUX, Kling, Runway, WAN, mmaudio, Real-ESRGAN, flux-lora-fast-training)
FAL_KEY=...

# Anthropic (pipeline Guion_expert)
ANTHROPIC_API_KEY=...

# Suno (música hero vía side-car gcui-art/suno-api)
SUNO_COOKIE=...

# Budget cap default (override vía CLI --budget)
BUDGET_USD=3.00
```

### 15.3 Paths canónicos

| Path | Propósito |
|---|---|
| `Guion_expert/output/YYYYMMDD_HHMMSS/` | Output raw de Guion_expert (en español) |
| `Guion_expert/bridge/openmontage_export.py` | Traductor (1705 líneas) |
| `Guion_expert/bridge/asset_generator.py` | Orquestador production-grade (1013 líneas, commit 11) |
| `OpenMontage/projects/<id>/stages/` | 4 artifacts JSON + opcionales (lora_models, asset_plan) |
| `OpenMontage/projects/<id>/assets/` | MP4/JPG/MP3 generados |
| `OpenMontage/projects/<id>/renders/` | MP4 final |
| `OpenMontage/schemas/artifacts/*.schema.json` | JSON Schemas que validan el handoff |
| `OpenMontage/pipeline_defs/cinematic.yaml` | Manifest con 7 stages + sub-stages |
| `OpenMontage/skills/pipelines/cinematic/*.md` | Skills por director (research → publish) |
| `OpenMontage/remotion-composer/public/demo-props/<slug>.json` | Mirror de remotion-cuts.json |

### 15.4 Glosario

- **Master Stack v2**: schema Pydantic que empaca FLUX + I2V + SFX + música + post-pro por escena (Guion_expert).
- **Scene plan v1.0**: JSON oficial de OpenMontage que lista escenas con `required_assets[]` y (opcionalmente) `master_stack`.
- **Pipeline cinematic**: de `pipeline_defs/cinematic.yaml`, 7 stages serial + EP.
- **Style playbook**: YAML en `OpenMontage/styles/*.yaml` que define tipografía, paleta, motion params. Hoy disponibles: `flat-motion-graphics`, `clean-professional`, `minimalist-diagram`, `anime-ghibli`.
- **Zero-key render**: camino Remotion que no necesita APIs pagas — solo Node + npx.
- **Driver one-off**: script Python ad-hoc (`run_*_director.py`) que corrió el pipeline en el proyecto 3SM.
- **EP**: Executive Producer, skill meta-nivel que orquesta los directors del pipeline.
- **LoRA (Low-Rank Adaptation)**: fine-tuning de FLUX para consistencia de personajes/estilo — trigger word en el prompt.

### 15.5 Archivos fuente consultados para este informe

| Ruta | Líneas | Rol |
|---|---|---|
| `Guion_expert/bridge/openmontage_export.py` | 1705 | Traductor Guion_expert → OM |
| `Guion_expert/bridge/asset_generator.py` | 1013 | Orquestador production-grade (commit 11) |
| `OpenMontage/OpenMontage/schemas/artifacts/scene_plan.schema.json` | 102 | Schema scene_plan |
| `OpenMontage/OpenMontage/schemas/artifacts/brief.schema.json` | 48 | Schema brief |
| `OpenMontage/OpenMontage/schemas/artifacts/asset_manifest.schema.json` | 45 | Schema target del stage `assets` |
| `OpenMontage/OpenMontage/pipeline_defs/cinematic.yaml` | 266 | Manifest pipeline cinematic |
| `OpenMontage/OpenMontage/lib/checkpoint.py` | 341 | Stage/artifact resolver |
| `OpenMontage/OpenMontage/lib/pipeline_loader.py` | 208 | Pipeline YAML loader |
| `OpenMontage/OpenMontage/render_demo.py` | 133 | Zero-key Remotion renderer |
| `OpenMontage/OpenMontage/skills/pipelines/cinematic/asset-director.md` | ~300 | Skill actual (sin v2) |
| `OpenMontage/OpenMontage/config.yaml` | 33 | Config global (budget, checkpoint policy) |
| `projects/.../stages/checkpoint.json` | 21 | Ejemplo real del handoff |
| `projects/.../stages/scene_plan.json` | 673 | Ejemplo real (6 escenas, master_stack v2) |
| `projects/.../run_asset_director.py` | 120 | Driver FLUX+Kling del proyecto 3SM |
| `projects/.../run_audio_director.py` | 80 | Driver MMAudio del proyecto 3SM |
| `projects/.../run_edit_director.py` | 50 | Driver moviepy concat |
| `projects/.../train_lora.py` | 50 | Driver fal flux-lora-fast-training |

---

**Fin del informe.** Para la arquitectura interna de Guion_expert (schemas Pydantic, integrations fal/Suno, config YAML, 12 commits del feature branch), ver `INFORME_GUION_EXPERT.md` en esta misma carpeta.
