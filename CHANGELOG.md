# Changelog

## [2.1.0-dev] — Branch `feature/llm-provider-unified`

Migración a **Claude Haiku 4.5** y hardening para producción en Hetzner CX22.
Ver `HANDOFF.md` para contexto completo.

### Commit 9 — `pending` (2026-04-20)
**feat(integrations/fal): FalClient unified para FLUX/Kling/Runway/WAN/mmaudio/ESRGAN/TTS**

- **`webapp/integrations/fal.py`** — un solo cliente para toda fal.ai,
  heredando de `BaseHTTPClient`. 38 métodos (sync + async parity).
  - **Queue-based API**: `submit()` → `poll_until_complete()` → `FalJobResult`.
    Poll con interval configurable, timeout cap 15min default (20min para
    LoRA training).
  - **`FalJobResult.first_url()`** — extractor robusto de URL del payload,
    cubre los 7 patterns de fal (flux/kling/runway/wan/mmaudio/esrgan/
    lora-training/tts).
  - **Excepciones**: `FalJobFailed` (status=FAILED), `FalJobTimeout`
    (excedió cap).
- **Modelos cubiertos** (11 en `FAL_MODEL_IDS`):
  - Imagen: flux-1.1-pro, flux-1.1-pro-ultra, flux-lora, flux-lora-train
  - I2V: kling-2.5-pro, runway-gen3-alpha-turbo, wan-2.1-14b
  - Audio: mmaudio-v2, tts-playai
  - Post: real-esrgan, rife-interp
- **Routing determinístico** — `dispatch_i2v(subject_type=..., image_url=...,
  prompt=..., duration_s=...)` lee `VIDEO_MODEL_ROUTING` del schema canónico
  y dispara el modelo correcto. Alineación verificada entre `FAL_MODEL_IDS`
  keys y `VIDEO_MODEL_ROUTING` values.
- **FLUX LoRA training** — `flux_lora_train(images_data_url, trigger_word,
  steps=1000)` para identity LoRA (3SM_BAND). Devuelve safetensors URL que
  queda en `resolved_assets` del scene_plan.
- **Payload builders** separados (`_kling_payload`, `_runway_payload`,
  `_wan_payload`) — cada modelo tiene su shape particular (Kling: duration
  "5"/"10" + aspect_ratio, Runway: ratio + duration, WAN: num_frames).
  Vertical 9:16 hardcoded para reels.
- **Config**: agregados `fal_api_key` (SecretStr), `fal_base_url`,
  `fal_poll_interval_s`, `fal_poll_max_wait_s`, `flux_lora_trigger`,
  `flux_lora_url`, `flux_model`, `flux_steps`, `flux_guidance`,
  `flux_image_size`, `i2v_default_model`, `i2v_default_duration_s`,
  `real_esrgan_scale`, `rife_target_fps`.
- Smoke: py_compile + AST check verifica 25 sync + 13 async methods.

### Commit 8 — `pending` (2026-04-20)
**feat(integrations): BaseHTTPClient + .env.example expandido**

- **`webapp/integrations/base.py`** — cliente HTTP compartido para todos
  los servicios externos (fal.ai, Suno, mmaudio). Features:
  - Sync + async (`request()` / `arequest()`) — asset_generator podrá
    paralelizar FLUX/I2V/Suno con `asyncio.gather`.
  - **Retries** exponenciales en 5xx/429/connect errors (cap 60s).
  - **Rate limit** — respeta `Retry-After` del header 429.
  - **Timeouts** separados connect/read (I2V puede tardar minutos).
  - **Structlog** con `service` + `attempt` + `elapsed_s` por request.
  - **Excepciones tipadas**: `HTTPClientError` (4xx no-retryable, bubble
    up), `RetryableError` (5xx/transport), `RateLimitError` (429).
  - Subclase debe implementar `_auth_headers()` — fail-fast si no.
- **`webapp/integrations/__init__.py`** — exporta el API público.
- **`.env.example` expandido** — cubre LLM + Flask + fal.ai + Suno +
  OpenMontage + HTTP + observability + budget caps.
- **`webapp/config.py`** — agregados `http_timeout_connect`,
  `http_timeout_read`, `http_max_retries`, `http_backoff_base`.
- **`requirements.txt`** — `httpx>=0.27.0`.
- Smoke test: `py_compile` OK + AST check sobre las 26 métodos de
  `BaseHTTPClient` (sync + async variants de `request/get/post/put/delete`).

### Commit 7.1 — `pending` (2026-04-20)
**fix(bridge): textures as list, escaleta regex, scene_plan schema**

Bugs descubiertos durante el primer run end-to-end del reel 3SM:

- **`bridge/openmontage_export.py::_synthesize_flux_prompt`** — `textures`
  se trataba como `str` pero el schema Pydantic lo tiene como `list[str]`.
  Ahora maneja ambos formatos.
- **`tmp/run_3sm_pipeline.py`** — regex de parseo de escaleta sólo
  matcheaba `"1."` al inicio de línea; Claude Haiku emite markdown
  `### **1. TÍTULO**`. Nueva regex acepta `#+`, `*+`, dedupe por número,
  cap a 6 escenas.
