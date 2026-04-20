# HANDOFF — Continuación de Sesión

> Documento canónico para retomar el trabajo en curso.
> Última actualización: **2026-04-20** · Branch activo: `feature/llm-provider-unified`

---

## Estado Actual (resumen ejecutivo)

Estamos hardenando `Guion_expert` para deploy en **Hetzner CX22 (VPS)** y migrando la generación a **Claude Haiku 4.5** (`claude-haiku-4-5-20251001`). El pipeline ahora incluye integración con **fal.ai** (FLUX, Kling, Runway, WAN, Real-ESRGAN) y **Suno** (self-hosted vía `gcui-art/suno-api`) para cerrar el loop guion → video con música original.

El trabajo está secuenciado como commits atómicos sobre la rama `feature/llm-provider-unified`. Van **7 commits landeados** y quedan **4 más + PR a main + deploy**.

---

## Arquitectura objetivo

```
┌────────────────┐    ┌──────────────┐    ┌─────────────────────┐
│ Guion_expert   │───►│ scene_plan   │───►│ OpenMontage         │
│ (Claude Haiku  │    │ master_stack │    │ (fal.ai + Suno +    │
│  + tool use)   │    │ v2 JSON      │    │  Remotion + FFmpeg) │
└────────────────┘    └──────────────┘    └─────────────────────┘
        │                                          ▲
        │ atmósfera sonora                         │
        ▼                                          │
   Suno (self-hosted) ────────────────────────────┘
```

### Pipeline de 3 Fases (Master Stack)

**Fase 1 — Ancla Visual (FLUX.1 Pro vía fal.ai)**
El generador de imagen crea el frame 0 con composición, paleta, lighting y texturas cinematográficas. El video I2V hereda esa calidad.

**Fase 2 — Inyección de Movimiento (I2V routing determinístico)**
- `human_gesture` / `human_performance` / `creature_animal` / `vfx_heavy` → **Kling 2.5 Pro**
- `landscape_static` / `landscape_dynamic` / `drone_sweep` → **Runway Gen-3**
- `subtle_slow_camera` / `object_reveal` → **WAN 2.1 (14B)**

**Fase 3 — Post-producción**
RIFE (interpolación slow-mo) + Real-ESRGAN vía fal.ai (o Topaz local) para upscale a 4K en escenas clave.

---

## Commits Landeados (rama `feature/llm-provider-unified`)

| # | SHA | Título |
|---|-----|--------|
| 1 | `3b44d7b` | feat: migrate pipeline to Claude Haiku 4.5 + add OpenMontage bridge |
| 2 | `c905774` | feat: fail-fast config with pydantic-settings |
| 3 | `1864ef6` | feat: structured logging with structlog (pipeline_id + trace_id) |
| 4 | `8185b32` | feat: containerize with multi-stage Dockerfile + docker-compose |
| 6 | `c77605f` | feat: per-expert LLM config via YAML |
| 7 | `0cde548` | **feat(master-stack): schemas cinematográficos + tool use + bridge v2** |

*(Commit 5 se consolidó dentro del 6; numeración original se mantiene para trazabilidad.)*

---

## Qué hace cada pieza del Master Stack

### `webapp/schemas/cinematic.py` (NUEVO, Commit 7)

Schemas Pydantic v2 con `Literal` types — el input_schema se pasa directo a Anthropic tool use:

- `CameraPhysics`: shot_type (12 opts), movement (15 opts), lens_mm (14/24/35/50/85/135/200), duration_seconds (1-15s).
- `VisualAnchor`: composition, palette (1-6), lighting, textures, style (11 opts), subject_description, environment.
- `MotionIntent`: subject_type (9 opts), action, motion_intensity (low/med/high), physics_notes.
- `SonicAtmosphere`: mood (1-5), music_brief (prompt Suno), music_reference_artists, sfx, diegetic_sound, silence_moments.
- `PostProduction`: target_fps (24/30/60), target_resolution (1080p/4k), upscale_with (real_esrgan/topaz/none), fps_interpolation (rife/none).
- `VeoPrompt`: scene_id (`^scene-\d{3}$`), scene_number, narrative_beat (9 opts) + los 5 bloques arriba + text_on_screen, director_notes + método `chosen_video_model()`.

