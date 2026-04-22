# Informe técnico — Guion_expert

> **Audiencia:** dev handoff (vos + un dev que entra al repo).
> **Fecha:** 2026-04-20 · **Branch activo:** `feature/llm-provider-unified` · **Último commit:** `c64a37c`
> **Estado:** migración Claude Haiku 4.5 en curso. Commits 1–11 landeados. PR a `main` y deploy a Hetzner CX22 pendientes.

---

## Tabla de contenidos

1. [Resumen ejecutivo](#1-resumen-ejecutivo)
2. [Arquitectura](#2-arquitectura)
3. [Estructura del repositorio](#3-estructura-del-repositorio)
4. [Módulos webapp/ — pipeline y servidor](#4-módulos-webapp--pipeline-y-servidor)
5. [Módulos webapp/schemas/ — Master Stack v2](#5-módulos-webappschemas--master-stack-v2)
6. [Módulos webapp/integrations/ — fal.ai + Suno](#6-módulos-webappintegrations--falai--suno)
7. [Módulos bridge/ — OpenMontage + asset_generator](#7-módulos-bridge--openmontage--asset_generator)
8. [Config, prompts, estructuras](#8-config-prompts-estructuras)
9. [Observabilidad y logging](#9-observabilidad-y-logging)
10. [Docker, deploy y operaciones](#10-docker-deploy-y-operaciones)
11. [Flujo end-to-end con un ejemplo real](#11-flujo-end-to-end-con-un-ejemplo-real)
12. [Historia de commits](#12-historia-de-commits)
13. [Deuda técnica y riesgos conocidos](#13-deuda-técnica-y-riesgos-conocidos)
14. [Roadmap inmediato](#14-roadmap-inmediato)
15. [Apéndices](#15-apéndices)

---

## 1. Resumen ejecutivo

**Qué es Guion_expert.** Suite de IA para escritura de guiones cinematográficos que automatiza el pipeline `idea → guion estructurado → scene_plan cinematográfico → video final con música original`. La autoría narrativa vive acá; la renderización vive en OpenMontage (Remotion + FFmpeg). Entre los dos hay un bridge determinístico que traduce artefactos.

**Qué hace único.** Nada de "un prompt gigante a GPT-4". El pipeline está descompuesto en siete experts especializados (clasificador, concepto, arquitecto, escaletista, dialoguista, localizador, director_flow) cada uno con su propia temperatura, max_tokens y prompt. Los cuatro modelos de video generativo (Kling 2.5 Pro, Runway Gen-3, WAN 2.1 14B, FLUX.1 Pro) se ruteán por una tabla determinística `subject_type → modelo`, no los elige el LLM.

**Estado actual (2026-04-20).**
- Seis experts totalmente migrados a Claude Haiku 4.5 (`claude-haiku-4-5-20251001`).
- Pipeline produce scene_plans v2 con `master_stack` completo (FLUX + I2V + Suno + mmaudio + post).
- Bridge a OpenMontage funciona end-to-end. Un run real de 2026-04-20 generó seis escenas con `master_stack_coverage=1.0`.
- Integraciones fal.ai y Suno (self-hosted) listas, sin tocar API todavía (faltan keys reales).
- Orquestador de generación de assets (`bridge/asset_generator.py`) listo, no corrido.
- Falta el PR a `main` y el deploy a Hetzner CX22.

**Costo estimado por reel de 30s.** ~$2.52 (6 escenas × [FLUX + Kling + mmaudio]). Suno es flat-rate Premium (~$10/mes de Leo). El primer run agrega ~$1.50 por LoRA training de identidad (una vez por banda).

**Decisiones de diseño críticas.** Claude tool use fuerza JSON válido (sin regex ni fallbacks). Bridge sin LLM calls. Routing I2V por tabla estática. Suno self-hosted porque no hay API pública. fal.ai como proxy único para seis modelos. Pydantic-settings fail-fast al boot.

---

## 2. Arquitectura

### Vista de alto nivel

```
┌─────────────────────────────────┐
│  Guion_expert (Python 3.14)     │
│                                 │
│  Flask + SocketIO ──► Pipeline  │
│     │                   │       │
│     ▼                   ▼       │
│  Browser          Claude Haiku  │
│  (index.html)     4.5 + tool use│
│                         │       │
│                         ▼       │
│                    output/      │
│                    <timestamp>/ │
│                    escenas/     │
│                    prompts_veo/ │
│                    (VeoPrompt   │
│                     JSON v2)    │
└────────────────┬────────────────┘
                 │
                 │  bridge/openmontage_export.py (sin LLM)
                 ▼
┌─────────────────────────────────┐
│  OpenMontage/                   │
│  projects/<slug>/stages/        │
│    brief.json                   │
│    script.json                  │
│    scene_plan.json  ◄──────────┐│
│    checkpoint.json              ││
│    remotion-cuts.json           ││
└─────────────────────────────────┘
                                 ││
                                 ││
                                 ││  bridge/asset_generator.py
                                 ││
┌────────────────────────────────▼▼┐
│  Integrations (webapp/integrations)│
│                                    │
│  FalClient ──► fal.ai              │
│    ├─ FLUX.1 Pro (+ LoRA)          │
│    ├─ Kling 2.5 Pro (humans)       │
│    ├─ Runway Gen-3 (landscapes)    │
│    ├─ WAN 2.1 14B (slow camera)    │
│    ├─ mmaudio v2 (SFX)             │
│    └─ Real-ESRGAN (upscale)        │
│                                    │
│  SunoClient ──► gcui-art/suno-api  │
│                 (self-hosted,      │
│                  cookie Premium)   │
└────────────────┬───────────────────┘
                 │
                 │  URLs de assets escritos en
                 │  scene_plan.json → resolved_assets
                 ▼
         OpenMontage agent
         (Remotion + FFmpeg)
              │
              ▼
          MP4 final 9:16
```

### El pipeline de 3 fases (Master Stack v2)

**Fase 1 — Ancla visual (FLUX.1 Pro).** El frame 0 manda. Una imagen bien iluminada, bien compuesta, con paleta coherente y texturas ricas, preserva todo eso cuando el video I2V le inyecta movimiento. Si FLUX produce algo mediocre, el video hereda esa mediocridad.

**Fase 2 — Inyección de movimiento (routing I2V determinístico).** Cada modelo tiene un superpoder:

| subject_type | Modelo | Por qué |
|---|---|---|
| `human_gesture` / `human_performance` / `creature_animal` / `vfx_heavy` | **Kling 2.5 Pro** | Mejor preservación de rostros y gestos humanos |
| `landscape_static` / `landscape_dynamic` / `drone_sweep` | **Runway Gen-3 Alpha Turbo** | Mejor física de mundo (cielo, agua, partículas) |
| `subtle_slow_camera` / `object_reveal` | **WAN 2.1 14B** | Maestro del dolly/push lento y elegante |

La tabla vive en `webapp/schemas/cinematic.py::VIDEO_MODEL_ROUTING`. Claude elige el `subject_type` (de nueve opciones enumeradas); la tabla hace el resto. **No delegamos el routing al LLM** — es un tradeoff de robustez contra creatividad, consciente.

**Fase 3 — Post-producción.** RIFE (interpolación de frames para slow-mo suave), Real-ESRGAN o Topaz para upscale 4K en escenas hero, mmaudio v2 para SFX contextuales pegados al video. Todo enrutable desde `scene["master_stack"]["post_production"]`.

### Sonic Atmosphere (paralelo a las tres fases)

Cada escena emite un `SonicAtmosphere` con:

- `music_brief` — prompt para Suno, escrito en lenguaje musical ("bajo solo en Mi menor, 55 BPM, fingerstyle seco sin reverb, decrescendo natural...").
- `music_reference_artists` — lista de referencias tonales (Jóhann Jóhannsson, Max Richter, etc.).
- `sfx` — efectos diegéticos y no-diegéticos (crujidos, chasquidos, respiración).
- `diegetic_sound` — el "ruido del mundo" de la escena.
- `silence_moments` — dónde el silencio es un personaje.

`bridge/asset_generator.py` envía el `music_brief` de la escena hero a Suno y los `sfx` de cada escena individual a mmaudio v2.

---

## 3. Estructura del repositorio

```
Guion_expert/
├── README.md                    Readme público
├── CLAUDE.md                    Contexto para agentes Claude Code/Cowork
├── HANDOFF.md                   Retomar sesión (canónico)
├── CHANGELOG.md                 Log detallado por commit
├── FEATURES_COMPLETE.md         Features ya cerradas (pre-migración)
├── CONTRIBUTING.md, LICENSE     Convencional
├── Dockerfile                   Multi-stage Python 3.14-slim
├── docker-compose.yml           guion-web + suno-api side-car
├── requirements.txt             flask, anthropic, pydantic, httpx, structlog, etc.
├── .env.example                 Template completo (149 líneas, 8 secciones)
├── .env                         Real (gitignored) — tiene ANTHROPIC_API_KEY, FAL_API_KEY, SUNO_COOKIE
├── .dockerignore, .gitignore
│
├── webapp/
│   ├── server.py                Flask app + SocketIO (779 líneas, 20+ rutas)
│   ├── pipeline_claude.py       Orquestador del pipeline de 7 stages (475 líneas)
│   ├── llm_provider.py          Adapter Claude/Ollama + generate_structured (269 líneas)
│   ├── config.py                Pydantic-settings fail-fast (318 líneas)
│   ├── observability.py         structlog + context vars + Flask integration (167 líneas)
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── cinematic.py         Master Stack v2: VeoPrompt + routing (394 líneas)
│   ├── integrations/
│   │   ├── __init__.py          Exports agrupados
│   │   ├── base.py              BaseHTTPClient (httpx async/sync + retries) (507 líneas)
│   │   ├── fal.py               FalClient unificado — 11 modelos (816 líneas)
│   │   └── suno.py              SunoClient vía gcui-art/suno-api (548 líneas)
│   ├── static/                  assets del frontend
│   ├── templates/               index.html + parciales
│   └── uploads/                 PDFs analizados por usuarios (gitignored)
│
├── bridge/
│   ├── __init__.py              Export lazy de asset_generator
│   ├── openmontage_export.py    Bridge determinístico → OpenMontage (1705 líneas)
│   └── asset_generator.py       Orquestador FLUX/I2V/Suno/mmaudio (1013 líneas)
│
├── config/
│   ├── llm_provider.yaml        Per-expert temperature/max_tokens
│   ├── formats.json             56 formatos de video (vertical_social, streaming, etc.)
│   ├── structures.json          45 estructuras narrativas
│   ├── models.conf              Legacy Ollama (en deprecación)
│   ├── production.conf, sd.conf Legacy
│
├── prompts/                     20 archivos .txt (prompts por expert)
│   ├── 00_clasificador[_completo].txt
│   ├── 01_concepto.txt
│   ├── 02_arquitecto.txt
│   ├── 02_five_act.txt, 02_hero_journey.txt, 02_in_media_res.txt,
│   ├── 02_save_the_cat.txt, 02_simple.txt, 02_story_circle.txt
│   ├── 03_escaletista.txt
│   ├── 04_dialoguista.txt       ← emite sonic_atmosphere
│   ├── 05_veo_flow.txt          ← Master Stack philosophy (director_flow)
│   ├── 06_sd.txt                Prompts Stable Diffusion legacy
│   ├── 07_youtube_short.txt, 08_reel_instagram.txt, 09_tiktok.txt
│   ├── 10_localizador_chile.txt
│   ├── 11_director_flow.txt, 12_director_flow_json.txt
│   └── 12_mi_experto.txt
│
├── estructuras/
│   ├── five_act.txt
│   └── in_media_res.txt
│
├── templates/
│   └── narrativas/              Plantillas narrativas
│
├── scripts/                     Shell scripts de UX
│   ├── pipeline.sh, pipeline_shorts.sh
│   ├── analizar_archivo.sh, analizar_pdf.sh, analizar_sub.sh
│   ├── comparar.sh, exportar.sh, lib.sh, monitor.sh
│   ├── pre_clasificar.sh, selector_estructura.sh, selector_prompt_estructura.sh
│   ├── storyboard.sh, usar_template.sh, validar.sh
│
├── tools/
│   ├── director_flow.sh
│   ├── extract_pdf.py
│   ├── generar_presupuesto.sh
│   ├── mostrar_estructura.sh
│   ├── test_clasificador.sh
│
├── docs/
│   ├── GUIA_COMPLETA.md
│   ├── INICIO_RAPIDO.txt
│   └── audit_ollama.md
│
├── output/                      Proyectos generados (~30 runs, gitignored)
│   └── <YYYYMMDD_HHMMSS>/
│       ├── clasificacion/
│       ├── concepto/
│       ├── escaleta/
│       ├── estructura/
│       ├── escenas/
│       ├── prompts_sd/
│       └── prompts_veo/
│
├── logs/                        Logs estructurados JSON (gitignored)
├── analyzer/                    Outputs de análisis de PDFs (pre-migración)
├── venv/                        Virtualenv local (gitignored)
│
└── Shell entrypoints (UX)
    ├── ejecutar.sh, ejecutar_con_storyboard.sh
    ├── generar_short.sh, detener.sh, iniciar.sh
    ├── logs.sh, restart.sh, status.sh, stop.sh
    ├── sync_github.sh, github_setup.sh
    └── test_pipeline.sh, verify_selectors.sh, analizar_completo.sh
```

**Totales:** 7.112 líneas de Python across 14 módulos (sin tests dedicados todavía — la verificación es `py_compile` + smoke tests manuales).

---

## 4. Módulos webapp/ — pipeline y servidor

### `webapp/server.py` (779 líneas)

Flask app con SocketIO para streaming de eventos al cliente. Expone 20+ rutas REST:

| Ruta | Método | Descripción |
|---|---|---|
| `/` | GET | Frontend SPA |
| `/api/health` | GET | Status del LLM provider |
| `/api/structures/all` | GET | Lista las 45 estructuras narrativas |
| `/api/experts` | GET | Lista los 7 experts del pipeline |
| `/api/projects` | GET | Lista proyectos generados en `output/` |
| `/api/project/<id>/open` | POST | Abre la carpeta (macOS `open`, Linux `xdg-open`) |
| `/api/project/<id>/files` | GET | Árbol de archivos del proyecto |
| `/api/project/<id>/download/<path>` | GET | Descarga un archivo específico |
| `/api/project/<id>/view/<path>` | GET | Visualiza inline |
| `/api/generate` | POST | **Dispara el pipeline completo** (threaded) |
| `/api/expert/run` | POST | Corre un solo expert sobre un input |
| `/api/structure/generate` | POST | Genera con estructura específica |
| `/api/flow/generate` | POST | Corre solo el director_flow |
| `/api/analyze/upload` | POST | Analiza un PDF subido por el usuario |
| `/api/config/models` | GET | Info de modelos disponibles |
| `/api/openmontage/export/<id>` | POST | Exporta manualmente a OpenMontage |

**Patrón de concurrencia.** Cada pipeline corre en un `threading.Thread` dedicado. El thread emite eventos por SocketIO (`log`, `stage_start`, `stage_end`, `pipeline_done`). El frontend los pinta en tiempo real.

**Bridge auto-export.** Al terminar el pipeline, `_maybe_export_to_openmontage()` (línea 340) intenta exportar automáticamente al proyecto OpenMontage. Si falla (repo ausente, formato no soportado), solo loguea warning — no aborta el run.

**Integración con observability.** `init_flask_logging(app)` inyecta `trace_id` por request + loguea `http_request_start` / `http_request_end` con latencia. Todos los logs que se emiten dentro del request heredan ese `trace_id` automáticamente vía `contextvars`.

### `webapp/pipeline_claude.py` (475 líneas)

El orquestador del pipeline. Función principal: `run_full_pipeline(idea, formato, estructura, auto_detect, socketio, project_dir)`.

Ocho stages secuenciales (cada uno emite log al socket):

1. **Clasificación** — detecta formato + estructura narrativa. Output en `clasificacion/resultado.txt`.
2. **Concepto** — genera logline, tema, hook. `concepto/concepto.txt`.
3. **Estructura** — aplica plantilla narrativa (viaje del héroe, save the cat, etc.). `estructura/estructura.txt`.
4. **Escaleta** — expande la estructura a lista de escenas. `escaleta/escaleta.txt`.
5. **Escenas** — dialoguista escribe cada escena individual. `escenas/escena_NNN.txt` + `escenas/sonic_NNN.json` (nuevo Commit 7).
6. **Prompts SD** — (legacy, mantenido para compatibilidad). `prompts_sd/NNN.txt`.
7. **Prompts VEO** — director_flow emite VeoPrompt JSON v2 por escena. `prompts_veo/veo_NNN.json`.
8. **Bridge OpenMontage** — (opcional, auto-trigger) exporta todo al repo OpenMontage.

Cada stage llama a `llm_provider.generate(role=..., prompt=...)` o `llm_provider.generate_structured(...)` (el director_flow). Las respuestas se escriben a disco con `_write()` y se emiten por socket con `_emit()`.

**Recovery de estados parciales.** Si un stage falla y se reintenta, los stages previos no se reejecutan (los archivos ya están en `project_dir`). El pipeline es idempotente a nivel file-system.

### `webapp/llm_provider.py` (269 líneas)

Adapter que unifica Claude y Ollama bajo la misma interfaz. **Claude es el default**; Ollama solo sobrevive por si hace falta fallback offline.

**Funciones principales:**

- `generate(model, prompt, stream=True, role=None) → Iterator[str]` — streaming texto libre. El `role` busca override en `config/llm_provider.yaml` (temperatura/max_tokens por expert).
- `generate_structured(prompt, tool_name, tool_description, input_schema, role=None, system_prompt="") → dict` — **fuerza Anthropic tool use** con `tool_choice={"type":"tool", "name":tool_name}`. Si el modelo devuelve texto libre en vez de invocar la tool, raises `RuntimeError`. Sin fallbacks silenciosos, sin parseo de regex.
- `is_available() → bool`, `provider_status() → dict` — health checks.

**Fail-fast al import.** Si `ANTHROPIC_API_KEY` falta (o tiene valor placeholder `REEMPLAZAR_...`), el import de `webapp.config` crashea inmediatamente con mensaje claro y stack minimal. Mejor morir al arrancar que al tercer request del usuario.

### `webapp/config.py` (318 líneas)

`Settings` class basada en `pydantic_settings.BaseSettings`. Lee `.env` en la raíz del proyecto + variables de entorno, valida con Pydantic v2.

**Campos agrupados por sección:**

- **LLM:** `llm_provider` (Literal["claude","ollama"]), `anthropic_api_key` (SecretStr), `claude_model`, `claude_max_tokens`, `claude_temperature`, `ollama_host`.
- **fal.ai:** `fal_api_key` (SecretStr), `fal_base_url`, `fal_poll_interval_s`, `fal_poll_max_wait_s`, `flux_lora_trigger`, `flux_lora_url`, `flux_model`, `flux_steps`, `flux_guidance`, `flux_image_size`.
- **I2V defaults:** `i2v_default_model`, `i2v_default_duration_s`.
- **Post:** `real_esrgan_scale`, `rife_target_fps`.
- **Suno:** `suno_cookie` (SecretStr), `suno_api_url`, `suno_model`, `suno_poll_interval_s`, `suno_poll_max_wait_s`, `suno_default_instrumental`.
- **OpenMontage:** `openmontage_root`, `max_budget_usd`, `max_scenes_per_project`.
- **HTTP:** `http_timeout_connect`, `http_timeout_read`, `http_max_retries`, `http_backoff_base`.

**Per-expert config.** `config/llm_provider.yaml` carga en `_experts` (PrivateAttr). `settings.params_for(role) → (max_tokens, temperature)` hace merge: override per-expert sobre defaults globales.

**Validación cruzada.** En `model_post_init` revisa que si `llm_provider=claude`, la API key exista y no tenga el valor placeholder. Si falla, el singleton `settings = Settings()` crashea con mensaje humano y `sys.exit(1)`.

---

## 5. Módulos webapp/schemas/ — Master Stack v2

### `webapp/schemas/cinematic.py` (394 líneas)

El core de "Master Stack v2". Siete clases Pydantic v2 que conforman el input_schema de la tool `emit_veo_prompt` de Anthropic.

**Jerarquía:**

```
VeoPrompt (root)
├── scene_id: str ^scene-\d{3}$
├── scene_number: int
├── narrative_beat: Literal[...9 opts...]
├── visual_anchor: VisualAnchor
│   ├── composition: str (máx 600 chars)
│   ├── palette: list[str] (1-6 items)
│   ├── lighting: str
│   ├── textures: list[str]
│   ├── style: Literal[11 opts] (cinematic_35mm_kodak, wes_anderson, ...)
│   ├── subject_description: str
│   └── environment: str
├── camera: CameraPhysics
│   ├── shot_type: Literal[12 opts]
│   ├── movement: Literal[15 opts] (static/dolly_in/orbit/handheld/crane/etc.)
│   ├── lens_mm: Literal[14, 24, 35, 50, 85, 135, 200]
│   └── duration_seconds: float (1-15)
├── motion_intent: MotionIntent
│   ├── subject_type: Literal[9 opts] — driver del routing I2V
│   ├── action: str
│   ├── motion_intensity: Literal["low","medium","high"]
│   └── physics_notes: str
├── sonic: SonicAtmosphere
│   ├── mood: list[str] (1-5)
│   ├── music_brief: str (prompt para Suno)
│   ├── music_reference_artists: list[str]
│   ├── sfx: list[str]
│   ├── diegetic_sound: str
│   └── silence_moments: list[str]
├── post_production: PostProduction
│   ├── target_fps: Literal[24, 30, 60]
│   ├── target_resolution: Literal["1080p", "4k"]
│   ├── upscale_with: Literal["real_esrgan", "topaz", "none"]
│   └── fps_interpolation: Literal["rife", "none"]
├── text_on_screen: str (opcional)
└── director_notes: str (opcional)

Método: VeoPrompt.chosen_video_model() → str  (consulta VIDEO_MODEL_ROUTING)
```

**Routing table** (mismo archivo, top-level):

```python
VIDEO_MODEL_ROUTING: dict[str, str] = {
    "human_gesture":        "kling-2.5-pro",
    "human_performance":    "kling-2.5-pro",
    "creature_animal":      "kling-2.5-pro",
    "landscape_static":     "runway-gen3-alpha-turbo",
    "landscape_dynamic":    "runway-gen3-alpha-turbo",
    "drone_sweep":          "runway-gen3-alpha-turbo",
    "subtle_slow_camera":   "wan-2.1-14b",
    "object_reveal":        "wan-2.1-14b",
    "vfx_heavy":            "kling-2.5-pro",
}

def choose_video_model(subject_type) -> str:
    """Fallback a kling-2.5-pro si subject_type no está mapeado."""
    return VIDEO_MODEL_ROUTING.get(subject_type, "kling-2.5-pro")
```

**Por qué tool use y no regex.** Antes usábamos `json.loads(extraer_regex(texto_libre_del_modelo))` — frágil, sin validación de tipos, fallbacks silenciosos que producían scene_plans mal formados. Ahora el input_schema de la tool garantiza que Claude SOLO puede responder emitiendo un JSON que pasa la validación Pydantic. Si no puede, raises — no hay "parser resiliente" que termine inventando campos.

**Por qué `Literal` en todos los enums.** Claude interpreta `enum: [...]` en el JSON schema y NUNCA devuelve valores fuera del enum. Esto baja la entropía en el output y permite que `VIDEO_MODEL_ROUTING` sea un dict sin default que igual nunca KeyError.

---

## 6. Módulos webapp/integrations/ — fal.ai + Suno

### `webapp/integrations/base.py` (507 líneas)

`BaseHTTPClient` compartido. Subclases: `FalClient`, `SunoClient`.

**Capacidades:**

- Sync + async parity (13 métodos cada uno). Usamos sync desde Flask, async desde `asset_generator.py`.
- Retry loop en 5xx, 429, `httpx.ConnectError`, `httpx.ReadError`, JSON decode errors.
- Backoff exponencial con jitter. Cap duro en 60s por retry.
- Respeto al `Retry-After` header (seconds o HTTP-date).
- Auth via `_auth_headers()` implementado por subclase (Bearer, Cookie, custom).
- Logs structlog con `service`, `method`, `url`, `status`, `elapsed_ms` — todos los requests trazables.
- Context managers: `with FalClient() as fal: ...` y `async with FalClient() as fal: ...`.

**Excepciones:**

- `HTTPClientError` — 4xx no-retryables.
- `RetryableError` — 5xx, transport errors, JSON decode.
- `RateLimitError` — 429 con Retry-After respetado.

### `webapp/integrations/fal.py` (816 líneas)

Un cliente para todos los modelos de fal.ai. Queue-based:

```
POST /{model_id}                              → request_id
GET  /{model_id}/requests/{id}/status?logs=1  → {status, logs}
GET  /{model_id}/requests/{id}                → result payload
```

**11 modelos registrados** en `FAL_MODEL_IDS`:

| Alias interno | fal model_id | Función |
|---|---|---|
| `flux-1.1-pro` | `fal-ai/flux-pro/v1.1` | T2I base |
| `flux-1.1-pro-ultra` | `fal-ai/flux-pro/v1.1-ultra` | T2I 2K |
| `flux-lora` | `fal-ai/flux-lora` | T2I con LoRA |
| `flux-lora-train` | `fal-ai/flux-lora-fast-training` | Train subject LoRA (~$1.50) |
| `kling-2.5-pro` | `fal-ai/kling-video/v2.5-turbo/pro/image-to-video` | I2V humanos |
| `runway-gen3-alpha-turbo` | `fal-ai/runway-gen3/turbo/image-to-video` | I2V landscapes |
| `wan-2.1-14b` | `fal-ai/wan-pro/v2.1-14b/image-to-video` | I2V slow camera |
| `mmaudio-v2` | `fal-ai/mmaudio-v2` | SFX contextuales |
| `tts-playai` | `fal-ai/playai/tts/v3` | Text-to-speech |
| `real-esrgan` | `fal-ai/real-esrgan` | Upscale 2x/4x |
| `rife-interp` | `fal-ai/rife-interpolation` | Interpolación frames |

**Primitivas de alto nivel** (sync y async):

- `flux_generate(prompt, lora_url=None, ...)` — T2I.
- `flux_lora_train(images_data_url, trigger_word, steps=1000)` — 1000 steps, cap 20min.
- `dispatch_i2v(subject_type, image_url, prompt, duration_s)` — **routing determinístico** delegado a `choose_video_model()`.
- `kling_i2v`, `runway_i2v`, `wan_i2v` — calls directos por si querés override.
- `mmaudio(video_url, prompt)` — agrega SFX al video.
- `real_esrgan(image_url, scale=2)`, `rife_interpolate(video_url, target_fps=60)`.
- `tts(text, voice)` — PlayAI v3.

**FalJobResult.first_url()** — extractor robusto que cubre los 7 patterns de response de fal: `images[0].url`, `video.url`, `audio.url`, `image.url`, `diffusers_lora_file.url`, `images[0]` string, top-level `url`.

**Excepciones:** `FalJobFailed` (status=FAILED/ERROR/CANCELLED), `FalJobTimeout` (excedió el cap de poll).

### `webapp/integrations/suno.py` (548 líneas)

Cliente para `gcui-art/suno-api` (reverse-proxy self-hosted a suno.com, corre en side-car Docker).

**Por qué self-hosted.** Suno NO tiene API pública. Leo paga Suno Premium ($10/mes); la cookie de sesión (DevTools → Cookies) se pasa como env var al contenedor `suno-api`, que hace proxy a suno.com con esa cookie en el Header.

**Flujo:**

1. `POST /api/custom_generate` con `{prompt, tags, title, make_instrumental, wait_audio:false, model}` → devuelve 2 clips (variants) con `id` pero `audio_url` vacío y `status="submitted"`.
2. `GET /api/get?ids=<csv>` cada 5s hasta que cada clip pase por `submitted → queued → streaming → complete`.
3. `SunoClip` dataclass expone `is_complete`, `is_streaming`, `is_failed`. `select_best()` elige el clip con mayor `duration_s` (Suno a veces genera una variante truncada).

**Auth** — NO usa Bearer. La cookie va como header `Cookie: <cookie-string>` en cada request. Se refresca ~24h según la vida de la sesión; si empieza a tirar 401, Leo regenera desde DevTools y actualiza `.env`.

**Excepciones:** `SunoClipFailed`, `SunoTimeout`.

**Parse tolerante.** `_parse_submit_response()` cubre los 3 formatos que devuelve gcui-art/suno-api: `list` directo, `{"data": [...]}`, `{"clips": [...]}`.

---

## 7. Módulos bridge/ — OpenMontage + asset_generator

### `bridge/openmontage_export.py` (1.705 líneas)

El bridge determinístico de Guion_expert → OpenMontage. **Sin LLM calls** — todo es parseo de texto + mapeos estáticos + construcción de JSON.

**Input:** carpeta `output/<timestamp>/` con:
- `clasificacion/resultado.txt`
- `concepto/concepto.txt`
- `estructura/estructura.txt`
- `escaleta/escaleta.txt`
- `escenas/escena_NNN.txt` (+ opcional `sonic_NNN.json`)
- `prompts_veo/veo_NNN.json`

**Output:** `<OpenMontage>/projects/<slug>/stages/`:
- `brief.json` (validado contra el schema de OpenMontage)
- `script.json`
- `scene_plan.json` (con `master_stack` v2 por escena)
- `checkpoint.json`
- `remotion-cuts.json` (listo para `python render_demo.py`)

**Funciones clave:**

- `_parse_classification_file()` — extrae `{formato, estructura, duration_seconds, estilo_visual}` del output del clasificador. Tolera variantes de formato ("REEL", "REEL_INSTAGRAM", "Instagram Reel").
- `_normalize_veo()` — acepta dos formatos de VeoPrompt: flat legacy `{plano, movimiento, iluminacion}` y el nested v2 con `parametros_globales` + `tracking_entidades` + `secuencia_planos`.
- `_normalize_master_stack()` — **construye el bloque `master_stack`** que se adjunta a cada escena: toma los campos de VeoPrompt, completa con heurísticas si algo falta, añade `chosen_video_model` resuelto por la tabla de routing, genera un `flux_prompt` sintético.
- `_synthesize_flux_prompt(visual, motion)` — junta composition + palette + lighting + **textures (list o str, fix de Commit 7.1)** + style en una sola línea.
- `_allocate_timestamps(scenes, total_duration)` — distribuye `start_seconds` / `end_seconds` respetando el `duration_seconds` de cada cámara.
- `_hero_moment_index(n_scenes)` — heurística: si N=6, hero=4 (índice 3, punto de giro clásico); si N=3, hero=2; fallback al medio.
- `_select_playbook()` — elige el style playbook de OpenMontage (`neo_noir`, `wes_anderson`, etc.) según formato + estilo_visual.
- `_build_brief`, `_build_script`, `_build_scene_plan`, `_build_checkpoint`, `_build_remotion_cuts` — builders por artifact.
- `_validate_artifacts()` — corre jsonschema contra los schemas oficiales de OpenMontage.

**Entry point:** `export_project_to_openmontage(project_dir, openmontage_root, idea, brief_hint=None)` → `dict[str, Path]` con las rutas absolutas de cada artifact.

### `bridge/asset_generator.py` (1.013 líneas)

El orquestador que cierra el loop. **Rompe intencionalmente la regla de "bridge sin deps a webapp"** — importa de `webapp.integrations.{fal,suno}` + `webapp.config`. Es el único módulo con ese privilegio, documentado en su docstring.

**Por qué está en `bridge/` y no en `webapp/`.** Consume el contrato de OpenMontage (scene_plan.json) como input/output, y corre fuera del ciclo request-response de Flask — típicamente CLI o job worker. Ponerlo en `webapp/` lo acoplaría al servidor HTTP; ponerlo en `bridge/` refleja que su unit of work es "un scene_plan".

**Pipeline por escena:**

1. **FLUX** (con LoRA si `settings.flux_lora_url` está seteado). Prompt = `_synthesize_flux_prompt(scene, trigger=settings.flux_lora_trigger)` — combina `visual_anchor.{subject_description, composition, palette, lighting, textures, style}`.
2. **I2V via `dispatch_i2v()`** — el modelo sale de `master_stack.chosen_video_model`, el prompt de `motion_intent.{action, physics_notes}` + `camera.movement`, duración de `camera.duration_seconds`.
3. **mmaudio** (opcional, controlable con `--no-sfx`) — toma el video I2V + prompt combinado de `sonic.{sfx, diegetic_sound}`.
4. **Real-ESRGAN** (solo si `post_production.upscale_with` está seteado) — upscale sobre el frame FLUX (mejor calidad que sobre el video).

**En paralelo:**

5. **Suno** (una vez, para el `metadata.hero_scene_id` o primera escena con `hero_moment=True`) — `sonic.music_brief` + `music_reference_artists`.

**Concurrencia:** `asyncio.gather` + `asyncio.Semaphore(concurrency)` limita cuántas escenas corren a la vez (default 2). Suno corre en paralelo a las escenas (es independiente).

**BudgetTracker.** Antes de cada submit a fal, reserva el costo estimado (tabla `COST_USD`). Si la suma supera `max_budget_usd`, raises `BudgetExceeded` — aborta ANTES de pagar. La tabla:

| Modelo | Costo USD aprox (2026-Q2) |
|---|---|
| flux-1.1-pro | 0.040 |
| flux-1.1-pro-ultra | 0.060 |
| flux-lora | 0.055 |
| flux-lora-train | 1.500 |
| kling-2.5-pro | 0.350 |
| runway-gen3-alpha-turbo | 0.400 |
| wan-2.1-14b | 0.100 |
| mmaudio-v2 | 0.015 |
| tts-playai | 0.030 |
| real-esrgan | 0.010 |
| rife-interp | 0.012 |
| suno | 0.000 (flat-rate Premium) |

**LoRA training.** `train_lora_if_needed()` usa `FLUX_LORA_URL` como cache. Si está vacío y se pasa `--lora-images <zip_url>`, entrena una vez con 1000 steps. El ZIP tiene que ser una URL pública — fal NO descarga del disco local.

**Atomicidad.** Escribe a `scene_plan.json.tmp` primero, `os.replace` al final. Si Python crashea o budget se excede, el JSON original no se corrompe.

**CLI:**

```
python -m bridge.asset_generator <scene_plan.json> \
  [--budget 3.00] [--concurrency 2] \
  [--no-sfx] [--no-music] \
  [--lora-images <zip_url>] [--force-train-lora] \
  [--dry-run]
```

`--dry-run` = estimación de costo sin tocar red. Útil para decidir si el budget alcanza antes de arrancar.

**Output JSON.** Cada escena recibe `resolved_assets`:

```json
{
  "type": "video",
  "phase": "i2v",
  "generator": "fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
  "url": "https://...",
  "cost_usd": 0.35,
  "elapsed_s": 47.2,
  "request_id": "abc-123"
}
```

+ `metadata.asset_generation` con started_at, finished_at, total_cost_usd, scenes_completed, lora_url, hero_music_url, etc.

---

## 8. Config, prompts, estructuras

### `config/llm_provider.yaml`

Tuning fino por expert. Siete experts mapeados:

```yaml
experts:
  clasificador:   { temperature: 0.2, max_tokens: 1024 }   # determinista
  concepto:       { temperature: 0.9, max_tokens: 2048 }   # creatividad alta
  arquitecto:     { temperature: 0.7, max_tokens: 4096 }   # balanceado
  escaletista:    { temperature: 0.7, max_tokens: 4096 }   # balanceado
  dialoguista:    { temperature: 0.85, max_tokens: 4096 }  # narrativa + diálogo
  localizador:    { temperature: 0.4, max_tokens: 512 }    # prompts técnicos cortos
  director_flow:  { temperature: 0.3, max_tokens: 2048 }   # structured output
```

Si un expert no está listado o le falta un campo, cae a los globales de `.env` (`CLAUDE_MAX_TOKENS=4096`, `CLAUDE_TEMPERATURE=0.7`).

### `config/formats.json` — 56 formatos

Organizados en nueve categorías:

- `vertical_social` (8): REEL_INSTAGRAM, TIKTOK, YOUTUBE_SHORT, STORY, etc.
- `horizontal_social` (6): IG_POST_16_9, TWITTER_VIDEO, etc.
- `streaming` (6): SERIE_NETFLIX, DOCUMENTARY, etc.
- `traditional` (5): CORTO, MEDIO, LARGO, TV_EPISODE, FILM.
- `musical` (4): VIDEOCLIP, PERFORMANCE, etc.
- `educational` (8): TUTORIAL, EXPLAINER, COURSE, etc.
- `commercial` (10): AD_SPOT, BRANDED, TESTIMONIAL, etc.
- `experimental` (5): ART_PIECE, INSTALLATION, etc.
- `gaming` (4): TRAILER, GAMEPLAY, etc.

### `config/structures.json` — 45 estructuras narrativas

Nueve familias: classic_hollywood, mythic_journey, episodic_tv, non_linear, international (kishōtenketsu, dan tian, etc.), experimental, short_form, documentary, theatre_performance.

### `prompts/` — 20 archivos .txt

Numeración estable para que el expert `XX` lea `prompts/XX_*.txt`:

| # | Archivo | Expert |
|---|---|---|
| 00 | clasificador.txt + clasificador_completo.txt | Clasificador de formato + estructura |
| 01 | concepto.txt | Generador de concepto + logline + hook |
| 02 | arquitecto.txt + {five_act,hero_journey,in_media_res,save_the_cat,simple,story_circle}.txt | Arquitecto narrativo (plantilla variable) |
| 03 | escaletista.txt | Beat sheet |
| 04 | dialoguista.txt | Dialoguista (emite también `sonic_atmosphere`) |
| 05 | veo_flow.txt | **Director técnico + Master Stack philosophy** |
| 06 | sd.txt | Prompts Stable Diffusion (legacy) |
| 07-09 | youtube_short.txt, reel_instagram.txt, tiktok.txt | Plantillas por formato |
| 10 | localizador_chile.txt | Localización contextual Chile |
| 11 | director_flow.txt | Director técnico cinematográfico |
| 12 | director_flow_json.txt + mi_experto.txt | Structured output |

### `estructuras/` + `templates/narrativas/`

Plantillas narrativas listas para que el arquitecto pueda aplicar sin reinventar. Ejemplo: `five_act.txt`, `in_media_res.txt`.

---

## 9. Observabilidad y logging

### `webapp/observability.py` (167 líneas)

Wrapper de structlog con tres decisiones:

1. **Auto-detect del formato.** Si `GUION_RUNTIME=docker` o `LOG_FORMAT=json` → JSON line-delimited (listo para Loki/Datadog/CloudWatch). Sino → consola con colores (dev local).
2. **Context vars.** `bind_pipeline_context(pipeline_id="pipe-abc-123")` propaga el `pipeline_id` a todos los logs que se emitan en ese ámbito. Mismo mecanismo para `trace_id` (por HTTP request).
3. **Flask integration.** `init_flask_logging(app)` registra hooks `before_request` / `after_request` que loguean `http_request_start` / `http_request_end` con latencia. Todos los logs dentro del request heredan `trace_id` automáticamente.

### Estructura de un log típico

En producción (JSON):

```json
{
  "timestamp": "2026-04-20T07:56:24.123Z",
  "level": "info",
  "event": "fal_dispatch_i2v",
  "logger": "webapp.integrations.fal",
  "service": "fal",
  "subject_type": "human_performance",
  "chosen_model": "kling-2.5-pro",
  "duration_s": 8,
  "pipeline_id": "pipe-abc-123",
  "trace_id": "trace-xyz-456",
  "request_id": "fal-req-def-789"
}
```

En dev (consola con colores): mismo contenido, formato legible.

### Logs críticos que Leo debería monitorear

- `fal_status` cuando status cambia (QUEUED → IN_PROGRESS → COMPLETED).
- `suno_clip_status` cuando un clip pasa por submitted → queued → streaming → complete.
- `budget_exceeded` (si aparece, alguien rompió el cap).
- `lora_cache_hit` vs `lora_train_start` — para saber si estás re-entrenando por error.
- `asset_generation_done` con `total_cost_usd` final.

---

## 10. Docker, deploy y operaciones

### `Dockerfile` multi-stage

**Etapa 1 (builder):** Python 3.14-slim + build-essential. Crea venv en `/opt/venv`, instala `requirements.txt` con pip cache vacío (wheels solo). **Etapa 2 (runtime):** solo copia `/opt/venv` y el código. Image final < 200MB.

Variables setteadas en el Dockerfile:
- `GUION_RUNTIME=docker` (activa JSON logs)
- `PYTHONDONTWRITEBYTECODE=1`
- `PYTHONUNBUFFERED=1`
- `PATH=/opt/venv/bin:$PATH`

### `docker-compose.yml`

Dos servicios:

**`guion-web`** (Flask + SocketIO):
- Build local de `./Dockerfile`.
- Port `5001:5001`.
- Volumes: `.env` (read-only), `output/`, `logs/`, `webapp/uploads/`, `prompts/` (ro), `estructuras/` (ro), `config/` (ro).
- `depends_on: suno-api: {condition: service_healthy}`.
- Healthcheck: `curl -fsS http://localhost:5001/api/health` cada 30s.

**`suno-api`** (gcui-art/suno-api side-car):
- Build de `./suno-api/` (Leo clona el repo como submódulo antes del primer `up`).
- Env: `SUNO_COOKIE` (desde `.env`), `SUNO_COOKIE_REFRESH_INTERVAL=5min`.
- Healthcheck: `wget http://localhost:3000/api/get_limit` (si responde 200, la cookie está viva).
- Restart policy: `unless-stopped`.
- No expuesto al host (comunicación interna via red bridge del compose).

### Deploy a Hetzner CX22 (pendiente)

Plan en `HANDOFF.md`:

1. SSH al VPS, `git clone` la rama.
2. `cp .env.example .env`, pegar `ANTHROPIC_API_KEY` + `FAL_API_KEY` + `SUNO_COOKIE` reales.
3. `git clone https://github.com/gcui-art/suno-api ./suno-api` (side-car).
4. `docker compose build && docker compose up -d`.
5. Caddy o Nginx + Let's Encrypt como reverse proxy en `guion.leodavidsoto.com`.
6. Monitoring via `docker compose logs -f guion-web` (JSON) + healthcheck en `/api/health`.

### Entry points shell (UX)

Scripts en la raíz que Leo usa sin entrar a Python:

- `ejecutar.sh` / `ejecutar_con_storyboard.sh` — arranca el server dev en foreground.
- `iniciar.sh` / `detener.sh` / `restart.sh` / `status.sh` / `stop.sh` — ciclo de vida dev.
- `logs.sh` — tail de logs estructurados.
- `generar_short.sh` — pipeline directo para formato short.
- `test_pipeline.sh` — smoke test end-to-end.
- `verify_selectors.sh` — verifica que los selectores frontend siguen matcheando.
- `analizar_completo.sh` — pipeline + análisis extendido.
- `sync_github.sh` / `github_setup.sh` — push/pull + setup inicial.

---

## 11. Flujo end-to-end con un ejemplo real

Reconstruyendo el run de `20260420_034929` (carpeta `output/20260420_034929/` + `OpenMontage/projects/20260420_034929-reel-de-instagram-sobre-banda-cover-3sm-una-historia-intrig/`).

**Input:** `"reel de Instagram sobre banda cover 3SM, una historia intrigante"` + 7 PNGs de referencia en `OpenMontage/3SM/`.

**Stage 1 — Clasificación** (clasificador, temp=0.2, max_tokens=1024):
- `formato=REEL_INSTAGRAM`, `estructura=SIMPLE (CON GIRO/REVELACIÓN)`, `duration_seconds=30`.
- Output: `clasificacion/resultado.txt`.

**Stage 2 — Concepto** (concepto, temp=0.9, max_tokens=2048):
- Logline: "Tres músicos veteranos se preparan para un concierto final en el sótano donde empezaron, sin saber que alguien del pasado los está observando."
- Hook: el bajista se quita los Ray-Ban — revelación visual.
- Output: `concepto/concepto.txt`.

**Stage 3 — Estructura** (arquitecto, temp=0.7):
- Aplica plantilla SIMPLE con giro. Cinco beats.
- Output: `estructura/estructura.txt`.

**Stage 4 — Escaleta** (escaletista, temp=0.7):
- Seis escenas enumeradas con markdown (`### **1. TITLE**`).
- Output: `escaleta/escaleta.txt`.
- **Gotcha:** el regex de `run_3sm_pipeline.py` solo capturaba 1 escena de 6 (Commit 7.1 fix: nuevo regex acepta markdown prefix + dedup por número).

**Stage 5 — Escenas** (dialoguista, temp=0.85, max_tokens=4096):
- Seis escenas × `escena_NNN.txt`.
- Cada escena emite también `sonic_NNN.json` con `music_brief` + `sfx` + `diegetic_sound`.

**Stage 6 — Prompts VEO** (director_flow, temp=0.3, **tool use**):
- Seis VeoPrompt JSON v2 con Master Stack completo.
- Cada uno: `visual_anchor` + `camera` + `motion_intent` + `sonic` + `post_production`.
- `subject_type` rango: `human_performance` (5/6), `vfx_heavy` (1/6).
- `chosen_video_model`: las 6 resuelven a `kling-2.5-pro` por la tabla de routing.

**Stage 7 — Bridge a OpenMontage:**
- Genera `brief.json`, `script.json`, `scene_plan.json`, `checkpoint.json`, `remotion-cuts.json`.
- `scene_plan.metadata.master_stack_coverage = 1.0` (6/6 scenes con master_stack).
- `metadata.hero_scene_id = "scene-004"` (heurística: hero = índice 3 de 6, momento de clímax).
- Duración total: 52.5s (sobre el target de 30s — recortable en edit-director).

**Stage 8 — AGENT_PROMPT.md** (generado manualmente esta sesión, no automático todavía):
- Instrucciones para el agente OpenMontage: entrenar LoRA una vez con trigger `3SM_BAND`, paralelizar FLUX+I2V por escena, Suno para hero, mmaudio SFX, editar a 30s priorizando `hero_moment=true`, renderizar 9:16 con Remotion, budget USD 3.00.

**Stage 9 — `bridge/asset_generator.py` (pendiente):**
```
python -m bridge.asset_generator \
    OpenMontage/projects/.../stages/scene_plan.json \
    --budget 3.00 --concurrency 2
```
Costo estimado (dry-run): **$2.52** (6 × [FLUX + Kling + mmaudio]). Sin Suno porque ya está en flat-rate. Sin LoRA training porque asumimos `FLUX_LORA_URL` cacheado.

**Stage 10 — Render final (OpenMontage):**
- El agente OpenMontage lee `scene_plan.json` con `resolved_assets` poblado.
- Remotion compone las escenas según `remotion-cuts.json` (timeline + fades).
- FFmpeg mixa audio Suno + SFX mmaudio + voiceover (si aplica).
- Output: `MP4 9:16 30s` en `OpenMontage/projects/<slug>/renders/`.

---

## 12. Historia de commits

Branch `feature/llm-provider-unified` — 12 commits ahead de `main`:

| SHA | Título | Qué introdujo |
|---|---|---|
| `3b44d7b` | feat: migrate pipeline to Claude Haiku 4.5 + add OpenMontage bridge | Commit 1: switch a Anthropic, primera versión del bridge |
| `c905774` | feat: fail-fast config with pydantic-settings | Commit 2: `webapp/config.py` con validación al boot |
| `1864ef6` | feat: structured logging with structlog (pipeline_id + trace_id) | Commit 3: `observability.py` + integración Flask |
| `8185b32` | feat: containerize with multi-stage Dockerfile + docker-compose | Commit 4: Dockerfile + compose con `guion-web` |
| `c77605f` | feat: per-expert LLM config via YAML | Commit 5-6: `llm_provider.yaml` + `settings.params_for()` |
| `0cde548` | feat(master-stack): schemas cinematográficos + tool use + bridge v2 | Commit 7: `webapp/schemas/cinematic.py` + generate_structured + bridge v2 |
| `5a69a86` | fix(bridge): handle textures as list in _synthesize_flux_prompt | Commit 7.1: fix bug descubierto en run end-to-end |
| `0e2c20f` | feat(integrations): BaseHTTPClient + .env.example expandido | Commit 8: cliente HTTP base + env template |
| `0c6091e` | feat(integrations/fal): FalClient unified — FLUX/Kling/Runway/WAN/mmaudio/ESRGAN/TTS | Commit 9: cliente fal.ai con 11 modelos |
| `43570f6` | feat(integrations/suno): SunoClient self-hosted + docker-compose side-car | Commit 10: cliente Suno + servicio Docker |
| `6dfaf86` | feat(bridge/asset_generator): orquestador FLUX → I2V → mmaudio → Suno | Commit 11: orquestador async end-to-end |
| `c64a37c` | fix(openmontage): normalize format mapping and correct I2V cost routing | Fix post-11 al bridge (normalización de formatos y costo I2V) |

**Commits previos a la migración** (en `main`, antes de la rama):
- `f69cdf6` feat: Auto Flow integration (JSON export)
- `286a43c` feat: Click on projects to open folder
- `9598375` feat: Clickable narrative structures
- `8648205`, `84bd693`, `97d0988`, `29897ff`, `c720070` — commits iniciales del proyecto.

**Convención de commit messages.** Conventional Commits (`feat:`, `fix:`, `refactor:`, etc.) con scope entre paréntesis. Mensaje largo (3+ párrafos) en español rioplatense. Cada commit co-authored con Claude:

```
Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## 13. Deuda técnica y riesgos conocidos

### Deuda técnica

**1. No hay tests automatizados.** La verificación es `py_compile` + smoke tests manuales. Para producción real deberíamos agregar al menos:
- `pytest` con fixtures para los schemas Pydantic.
- Mocks de `FalClient` y `SunoClient` con `respx` (httpx test adapter).
- Test end-to-end del bridge con un proyecto fixture.
- CI en GitHub Actions.

**2. Prompts modificados sin commitear.** `git status` muestra ~15 archivos en `prompts/` editados localmente que nunca fueron landeados. Hay que revisar qué cambios son legítimos (iteración de Leo) vs stale.

**3. Legacy Ollama.** `config/models.conf` + código en `llm_provider.py::_generate_ollama()` siguen vivos. Baja prioridad pero eventualmente borrar o dejar muy claramente marcado como fallback-only.

**4. `output/` tiene 16+ runs acumulados.** Algunos son smoke tests, otros son runs reales. Convendría un `scripts/cleanup_output.sh --older-than 30d`.

**5. `analyzer/` tiene outputs de pre-migración.** Archivos de 2025-12-01 sin uso claro. Probablemente borrable.

**6. Duración del pipeline total a 30s.** El ejemplo real produjo 52.5s para un target de 30s. Falta un stage "edit-director" que priorice escenas `hero_moment=true` y recorte el resto para cumplir la duración solicitada. Hoy eso se delega al agente OpenMontage via el AGENT_PROMPT.md — convendría formalizarlo.

**7. LoRA training manual.** `asset_generator.py` soporta entrenar LoRA pero requiere que Leo suba manualmente un ZIP a algún host público (Cloudflare R2, S3, o similar). Un helper `FalClient.upload_file()` usando el endpoint de fal.ai storage cerraría este loop — está en el roadmap.

**8. No hay rate limiting del lado de Guion_expert.** Si Leo dispara 5 pipelines en paralelo desde el frontend, hay 5 threads pegándole a Anthropic simultáneamente. Anthropic tiene tier de rate limiting pero conviene un semáforo global en `llm_provider.generate()`.

### Riesgos

**1. Cookie de Suno expira cada ~24h.** Si Leo no renueva antes del reel de la mañana, el pipeline falla con 401/403. Mitigación: health check + alerta antes del run. Medida drástica: pasar a una cuenta dedicada con renovación programada.

**2. fal.ai cambia precios.** La tabla `COST_USD` está hardcoded (2026-Q2 snapshot). Si fal sube precios y no actualizamos, el BudgetTracker sub-estima y Leo gasta más. Monitoreo trimestral manual.

**3. Anthropic deprecation de Haiku 4.5.** Inevitable. `claude-haiku-4-5-20251001` tiene fecha de sunset. Cuando pase, `CLAUDE_MODEL` en `.env` se actualiza sin tocar código.

**4. Docker compose depends_on no garantiza que suno-api tenga cookie válida.** Solo verifica que responda en `/api/get_limit`. Si la cookie está vieja pero el servicio responde, `guion-web` arranca igual y falla al primer request. Considerar healthcheck con test de generación real.

**5. `FAL_API_KEY` + `SUNO_COOKIE` en `.env` mount read-only en el container.** Si alguien con shell access al VPS hace `cat /app/.env`, las keys quedan expuestas. Mejor: Docker Secrets o Vault. Baja prioridad mientras sea un solo user.

**6. `webapp/schemas/cinematic.py` es el contrato con Anthropic.** Cualquier edit invalidante (renombrar un enum, cambiar un required field) rompe inmediatamente `generate_structured()`. Tests del schema + roundtrip (ejemplo → Pydantic → JSON → Pydantic) serían baratos y salvan horas de debugging.

**7. Bridge depende del layout exacto de `output/<timestamp>/`.** Si `pipeline_claude.py` renombra una carpeta, el bridge revienta. Acoplamiento informal, no validado en tests.

---

## 14. Roadmap inmediato

### Antes del PR a `main`

- [ ] Commitear los cambios pendientes en `prompts/*` (revisar qué es real vs stale).
- [ ] Dry-run del asset_generator sobre el scene_plan de `20260420_034929` para validar costos y routing.
- [ ] End-to-end con keys reales de 1-2 escenas (no el reel completo) para humear el loop.
- [ ] `CHANGELOG.md` final con sección `[2.1.0]` cerrada y `## Released: 2026-04-21`.
- [ ] PR description con sumario de los 11 commits + link al scene_plan real + captura de un video generado.

### Deploy a Hetzner CX22

- [ ] Crear VPS CX22 (Ubuntu 22.04), SSH key en `~/.ssh/authorized_keys`.
- [ ] `git clone` la rama + `git clone gcui-art/suno-api`.
- [ ] `.env` con keys reales.
- [ ] `docker compose up -d`, verificar `/api/health` responde.
- [ ] Caddyfile o nginx + certbot para HTTPS en subdominio.
- [ ] Smoke test: generar un reel completo desde el frontend remoto.

### Siguiente sprint (post-deploy)

1. **Tests automatizados.** `pytest` + `respx` + fixtures. CI en GH Actions.
2. **Edit-director stage.** Que respete `duration_target` recortando escenas no-hero.
3. **FalClient.upload_file()** — cerrar el loop de LoRA training (no más upload manual).
4. **Rate limiting del pipeline global.** Semáforo en `llm_provider.generate()`.
5. **Cookie refresh automation para Suno.** O al menos un script `scripts/check_suno_cookie.sh` que corra daily y alertee antes de que expire.
6. **Dashboard básico.** Página en `/api/dashboard` con últimos 10 pipelines, costos totales del mes, status de integraciones.
7. **Cleanup scripts.** `output/`, `analyzer/`, logs viejos.

---

## 15. Apéndices

### A. Variables de entorno (todas)

Ver `.env.example` para el template canónico con comentarios. Agrupadas:

**LLM:** `LLM_PROVIDER`, `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, `CLAUDE_MAX_TOKENS`, `CLAUDE_TEMPERATURE`, `OLLAMA_HOST`.

**Servidor:** `WEBAPP_HOST`, `WEBAPP_PORT`, `FLASK_SECRET_KEY`, `LOG_LEVEL`.

**fal.ai:** `FAL_API_KEY`, `FAL_BASE_URL`, `FLUX_LORA_TRIGGER`, `FLUX_LORA_URL`, `FLUX_MODEL`, `FLUX_STEPS`, `FLUX_GUIDANCE`, `FLUX_IMAGE_SIZE`, `I2V_DEFAULT_MODEL`, `I2V_DEFAULT_DURATION_S`, `REAL_ESRGAN_SCALE`, `RIFE_TARGET_FPS`.

**Suno:** `SUNO_COOKIE`, `SUNO_API_URL`, `SUNO_MODEL`, `SUNO_POLL_INTERVAL_S`, `SUNO_POLL_MAX_WAIT_S`, `SUNO_DEFAULT_INSTRUMENTAL`.

**OpenMontage:** `OPENMONTAGE_ROOT`.

**HTTP:** `HTTP_TIMEOUT_CONNECT`, `HTTP_TIMEOUT_READ`, `HTTP_MAX_RETRIES`, `HTTP_BACKOFF_BASE`.

**Observability:** `LOG_FORMAT`, `SENTRY_DSN`.

**Limits:** `MAX_SCENES_PER_PROJECT`, `MAX_BUDGET_USD`.

### B. IDs oficiales de fal.ai (copy-paste al actualizar)

```python
FAL_MODEL_IDS = {
    "flux-1.1-pro":           "fal-ai/flux-pro/v1.1",
    "flux-1.1-pro-ultra":     "fal-ai/flux-pro/v1.1-ultra",
    "flux-lora":              "fal-ai/flux-lora",
    "flux-lora-train":        "fal-ai/flux-lora-fast-training",
    "kling-2.5-pro":          "fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
    "runway-gen3-alpha-turbo":"fal-ai/runway-gen3/turbo/image-to-video",
    "wan-2.1-14b":            "fal-ai/wan-pro/v2.1-14b/image-to-video",
    "mmaudio-v2":             "fal-ai/mmaudio-v2",
    "tts-playai":             "fal-ai/playai/tts/v3",
    "real-esrgan":            "fal-ai/real-esrgan",
    "rife-interp":            "fal-ai/rife-interpolation",
}
```

Verificables en `https://fal.ai/models`. Al actualizar, revisar también `COST_USD` en `bridge/asset_generator.py`.

### C. Comandos rápidos de referencia

```bash
# Dev local sin Docker
source venv/bin/activate
cd webapp && python server.py

# Con Docker (prod-like)
docker compose build && docker compose up -d
docker compose logs -f guion-web

# Smoke tests
python -m py_compile webapp/schemas/*.py webapp/llm_provider.py \
    webapp/pipeline_claude.py bridge/openmontage_export.py \
    bridge/asset_generator.py webapp/integrations/*.py

# Pipeline desde CLI (sin frontend)
python -c "
from webapp.pipeline_claude import run_full_pipeline
from pathlib import Path
run_full_pipeline(
    idea='reel sobre AI generativa',
    formato='REEL_INSTAGRAM',
    project_dir=Path('output/test_cli'),
)"

# Bridge a OpenMontage
python -c "
from bridge import export_project_to_openmontage
from pathlib import Path
export_project_to_openmontage(
    project_dir=Path('output/20260420_034929'),
    openmontage_root=Path('/Users/leo/Desktop/ESCRIBE/OpenMontage'),
    idea='reel de Instagram sobre banda 3SM',
)"

# Asset generator (cuando las keys estén listas)
python -m bridge.asset_generator \
    OpenMontage/projects/20260420_034929-.../stages/scene_plan.json \
    --budget 3.00 --concurrency 2 --dry-run

# Ver estructura de un scene_plan
python3 -c "
import json
p = json.load(open('.../stages/scene_plan.json'))
print('top:', list(p.keys()))
print('scenes:', len(p['scenes']))
print('hero:', p['metadata']['hero_scene_id'])
print('coverage:', p['metadata']['master_stack_coverage'])"

# Validar integraciones offline (stubs)
python3 -m py_compile webapp/integrations/*.py bridge/asset_generator.py
```

### D. Stack tecnológico

**Runtime:** Python 3.14, Flask 3.x, SocketIO (eventlet/gevent via flask-socketio).

**LLM:** Anthropic SDK `>=0.40.0`. Modelo default: `claude-haiku-4-5-20251001`.

**HTTP:** httpx `>=0.27.0` (sync + async), usado por BaseHTTPClient.

**Validación:** Pydantic v2 + pydantic-settings `>=2.2.0`.

**Logging:** structlog `>=24.1.0`.

**Generativa (externos):**
- **fal.ai** — FLUX.1 Pro, Kling 2.5 Pro, Runway Gen-3, WAN 2.1 14B, mmaudio v2, Real-ESRGAN, RIFE, PlayAI TTS.
- **Suno** (self-hosted vía `gcui-art/suno-api`) — música original.

**Downstream:**
- **OpenMontage** (repo hermano) — Remotion + FFmpeg para render final.

**Deploy:** Docker + docker-compose. Target: Hetzner CX22 (Ubuntu 22.04, 4GB RAM, 2 vCPU). Reverse proxy: Caddy o Nginx + Let's Encrypt.

### E. Glosario

- **Master Stack v2** — Convención interna para referirse al bloque `scene["master_stack"]` con los cinco sub-bloques `visual_anchor`, `camera`, `motion_intent`, `sonic`, `post_production`.
- **VeoPrompt** — Instancia de `webapp.schemas.cinematic.VeoPrompt`. El output estructurado del director_flow.
- **Hero scene** — La escena que concentra el clímax visual/narrativo. Determinada por `master_stack.narrative_beat ∈ {climax, revelation}` o por `hero_moment=true`.
- **Playbook** — Style preset de OpenMontage (`neo_noir`, `wes_anderson`, `kinoeye`, etc.). Elegido por el bridge según formato + estilo_visual.
- **Trigger word** — Token mágico que activa un LoRA de identidad (`3SM_BAND` en nuestro caso). Se prepend al prompt FLUX.
- **Sonic atmosphere** — Bloque `master_stack.sonic` con brief de Suno, SFX de mmaudio, silencios narrativos.
- **Dispatch I2V** — Acto de elegir Kling/Runway/WAN según `subject_type`. Función `FalClient.dispatch_i2v()`.
- **Bridge** — Código que traduce artefactos entre sistemas sin invocar LLMs. `bridge/openmontage_export.py` es el bridge canónico.

---

*Documento generado 2026-04-20 durante la sesión de hardening pre-deploy. Para retomar el trabajo, leé `HANDOFF.md` primero.*