- **`OpenMontage/schemas/artifacts/scene_plan.schema.json`** — agregados
  `master_stack` (object, additionalProperties:true) y `generator_hint`
  al schema para que el JSON del bridge v2 valide sin warnings.

Resultado: run end-to-end 3SM con Character Bible, 6 escenas, Master
Stack coverage 1.0, 52.5s totales, 0 warnings.

### Commit 7 — `0cde548` (2026-04-20)
**feat(master-stack): schemas cinematográficos + tool use + bridge v2**

- **Fase 1 (FLUX.1 Pro vía fal.ai)** — `VisualAnchor` define composición,
  paleta, lighting, texturas y estilo. Bridge sintetiza el prompt denso
  determinísticamente.
- **Fase 2 (routing I2V determinístico)** — `VIDEO_MODEL_ROUTING` mapea
  `subject_type` → modelo:
  - human_* / creature_animal / vfx_heavy → **Kling 2.5 Pro**
  - landscape_* / drone_sweep → **Runway Gen-3**
  - subtle_slow_camera / object_reveal → **WAN 2.1 (14B)**
- **Fase 3 (post-producción)** — `PostProduction` con target_fps,
  target_resolution, upscale_with (real_esrgan/topaz/none), fps_interpolation
  (rife/none).
- **Atmósfera sonora baked-in** (Opción A) — `04_dialoguista.txt` emite
  bloque `=== ATMÓSFERA SONORA ===` con MOOD/MÚSICA/REFERENCIAS/SFX/DIÉGESIS/SILENCIO.
  `SonicAtmosphere` estructura ese bloque para Suno + mmaudio.
- **Tool use estructurado** — `llm_provider.generate_structured()` fuerza
  Anthropic tool use con `tool_choice={type:tool,name:...}`. Fail-fast: si
  Claude no invoca la tool, raises. `pipeline_claude._stage_prompts_veo`
  reescrita para validar con `VeoPrompt.model_validate()`.
- **Bridge v2** — `_normalize_veo()` detecta Master Stack por presencia de
  `{visual_anchor, motion_intent, camera}` y delega a `_normalize_master_stack()`.
  `_build_scene_plan()` emite bloque `scene.master_stack` completo con las
  3 fases + sonic para que OpenMontage lo consuma.
- **Retrocompatibilidad**: formatos legacy (nested + flat) siguen funcionando.

### Commit 6 — `c77605f`
**feat: per-expert LLM config via YAML**

`config/llm_provider.yaml` define temperature/max_tokens por expert
(clasificador 0.2/1024, concepto 0.9/2048, arquitecto 0.7/4096,
escaletista 0.7/4096, dialoguista 0.85/4096, localizador 0.4/512,
director_flow 0.3/1024). Consumido por `Settings.params_for(role)` +
`llm_provider.generate(role=...)`.

### Commit 4 — `8185b32`
**feat: containerize with multi-stage Dockerfile + docker-compose**

Multi-stage Dockerfile (builder + runtime slim), `docker-compose.yml`
con mounts de config/, `.dockerignore` para builds chicos.

### Commit 3 — `1864ef6`
**feat: structured logging with structlog (pipeline_id + trace_id)**

Logs JSON con `pipeline_id` + `trace_id` por request. Contexto inyectado
en cada log call. Procesador formatea timestamp ISO + level.

### Commit 2 — `c905774`
**feat: fail-fast config with pydantic-settings**

`webapp/config.py` con `Settings(BaseSettings)`. Variables de entorno
requeridas (`ANTHROPIC_API_KEY`) validadas al import — si faltan, crashea
antes del primer request con mensaje claro.

### Commit 1 — `3b44d7b`
**feat: migrate pipeline to Claude Haiku 4.5 + add OpenMontage bridge**

Migración del backend a `claude-haiku-4-5-20251001` via Anthropic SDK.
`llm_provider.py` adapter unificado con fallback a Ollama. Nuevo módulo
`bridge/openmontage_export.py` que convierte output de Guion_expert en
artifacts oficiales de OpenMontage (brief/script/scene_plan/checkpoint).

---

## [2.0.0] - 2025-01-19

### Added
- 🎬 Director Flow para Google Veo/Flow
- 📖 53 estructuras narrativas de todo el mundo
- 📺 70+ formatos de video soportados
- 🌐 Interfaz web moderna con WebSockets
- 🤖 8 expertos de IA especializados
- 🐳 Soporte completo para Docker
- 🔐 Sistema multi-usuario con autenticación
- 📊 Sistema de cola para múltiples generaciones
- 🚀 Scripts de deploy para Railway, Vercel, DigitalOcean
- 📚 Documentación extensa

### Changed
- ⚡ Optimización de prompts (30% más rápido)
- 🎨 UI completamente rediseñada
- 📝 Pipeline mejorado con mejor logging

### Fixed
- 🐛 Parsing robusto de archivos de clasificación
- 🐛 Manejo de errores en WebSockets
- 🐛 Timeouts configurables por tarea

## [1.0.0] - 2024-12-01

### Added
- Versión inicial del sistema
- Pipeline básico de 5 expertos
- Interfaz por línea de comandos