`VIDEO_MODEL_ROUTING: dict[str, str]` es la tabla de routing subject_type → modelo I2V.

### `webapp/llm_provider.py` (EDITADO, Commit 7)

Agregada función `generate_structured(prompt, tool_name, tool_description, input_schema, role, system_prompt) -> dict` que fuerza Anthropic tool use (`tool_choice={"type":"tool", "name":...}`). **Fail-fast**: si Claude no invoca la tool, raise RuntimeError (no fallback silencioso).

### `webapp/pipeline_claude.py` (EDITADO, Commit 7)

`_stage_prompts_veo` reescrita: usa `generate_structured()`, valida con `VeoPrompt.model_validate()`, loguea `chosen_video_model` al cliente via SocketIO con shot_type·movement·chosen_model.

### `bridge/openmontage_export.py` (EDITADO, Commit 7)

- `VIDEO_MODEL_ROUTING` duplicado intencionalmente (espejo de `webapp/schemas/cinematic.py`) — desacopla el bridge de webapp/.
- `_normalize_veo()` detecta v2 por presencia de `{visual_anchor, motion_intent, camera}` y delega a `_normalize_master_stack()`.
- `_normalize_master_stack()` mapea el schema v2 al dict canónico + passthroughs con prefijo `_` (`_camera`, `_visual_anchor`, `_motion_intent`, `_sonic`, `_post`, `_chosen_video_model`, `_scene_id`, `_narrative_beat`).
- `_synthesize_flux_prompt()` sintetiza el prompt denso para FLUX.1 Pro (composición + paleta + lighting + texturas + style + acción).
- `_build_scene_plan()` emite bloque `scene.master_stack` con las 3 fases completas + sonic + enriquece `required_assets` con `generator_hint` (`flux-1.1-pro` para imagen, `chosen_video_model` para video).
- `CAMERA_MOVEMENT_SYNONYMS` acepta variantes underscore (match directo con el Literal del schema).

**Retrocompatibilidad**: los formatos legacy (nested + flat) siguen funcionando sin tocar.

### `prompts/04_dialoguista.txt` (EDITADO, Commit 7)

Agregado bloque mandatorio al final de cada escena:

```
=== ATMÓSFERA SONORA ===
MOOD: 2-4 keywords emocionales
MÚSICA: prompt denso para Suno (género, instrumentación, BPM, tonalidad, dinámica)
REFERENCIAS: 1-3 artistas/scores
SFX: 3-5 efectos diegéticos concretos
DIÉGESIS: sonido del mundo
SILENCIO: momentos donde el silencio narra
=== FIN ATMÓSFERA ===
```

El sound designer está **baked-in** al dialoguista (Opción A) — no hay expert separado.

### `prompts/05_veo_flow.txt` (REESCRITO, Commit 7)

Sin JSON inline (la tool maneja el schema). Prompt puro de criterio cinematográfico:
- Filosofía Master Stack (3 fases)
- Reglas de routing por `subject_type`
- Criterios para cada bloque (camera, visual_anchor, motion_intent, sonic, post)
- 6 reglas críticas

---

## Configuración per-expert (Commit 6)

`config/llm_provider.yaml` define temperature/max_tokens por expert:

| expert | temperature | max_tokens |
|--------|------------|------------|
| clasificador | 0.2 | 1024 |
| concepto | 0.9 | 2048 |
| arquitecto | 0.7 | 4096 |
| escaletista | 0.7 | 4096 |
| dialoguista | 0.85 | 4096 |
| localizador | 0.4 | 512 |
| director_flow | 0.3 | 1024 |

Consumido en `webapp/config.py::Settings.params_for(role)` → `llm_provider.generate(..., role=...)`.

---

## Commits Pendientes (Roadmap)

### ✅ Commit 7.1 — fixes del run end-to-end (pending commit)
- `bridge/openmontage_export.py::_synthesize_flux_prompt` — `textures`
  ahora acepta `list[str]` (schema correcto).
- `tmp/run_3sm_pipeline.py` — regex de escaleta acepta markdown headers.
- `OpenMontage/schemas/artifacts/scene_plan.schema.json` — incluye
  `master_stack` y `generator_hint`.

### ✅ Commit 8 — `.env.example` + integraciones base (pending commit)
- `.env.example` expandido (LLM + Flask + fal + Suno + OpenMontage + HTTP +
  observability + budget caps).
- `webapp/integrations/__init__.py` + `webapp/integrations/base.py` con
  `BaseHTTPClient` (sync + async, retries exponenciales, rate-limit
  respetado, structlog, excepciones tipadas).
- `webapp/config.py` ahora tiene `http_timeout_connect`, `http_timeout_read`,
  `http_max_retries`, `http_backoff_base`.
- `httpx>=0.27.0` en requirements.
- Smoke: py_compile OK, AST check verifica los 26 métodos de BaseHTTPClient.

### ✅ Commit 9 — `webapp/integrations/fal.py` (pending commit)
`FalClient` unified con queue-based API, sync + async parity (38 métodos).
- **FLUX**: `flux_generate`, `flux_lora_train` (con trigger_word + safetensors out).
- **I2V**: `kling_i2v`, `runway_i2v`, `wan_i2v` con payload-builders específicos
  por modelo.
- **Routing**: `dispatch_i2v(subject_type, image_url, prompt, duration_s)` usa
  `VIDEO_MODEL_ROUTING` del schema canónico.
- **Audio/post**: `mmaudio`, `real_esrgan`, `rife_interpolate`, `tts`.
- **`FalJobResult.first_url()`** — extractor robusto cubriendo 7 response
  patterns.
- **Excepciones**: `FalJobFailed`, `FalJobTimeout`.
- Alineación verificada: todos los values de `VIDEO_MODEL_ROUTING` están en
  `FAL_MODEL_IDS` keys.

### ✅ Commit 10 — `webapp/integrations/suno.py` + compose suno-api (pending commit)
`SunoClient` auth via cookie (no Bearer), 13 sync + 6 async methods.
- Endpoints: `/api/custom_generate`, `/api/generate`, `/api/get`,
  `/api/get_limit`.
- `generate_song()` → submit + poll + `select_best()` (variante con mayor
  duration_s). Poll cap 10min, intervalo 5s default.
- `SunoClip` dataclass con `is_complete`/`is_streaming`/`is_failed`.
  `from_api()` tolera 3 formatos de response de gcui-art/suno-api.
- Excepciones: `SunoClipFailed`, `SunoTimeout`.
- `docker-compose.yml` con servicio `suno-api` buildeado desde `./suno-api/`
  (user clona gcui-art/suno-api como side-car antes del primer `up`).
  Healthcheck `wget /api/get_limit`. `guion-web.depends_on` = suno-api
  healthy.
- Config: `suno_cookie` (SecretStr), `suno_api_url`, `suno_model`,
  `suno_poll_interval_s`, `suno_poll_max_wait_s`,
  `suno_default_instrumental`.

### Commit 11 — `bridge/asset_generator.py` (orquestador)
Script que consume `scene_plan.json` (con `master_stack` block) y dispara en paralelo:
- Para cada escena: FLUX (Fase 1) → I2V elegido por routing (Fase 2) → mmaudio SFX → Real-ESRGAN si `upscale_with=real_esrgan` (Fase 3).
- Para toda la película: Suno (música desde `sonic.music_brief`) → crossfade + mix según `silence_moments`.
- Escribe todos los URLs de assets de vuelta al `scene_plan.json` en el campo `resolved_assets`.

### Deploy Final
1. PR `feature/llm-provider-unified` → `main`.
2. `docker compose build && docker compose up -d` en Hetzner CX22 (Ubuntu 22.04).
3. Nginx + Let's Encrypt (certbot) como reverse proxy.
4. Monitoring básico con `docker compose logs -f` + healthcheck en `/api/health`.

---

## Cómo retomar en una nueva sesión

En la próxima sesión de Claude Code / Cowork, empezar con:

> "Leí `HANDOFF.md`. Vamos con **Commit 11** — `bridge/asset_generator.py`, el orquestador que consume `scene_plan.json` con `master_stack` y dispara FLUX LoRA training (una vez) + FLUX+I2V por escena (paralelo con asyncio.gather) + Suno música + mmaudio SFX + Real-ESRGAN si `upscale_with` está seteado. Escribe `resolved_assets` de vuelta al scene_plan."

La sesión nueva debe:
1. Leer `HANDOFF.md`, `CLAUDE.md`, `CHANGELOG.md`.
2. Confirmar con `git log --oneline -10` que los últimos commits están en la rama (7, 7.1, 8, 9, 10).
3. Leer `webapp/integrations/fal.py` (queue pattern) + `webapp/integrations/suno.py` (cookie + poll pattern) como referencia.
4. Proceder con Commit 11. El bridge sigue siendo **sin LLM calls** — es puro I/O + orquestación.

---

## Smoke Tests que Deben Pasar

```bash
# 1. Py_compile de los módulos core
python -m py_compile webapp/schemas/cinematic.py webapp/schemas/__init__.py webapp/llm_provider.py webapp/pipeline_claude.py bridge/openmontage_export.py

# 2. Schema roundtrip (requiere pydantic instalado)
python -c "
import sys; sys.path.insert(0, 'webapp')
from schemas.cinematic import VeoPrompt, choose_video_model
print('routing OK:', choose_video_model('human_performance'))  # → kling-2.5-pro
"

# 3. Bridge end-to-end (solo stdlib)
python -c "
import sys; sys.path.insert(0, '.')
from bridge.openmontage_export import _build_scene_plan, _normalize_veo
# … ver bloque de tests en bridge/openmontage_export.py
"

# 4. Docker build
docker compose build
```

---

## Archivos de Contexto Clave

- `HANDOFF.md` — este doc.
- `CLAUDE.md` — auto-cargado por Claude Code/Cowork al entrar al repo.
- `CHANGELOG.md` — log detallado de cada commit.
- `config/llm_provider.yaml` — per-expert tuning.
- `prompts/04_dialoguista.txt` — define el bloque sonoro que alimenta Suno.
- `prompts/05_veo_flow.txt` — define cómo el director_flow razona sobre el Master Stack.
- `webapp/schemas/cinematic.py` — source of truth del schema v2.
- `bridge/openmontage_export.py` — puente a OpenMontage con passthrough Master Stack.

---

## Riesgos / Cosas a Vigilar

1. **Pydantic instalado**: El schema requiere `pydantic>=2.0`. Ya está en `requirements.txt`. El sandbox de Cowork a veces no tiene PyPI — los tests críticos se corren en Docker.
2. **fal.ai rate limits**: Cuenta con backoff exponencial en `integrations/base.py` (Commit 8).
3. **Suno cookie rota**: `SUNO_COOKIE` expira — el healthcheck del servicio debe detectarlo y alertar.
4. **Routing table sync**: La duplicación de `VIDEO_MODEL_ROUTING` entre `webapp/schemas/cinematic.py` y `bridge/openmontage_export.py` es intencional, pero si se agrega un subject_type hay que updatear ambos.
5. **Tool use truncation**: Si `max_tokens` del expert `director_flow` (1024) queda corto, Claude trunca antes del `tool_use` y `generate_structured()` raise. Subir en `config/llm_provider.yaml` si se ve.
