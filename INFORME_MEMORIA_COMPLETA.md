# Informe consolidado — Memoria completa de la conversación

> **Audiencia:** dev handoff (vos + cualquier dev/diseñador/PM que entre frío al proyecto).
> **Fecha:** 2026-04-22 · **Revisión:** v1 (memoria-snapshot)
> **Alcance:** consolidación catalogada de los 4 hilos de research producidos en la conversación: (1) deep-dive Guion_expert, (2) handoff Guion_expert → OpenMontage, (3) research del "Ghost Agent / Agente Fantasma" + PRD/PRS de la plataforma unificada, (4) landscape competitivo de las 10 grandes empresas IA aplicadas a cine.
> **Branch activo:** `feature/llm-provider-unified` · **Último commit propio:** `6dfaf86` (commit 11/12 — `feat(bridge/asset_generator)`).
> **Complementa (no reemplaza):** `INFORME_GUION_EXPERT.md`, `INFORME_HANDOFF_OM.md`, `PRD_PLATAFORMA_UNIFICADA.md`. Este documento es el **mapa-índice + síntesis ejecutiva** que une los tres anteriores con la investigación externa.

---

## Tabla de contenidos

1. [Resumen ejecutivo](#1-resumen-ejecutivo)
2. [Mapa de la conversación y entregables previos](#2-mapa-de-la-conversación-y-entregables-previos)
3. [Pieza 1 — Guion_expert: motor cognitivo de guion](#3-pieza-1--guion_expert-motor-cognitivo-de-guion)
4. [Pieza 2 — Handoff Guion_expert → OpenMontage](#4-pieza-2--handoff-guion_expert--openmontage)
5. [Pieza 3 — Ghost Agent / Agente Fantasma: arquitectura unificada](#5-pieza-3--ghost-agent--agente-fantasma-arquitectura-unificada)
6. [Pieza 4 — UI/UX consumer: del producto a video descargable](#6-pieza-4--uiux-consumer-del-producto-a-video-descargable)
7. [PRD consolidado](#7-prd-consolidado)
8. [PRS — Especificación técnica](#8-prs--especificación-técnica)
9. [Landscape competitivo: 10 empresas IA aplicadas a cine](#9-landscape-competitivo-10-empresas-ia-aplicadas-a-cine)
10. [Roadmap de ejecución (3 fases)](#10-roadmap-de-ejecución-3-fases)
11. [Deuda técnica, riesgos y gaps abiertos](#11-deuda-técnica-riesgos-y-gaps-abiertos)
12. [Decisiones pendientes (asks al usuario)](#12-decisiones-pendientes-asks-al-usuario)
13. [Apéndices](#13-apéndices)

---

## 1. Resumen ejecutivo

### Qué se construyó hasta hoy

Hay dos pipelines existentes y funcionales en el repo:

- **Guion_expert** — motor cognitivo Python/Flask que toma una idea en español y produce: guion estructurado, scene_plan cinematográfico v2 con `master_stack` completo (FLUX prompt, I2V config, Suno music, mmaudio SFX, post_production), y un bridge determinístico hacia OpenMontage. Siete *experts* especializados (clasificador, concepto, arquitecto, escaletista, dialoguista, localizador, director_flow), seis migrados a `claude-haiku-4-5-20251001` con tool use forzando JSON válido. Branch `feature/llm-provider-unified`, 12 commits desde el inicio, último propio `6dfaf86`.

- **OpenMontage** — pipeline agentic Markdown/YAML que ensambla el video final (Remotion + FFmpeg) consumiendo el handoff de Guion_expert. Tiene dos modos: el oficial (`cinematic.yaml`, 7 stages) que aún no consume el `master_stack v2`, y los drivers Python one-off (`run_asset_director.py`, `train_lora.py`, `run_audio_director.py`, `run_edit_director.py`) que sí produjeron `FINAL_3SM_REEL.mp4` (9.4 MB) en el proyecto piloto 3SM.

### Lo que falta y por qué importa

Tres bloques están separados y hay que unirlos:

1. **El bridge `bridge/asset_generator.py`** (commit 11) está escrito (1013 líneas) pero todavía no reemplaza a los drivers one-off. Una vez cableado, sustituye a los 4 scripts manuales y vuelve la generación de assets programática y observable.
2. **El skill cinematic de OpenMontage no consume el `master_stack v2`** que produce Guion_expert. Hoy ignora `camera`, `motion_intent`, `sonic.silence_moments` y `post_production`. Hay que enseñar al asset-director y al edit-director a leerlos.
3. **No hay UI consumer.** Hoy todo se opera por CLI/scripts. El producto necesita una interfaz web donde el usuario sube selfie + foto del producto, escribe la idea, ve un preview Remotion zero-key, aprueba/itera, y descarga MP4 sin marca de agua.

### El concepto unificador: Ghost Agent (Agente Fantasma)

La pregunta del usuario fue *"¿podemos crear un sistema de agente fantasma para unificar ambos pipelines?"*. La respuesta es sí, y el patrón correcto es un **orquestador stateful y resiliente, residente en background, que no genera contenido creativo** sino que actúa como tejido de unión entre Guion_expert y OpenMontage. El Ghost Agent:

- **Suplanta contextos de autorización** — resuelve OAuth, API keys (fal.ai, Anthropic, ElevenLabs, Suno) sin pedir login al usuario en cada salto.
- **Rehidrata estado** — usa un motor de durable execution (recomendado: Temporal; alternativa: Inngest/Trigger.dev) para persistir el workflow antes de cada llamada larga (render de video toma minutos). Si un nodo falla, hidrata el último estado válido y reintenta sin duplicar costos.
- **Resuelve contratos de datos** — intercepta el `checkpoint.json` de Guion_expert (`source=Guion_expert, next_stage=assets`), valida `master_stack_v2` contra schema, salta las stages 1–4 de OpenMontage y arranca directo en `asset-director`.
- **Conmuta por error entre proveedores** — si Kling 3 cae o un filtro de contenido bloquea un prompt, redirige el mismo `master_stack` a Veo 3.1 / Runway Gen-4.5 / Hailuo 02 / WAN 2.2 sin intervención.
- **Auditabilidad inmutable** — todas las decisiones autónomas (reintentos, escaladas, routing por costo) van a telemetría OpenTelemetry para observabilidad.

### El producto resultante

**Guion Studio** — SaaS donde un emprendedor LATAM sube **selfie + foto de su producto** (perfume, crema, plato de comida, ropa), escribe **una idea en español** ("quiero un reel mostrando mi perfume como un recuerdo de verano"), hace clic en **Generar**, y recibe un **video terminado 1080×1920, 15–60 s, con música + SFX + consistencia facial y de producto** listo para Instagram/TikTok. Costo marginal ~$1 por video vs. $200–500 que cobra una agencia.

### Posicionamiento

- **Krea / Higgsfield / Runway / Pika** son creative suites generalistas en inglés, sin pipeline narrativo en español, sin onboarding consumer.
- **Sora 2 (OpenAI)** tiene filtros que bloquean productos comerciales y rostros sin consentimiento explícito.
- **Synthesia** es para video corporativo con avatares fijos, no para producto físico.
- **Guion Studio** se diferencia por: (a) input español por default, (b) pipeline narrativo de 7 experts especializados, (c) Master Stack v2 que entrega fidelidad de marca y producto (Product Truth) usando IP-Adapter + ControlNet sobre FLUX como capa base, (d) UX consumer "subo foto y describo idea", sin prompts técnicos.

### Estimación de costo unitario (revisión 2 del PRD)

~$1.00–$2.50 por reel de 15–30 s, dependiendo de routing:

- 6 escenas × FLUX.1 Pro (img keyframes) ≈ $0.18
- 6 escenas × Kling 2.5 Pro Std (I2V, 5 s c/u) ≈ $1.50
- 6 escenas × mmaudio v2 (SFX) ≈ $0.30
- 1 track Suno (música, flat-rate $10/mes prorrateado)
- LoRA training de identidad ≈ $1.50 (one-shot por usuario)

A 1000 reels/mes con 30% margen, plan pago = $5–$15/usuario/mes (vs. agencia $200–500/reel).

---

## 2. Mapa de la conversación y entregables previos

Esta es la cronología de los 4 entregables que vivimos juntos. Todos viven en `/sessions/bold-great-goldberg/mnt/ESCRIBE/Guion_expert/`:

| # | Archivo | Tamaño | Fecha | Foco |
|---|---|---|---|---|
| 1 | `INFORME_GUION_EXPERT.md` | 56 KB | 2026-04-21 21:32 | Deep-dive del repo Guion_expert: 15 secciones, módulo por módulo, schemas, configuración, commits, deuda |
| 2 | `INFORME_HANDOFF_OM.md` | 47 KB | 2026-04-21 22:35 | Contrato Guion_expert ↔ OpenMontage: los 6 archivos del handoff, master_stack v2, modos de ejecución, gaps |
| 3 | `PRD_PLATAFORMA_UNIFICADA.md` | 61 KB | 2026-04-22 01:17 | PRD revisión 2 de Guion Studio: visión, journey, features P0–P2, Ghost Agent, ADRs, plan de PRs, comparativa top-10 modelos |
| 4 | (este archivo) `INFORME_MEMORIA_COMPLETA.md` | — | 2026-04-22 | Consolidación catalogada de los 3 anteriores + research externo (Gemini Phantom Agent + 10 empresas IA cine) |

Adicionalmente, en la conversación llegó research externo (no como archivo sino como mensaje pegado del usuario):

- **Gemini "Agente Fantasma"** — research que define el patrón Phantom Agent, el contrato de datos Master Stack v2, la fusión Guion_expert + OpenMontage, la arquitectura de Brain & Brawn (control plane vs execution plane), el uso de IP-Adapter + ControlNet para Product Truth, y un esqueleto PRD/PRS. Cita ~50 fuentes (atlascloud.ai, learn.microsoft.com, arxiv.org, huggingface.co, etc.).
- **Comparativa "Top 10 empresas IA cine"** — ChatGPT/equiv. mapeando OpenAI, Google, Microsoft, AWS, Meta, NVIDIA, Adobe, Stability AI, Synthesia, ElevenLabs contra atributos cinematográficos (resolución, fps, control de cámara, audio, formatos) y roles de producción (director, DP, gaffer, editor, sonido, ADR).

Este documento sintetiza esos 4 inputs en un único punto de entrada.

---

## 3. Pieza 1 — Guion_expert: motor cognitivo de guion

> Ver detalle completo en `INFORME_GUION_EXPERT.md` (56 KB, 15 secciones). Aquí va el resumen ejecutivo.

### 3.1 Qué es

Suite de IA en Python 3.14 que automatiza el pipeline:

```
idea (es) → guion estructurado → scene_plan v2 → bridge a OpenMontage
```

La autoría narrativa vive acá. La renderización vive en OpenMontage. Entre los dos hay un bridge determinístico (`bridge/openmontage_export.py`) que traduce los artefactos sin llamar a un LLM.

### 3.2 Arquitectura (alto nivel)

```
┌─────────────────────────────────┐
│  Guion_expert (Python 3.14)     │
│  Flask + SocketIO ──► Pipeline  │
│     │                   │       │
│     ▼                   ▼       │
│  Browser          Claude Haiku  │
│  (index.html)     4.5 + tool use│
│                         │       │
│                         ▼       │
│                    output/<ts>/ │
│                    escenas/     │
│                    prompts_veo/ │
└────────────────┬────────────────┘
                 │ bridge (sin LLM)
                 ▼
┌─────────────────────────────────┐
│  OpenMontage/projects/<slug>/   │
│    stages/{brief,script,        │
│    scene_plan,checkpoint,       │
│    remotion-cuts}.json          │
└─────────────────────────────────┘
                 │ asset_generator
                 ▼
┌─────────────────────────────────┐
│  Integrations (fal.ai + Suno)   │
│  FLUX, Kling, Runway, WAN,      │
│  mmaudio, Real-ESRGAN, Suno     │
└─────────────────────────────────┘
```

### 3.3 Los 7 experts

Pipeline descompuesto, no "un prompt gigante":

| Expert | Rol | Modelo | Notas |
|---|---|---|---|
| `clasificador` | Detecta tipo de proyecto (publicidad / corto / videoclip / explainer) | Claude Haiku 4.5 | Migrado |
| `concepto` | Refina idea en pitch + tagline | Claude Haiku 4.5 | Migrado |
| `arquitecto` | Estructura narrativa (acto 1/2/3, beats) | Claude Haiku 4.5 | Migrado |
| `escaletista` | Escaleta scene-by-scene | Claude Haiku 4.5 | Migrado |
| `dialoguista` | Diálogo + voiceover | Claude Haiku 4.5 | Migrado |
| `localizador` | Localización geográfica/cultural (LATAM por default) | Claude Haiku 4.5 | Migrado |
| `director_flow` | Cinematografía: planos, cámara, iluminación, sonido | Claude Haiku 4.5 (último en migrar) | Pendiente migración total |

Cada expert tiene su propia `temperature`, `max_tokens`, `system_prompt` y schema de tool use que fuerza JSON válido sin necesidad de regex/fallbacks.

### 3.4 Routing determinístico de modelos de video

Los 4 modelos I2V se eligen por **tabla estática** `subject_type → modelo`, no los elige el LLM:

| `subject_type` | Modelo | Por qué |
|---|---|---|
| `human_action` (gente, retratos) | Kling 2.5 Pro | Mejor en rostros y movimiento humano |
| `landscape` (paisajes, naturaleza) | Runway Gen-3 | Mejor en escenas amplias y luz natural |
| `slow_camera` (movimiento lento, contemplativo) | WAN 2.1 14B | Mejor en cámara lenta sin artefactos |
| `static_keyframe` (imágenes base) | FLUX.1 Pro (+ LoRA) | Mejor calidad fotográfica y consistencia |

La revisión 2 del PRD ajusta esto: ya no es **un único proveedor (fal.ai)** sino **multi-proveedor con routing por especialidad** (ver §9 del PRD). Razones: fal.ai cobra +20–50% markup vs. APIs directas, y algunos modelos (Veo, Sora) no están en fal.ai.

### 3.5 Estado del repo (snapshot)

- **Branch activo:** `feature/llm-provider-unified`
- **HEAD del branch:** `c64a37c` (commit no propio, intermedio)
- **Último commit propio:** `6dfaf86` — `feat(bridge/asset_generator)` (commit 11/12)
- **12 commits totales** desde el inicio del branch
- **Line counts confirmados (ver INFORME_GUION_EXPERT.md §15):**
  - `bridge/asset_generator.py`: 1013 líneas
  - `bridge/openmontage_export.py`: 1705 líneas
  - `webapp/integrations/fal.py`: 816 líneas
  - `webapp/integrations/suno.py`: 548 líneas
  - `webapp/server.py`: 779 líneas
  - `webapp/schemas/cinematic.py`: 394 líneas
  - `config/config.py`: 318 líneas
- **Pendiente:** PR a `main`, deploy a Hetzner CX22, prompts/ uncommitted en working tree.

### 3.6 Configuración (config/)

- **56 formatos de salida** definidos (1080×1920 vertical, 1920×1080 horizontal, 1:1 cuadrado, etc., × duraciones 15/30/45/60 s × variantes plataforma).
- **45 estructuras narrativas** (3-act, 5-act, hero's journey, problema-solución, before-after, etc.).
- **7 experts** con configs YAML separadas.
- **Pydantic-settings fail-fast al boot** — si falta una API key se cae al iniciar, no in flight.

### 3.7 Costo unitario por reel de 30 s (estado actual)

~$2.52 por reel de 6 escenas:

- 6 × FLUX.1 Pro keyframe ≈ $0.18
- 6 × Kling 2.5 Pro I2V ≈ $1.50
- 6 × mmaudio v2 SFX ≈ $0.30
- 1 × Suno Premium (flat $10/mes Leo)
- + $1.50 LoRA training one-shot por banda/cliente

Revisión 2 del PRD baja esto a ~$1.00–$1.50 con routing multi-proveedor (Hailuo 02 reemplaza Kling para escenas no-críticas).

### 3.8 Decisiones de diseño críticas

1. **Claude tool use** fuerza JSON válido — sin regex, sin fallbacks, sin "parsear texto markdown".
2. **Bridge sin LLM calls** — 100% determinístico, traducción puramente sintáctica.
3. **Routing I2V por tabla estática** — el LLM no elige modelo; lo elige la tabla.
4. **Suno self-hosted** — porque no tiene API pública oficial; se usa `gcui-art/suno-api` con cookie Premium.
5. **fal.ai como proxy único en r1, multi-proveedor en r2** — flexibilidad vs. simplicidad.
6. **Pydantic-settings fail-fast** — errores de config visibles al boot, no en producción.

---

## 4. Pieza 2 — Handoff Guion_expert → OpenMontage

> Ver detalle completo en `INFORME_HANDOFF_OM.md` (47 KB, 15 secciones). Aquí va el resumen.

### 4.1 Los 6 archivos del handoff

Cuando Guion_expert termina, escribe a `OpenMontage/projects/<slug>/stages/`:

| Archivo | Propósito | Schema |
|---|---|---|
| `brief.json` | Parámetros iniciales del usuario (idea, plataforma, duración, objetivos comerciales, URL de imagen base) | `brief.schema.json` |
| `script.json` | Guion narrativo segmentado por actos + locuciones para TTS | `script.schema.json` |
| `scene_plan.json` | Desglose escena-por-escena con `master_stack v2` por escena | `scene_plan.schema.json` |
| `checkpoint.json` | Manifiesto de control de estado: `source=Guion_expert`, `next_stage=assets` | `checkpoint.schema.json` |
| `remotion-cuts.json` | Instrucciones de ensamblaje zero-key para preview React/Remotion sin gastar API | `remotion-cuts.schema.json` |
| `README.md` | Resumen humano-legible del handoff y qué corre ahora OpenMontage | (texto libre) |

### 4.2 El Master Stack v2 — el bloque estrella

Por cada escena, `scene_plan.json` lleva un objeto `master_stack` con 5 dominios paramétricos:

```json
{
  "scene_id": "s01",
  "master_stack": {
    "FLUX_prompt": {
      "subject": "perfume bottle on volcanic rock under moonlight",
      "environment": "obsidian beach, low fog, distant ocean",
      "style": "cinematic, 85mm, shallow DoF, cool grade",
      "negative": "people, text, watermark"
    },
    "camera": {
      "movement": "slow_dolly_in",
      "pan_x": 0.0, "tilt_y": 0.05, "zoom_z": 0.3,
      "duration_s": 5,
      "lens_mm": 85
    },
    "motion_intent": {
      "subject_motion": "static",
      "ambient_motion": "fog drift, water shimmer",
      "intensity": 0.4
    },
    "sonic": {
      "voiceover": { "text": "...", "lang": "es-LA", "voice_id": "..." },
      "sfx": [{ "type": "ambient_ocean", "volume_db": -18 }],
      "music": { "suno_prompt": "ambient cinematic, slow tempo, ethereal" },
      "silence_moments": [{ "at_s": 2.3, "duration_ms": 600 }]
    },
    "post_production": {
      "lut": "kodak_2383",
      "grading": "cool_blue_shadows",
      "subtitles": { "style": "tiktok_white_bg", "lang": "es" },
      "transitions": { "in": "fade", "out": "cut" }
    }
  }
}
```

Este es el **lenguaje universal** que une el espacio de tokens del LLM con el espacio latente de los modelos de difusión y el motor de composición Remotion.

### 4.3 Cómo OpenMontage ingesta

El skill cinematic de OpenMontage lee `checkpoint.json`, ve `source=Guion_expert` y `next_stage=assets`, y **salta las stages 1–4** (research, proposal, script, scene_plan), arrancando directo en `asset-director`:

```
cinematic.yaml stages:
  1. research        ◄ skip
  2. proposal        ◄ skip
  3. script          ◄ skip
  4. scene_plan      ◄ skip
  5. asset-director  ◄ START AQUÍ
  6. audio-director
  7. edit-director
```

### 4.4 Modos de ejecución de OpenMontage

Hay **dos modos coexistiendo**:

**Modo A — Agentic oficial** (`cinematic.yaml`, 7 stages, skill Markdown):
- Lo que debería usarse en producción.
- Hoy **no consume el `master_stack v2` completo** — ignora `camera`, `motion_intent`, `sonic.silence_moments`, `post_production`.
- Gap conocido a resolver.

**Modo B — Drivers Python one-off** (4 scripts):
- `run_asset_director.py` — genera keyframes FLUX + I2V Kling/Runway/WAN.
- `train_lora.py` — entrena LoRA de identidad por sujeto.
- `run_audio_director.py` — Suno + mmaudio + ElevenLabs.
- `run_edit_director.py` — ensambla con Remotion + FFmpeg.
- **Estos drivers SÍ produjeron el `FINAL_3SM_REEL.mp4` (9.4 MB)** del proyecto piloto 3SM. Son la prueba de que el pipeline funciona end-to-end, pero son frágiles, hardcoded y sin observabilidad.

### 4.5 El camino zero-key Remotion

Antes de gastar créditos de API caros (Kling, Veo), OpenMontage puede generar un **preview animado** en el navegador usando solo Remotion (React) + los keyframes FLUX (que son baratos, ~$0.03 c/u). El usuario ve el ritmo, las transiciones, los subtítulos y la música sintética. Si aprueba, se dispara el render full con I2V real.

Esto es clave para la UX consumer: **iterar gratis, gastar solo cuando el usuario aprueba**.

### 4.6 Gaps conocidos del handoff

1. **Rutas macOS hardcodeadas** en los drivers Python — `/Users/leo/...` no funciona en Linux. Bloqueante para Hetzner.
2. **`asset_plan.json` no cumple `asset_manifest.schema.json`** — Guion_expert escribe un formato legacy que OpenMontage rechaza si valida estricto. Hoy se permite. Hay que normalizar.
3. **Skills cinematic aún no consumen `master_stack v2`** — pierden información de cámara, motion intent, sonic silences, post-production.
4. **`bridge/asset_generator.py` (commit 11) está escrito pero no cableado** — hay que reemplazar los 4 drivers one-off por este orquestador único.

---

## 5. Pieza 3 — Ghost Agent / Agente Fantasma: arquitectura unificada

### 5.1 La pregunta que disparó esto

> *"podemos crear un sistema de agente fantasma para unificar ambos pipelines, investiga la mejor implementación"*

Y la respuesta del usuario al *"¿qué entendés por agente fantasma?"*:

> *"quiero indagar en un código que haga una fisión entre Guion_expert y OpenMontage, luego convertir la UI/UX en una plataforma donde suba mi foto, mi producto (perfume, cremas, platos de comida) y muchas más, escribir la idea, corre el script y en la UI vemos el resultado, desde ahí un botón para descargar, luego implementar nuevas funciones."*

Esto definió tres ejes simultáneos: **(a) fusión técnica**, **(b) UI consumer**, **(c) extensibilidad futura**.

### 5.2 Por qué un Ghost Agent y no un orquestador clásico

Los patrones tradicionales (Celery + Redis, Airflow, AWS Step Functions plain) tienen tres problemas para este dominio:

1. **Ciclos largos** — un render de video toma 2–5 minutos por escena. Serverless tradicional (Lambda 15 min cap) y workers Celery hilados con timeouts cortos son frágiles.
2. **Idempotencia** — si un nodo falla y reintenta, no debe duplicar el costo de generar el video. Celery default no garantiza esto.
3. **Estado complejo en multi-etapa** — el workflow tiene ramas condicionales, fallbacks por proveedor, esperas a webhooks. Una cola FIFO no lo modela.

El Ghost Agent es un patrón especializado:

- **No genera contenido creativo.** No corre el LLM, no llama a FLUX, no compone con Remotion.
- **Sí orquesta el estado** — lee `checkpoint.json`, valida schemas, decide rutas, gestiona reintentos, suplanta autorizaciones.
- **Vive en background** como un daemon stateful, no como un worker stateless.

### 5.3 Arquitectura "Brain & Brawn"

Inspirado en el research de Gemini y validado por la comparativa Atlas Cloud + Temporal:

```
┌──────────────────────────────────────────────┐
│  CONTROL PLANE (Brain) — CPU ligero, alta    │
│  concurrencia                                │
│                                              │
│  - Webapp (Next.js / Flask + SocketIO)       │
│  - API Gateway                               │
│  - Ghost Agent (Temporal worker)             │
│  - Postgres (state, users, jobs)             │
│  - Redis (cache, websocket pubsub)           │
│  - Object Storage (S3/R2 para assets)        │
└──────────────────┬───────────────────────────┘
                   │ Temporal RPC + webhooks
                   ▼
┌──────────────────────────────────────────────┐
│  EXECUTION PLANE (Brawn) — GPUs caros, on-   │
│  demand vía API agregadoras                  │
│                                              │
│  - fal.ai (FLUX, Kling, Runway, WAN, mmaudio)│
│  - Anthropic API (Claude Haiku 4.5)          │
│  - ElevenLabs API (TTS)                      │
│  - Suno self-hosted (cookie Premium)         │
│  - Replicate / Atlas Cloud (fallback)        │
└──────────────────────────────────────────────┘
```

**Ventaja clave:** las GPUs son las que cuestan. Mantenerlas fuera del control plane permite escalar el frontend infinitamente (CDN + edge) sin escalar el costo, y rutar a GPUs externas que se pagan por uso real.

### 5.4 Las 5 funciones canónicas del Ghost Agent

| Función | Comportamiento |
|---|---|
| **Suplantación de contexto de autorización** | Asume tokens OAuth y API keys (fal.ai, Anthropic, ElevenLabs, Suno). El usuario hace login una vez en la webapp; el Ghost Agent gestiona credenciales del lado backend. |
| **Rehidratación de estado** | Usa Temporal (recomendado) o Inngest/Trigger.dev para persistir el workflow antes de cada llamada externa. Si el worker se reinicia, hidrata el estado exacto y continúa sin duplicar costos. |
| **Resolución de contratos de datos** | Valida `master_stack_v2` contra schema antes de enviar a fal.ai. Si el LLM produjo un `pan_x` fuera de rango o un aspect ratio incompatible, dispara un loop de auto-corrección con el LLM antes de gastar API. |
| **Conmutación por error entre proveedores** | Si Kling cae (HTTP 5xx) o un filtro de contenido bloquea, redirige a Veo 3.1 / Runway Gen-4.5 / Hailuo 02 sin tocar la UI. El usuario nunca ve el error. |
| **Auditabilidad inmutable** | Cada decisión autónoma (reintento, escalada, routing por costo) va a OpenTelemetry → ClickHouse / Grafana. Trazabilidad completa para debug y para análisis de unit economics. |

### 5.5 Stack recomendado (decisión de arquitectura)

| Capa | Tecnología | Razón |
|---|---|---|
| Durable workflow | **Temporal** (self-hosted o Temporal Cloud) | Maduro, idempotencia nativa, retries con backoff, signals/queries. Alternativa: Inngest si se quiere serverless puro. |
| Backend webapp | **Flask + SocketIO** (continúa lo que ya tiene Guion_expert) → eventual migración a **FastAPI** | Continuidad con código existente. FastAPI da tipado + async nativo si crece. |
| Frontend | **Next.js 14 + React Server Components + shadcn/ui + Tailwind** | Ecosistema maduro, edge-ready, server actions para uploads. |
| Render preview | **Remotion** (ya en OpenMontage) | Reutilizable, browser-side, zero-key. |
| Cola de eventos | **Redis Streams** (para pubsub con frontend vía SocketIO) | Simple, latencia sub-100ms para progress updates. |
| Object Storage | **Cloudflare R2** o **S3** | R2 sin egress fees → ahorro grande si se sirven previews. |
| Database | **Postgres 16** (managed: Supabase / Neon / Hetzner) | Estable, JSONB para schemas flexibles. |
| Observabilidad | **OpenTelemetry → Grafana + ClickHouse** | Stack open-source, sin lock-in. |
| Hosting | **Hetzner CX22** (control plane) + **fal.ai / proveedores** (execution plane) | Hetzner ya elegido en Guion_expert; fal.ai como agregador → pago por uso. |

### 5.6 Ciclo de vida de un job (desde clic "Generar" hasta MP4)

```
1. Usuario clic "Generar" en webapp
2. Webapp crea job_id en Postgres → emite Temporal workflow
3. Ghost Agent (Temporal worker) arranca workflow:
   3.1 Llama Guion_expert pipeline (Claude Haiku 4.5, 7 experts)
       → genera brief, script, scene_plan v2, checkpoint
   3.2 Valida master_stack_v2 contra schema
       (loop de auto-corrección si falla)
   3.3 Render keyframes FLUX (paralelo, 6 llamadas a fal.ai)
   3.4 Genera preview Remotion zero-key
       → emite evento WebSocket → UI muestra preview
4. Usuario aprueba o itera
   - Si itera: vuelve a paso 3.3 con master_stack actualizado
   - Si aprueba: continúa
5. Render full I2V (paralelo, 6 llamadas — Kling/Runway/WAN según routing)
6. Render audio (Suno música + mmaudio SFX + ElevenLabs voz)
7. Composición final (Remotion + FFmpeg) → MP4 1080×1920
8. Sube a R2/S3 → URL firmada con expiración 7 días
9. Emite evento WebSocket → UI muestra botón Descargar
10. Telemetría completa al data lake
```

### 5.7 Tabla de patrones rechazados y por qué

| Patrón | Por qué se rechaza |
|---|---|
| Celery + Redis simple | No idempotencia nativa, retries duplican costos en cargas largas. Sirve para webapp clásica, no para pipelines IA con costos por llamada. |
| AWS Step Functions | Vendor lock-in, latencia de RPC entre nodos costosa, modelo de definición YAML pesado. |
| Airflow | Diseñado para ETL batch nocturno, no para workflows iniciados por usuario con SLA <5 min. |
| Plain async/await en Python | Si el worker muere, se pierde el estado completo. Sin idempotencia. |
| LangGraph / CrewAI / AutoGen como orquestador | Útil para chains LLM, no para pipelines de generación con costos altos por llamada. Falta de durable execution. |

---

## 6. Pieza 4 — UI/UX consumer: del producto a video descargable

### 6.1 Principio rector: divulgación progresiva (Progressive Disclosure)

La interfaz debe sentirse tan simple como Instagram, ocultando completamente la complejidad de IP-Adapter, ControlNet, Master Stack v2, Ghost Agent, fallback de proveedores. El usuario solo ve:

```
1. Subo foto    →    2. Escribo idea    →    3. Espero    →    4. Descargo
```

### 6.2 Las 5 etapas de la UI

| Etapa | Pantalla | Lógica oculta |
|---|---|---|
| **1. Ingesta de activos** | Drop-zone para selfie + foto del producto. IA en cliente (TF.js o Replicate edge) valida iluminación, aísla sujeto del fondo, sugiere contextos visuales. | LoRA training se dispara en background si es la primera vez. Costo $1.50 una sola vez por usuario. |
| **2. Declaración de intención** | Caja de texto simple ("Quiero un reel mostrando mi perfume como recuerdo de verano") + dropdowns de plataforma (Instagram Reels / TikTok / Shorts) y duración (15/30/45/60 s). Controles avanzados (motion intent, lentes, LUTs) en panel plegable "Avanzado". | Guion_expert pipeline arranca con plataforma/duración como inputs del `brief.json`. |
| **3. Manejo de latencia** | Stepper visual con narrativa ("Extrayendo geometría del producto", "Escribiendo el guion en español", "Componiendo la música", "Renderizando iluminación cinemática"). Progress real vía WebSocket. | Cada etapa del stepper mapea a una activity de Temporal. Eventos vienen del Ghost Agent. |
| **4. Preview zero-key** | Reproductor Remotion en navegador con borrador animado: keyframes + voiceover sintético + música real. Botones: "Aprobar y generar HD" / "Iterar". | Solo se gastó ~$0.20 hasta acá (FLUX keyframes + Suno + ElevenLabs). I2V real (Kling) se paga solo si aprueba. |
| **5. Iteración y descarga** | Reproductor del MP4 final + botones modulares ("Cambiar música", "Hacer paneo más lento", "Otra paleta de color") + botón Descargar (sin watermark en plan pago). | Cada modular cambia 1 nodo del Master Stack v2 y re-renderiza solo lo afectado, no todo el reel. Costo de iteración ~$0.30. |

### 6.3 Product Truth — el problema técnico que resolver

El fracaso típico de "subo foto y genero video" es **character drift**: el perfume se deforma, la etiqueta cambia de color, el frasco pierde proporciones. Para producto comercial esto es deal-breaker.

La solución es un **Hybrid Control Stack** sobre FLUX (modelo base):

```
┌─────────────────────────────────────────────┐
│  IP-Adapter                                 │
│  Inyecta features visuales del producto     │
│  directamente en cross-attention del U-Net  │
│  (paralelo al text encoder)                 │
│  → 90%+ consistencia zero-shot              │
└─────────────────────────────────────────────┘
                  +
┌─────────────────────────────────────────────┐
│  ControlNet (depth o canny)                 │
│  Bloqueo topológico: extrae mapa de         │
│  profundidad/bordes → fuerza al U-Net a     │
│  respetar geometría 3D del producto         │
│  → evita deformaciones bajo movimiento      │
└─────────────────────────────────────────────┘
                  +
┌─────────────────────────────────────────────┐
│  LoRA training opcional (en primer reel)    │
│  Entrenamiento de identidad facial del      │
│  usuario (~$1.50, ~5 min, una vez)          │
│  → reusable en futuros reels                │
└─────────────────────────────────────────────┘
                  =
        Product Truth >95% retention
        (umbral comercial mínimo)
```

Para el video propiamente dicho (I2V), el flujo es:

1. FLUX genera el **anchor frame** (imagen estática perfecta del producto en el contexto narrativo).
2. Kling 3 / Veo 3.1 hace **temporal inflation** — toma el anchor frame y genera 5 s de video manteniendo la semilla de ruido y aplicando los vectores de cámara del Master Stack v2.
3. Resultado: movimiento cinemático sin alucinar geometría del producto.

### 6.4 Micro-interacciones críticas

- **No barra estática** — narrativa de creación ("Ahora el director de fotografía está eligiendo el lente"). Reduce abandono.
- **Preview audible** durante la espera — locuciones generadas con ElevenLabs llegan en segundos y se reproducen mientras se renderiza el video, dando sensación de progreso.
- **Cambios modulares en el video final** — no regenerar todo. Si el usuario dice "cambiar música", solo se re-renderiza la track de audio + composición final, no los I2V (que son lo caro).
- **Onboarding sin login** — el primer reel se puede generar con email-only (magic link) para reducir fricción. Login obligatorio solo en descarga.

### 6.5 Casos de uso por vertical

| Vertical | Ejemplo de input | Output esperado |
|---|---|---|
| Perfumería | Foto del frasco + "como recuerdo de verano en la playa" | Reel cinematográfico, 30 s, paleta cool, música ambient, 6 escenas |
| Cosmética / Cremas | Foto del envase + "skincare nocturno relajante" | Reel suave, 30 s, paleta warm, música spa, 5 escenas |
| Gastronomía | Foto del plato + "comida casera con sabor a abuela" | Reel cálido, 45 s, primeros planos, música acústica, 7 escenas |
| Ropa / Moda | Foto + selfie + "outfit de fin de semana urbano" | Reel dinámico, 15 s, ritmo rápido, música electrónica, 4 escenas |
| Joyería | Foto de la pieza + "elegancia atemporal" | Reel slow-motion, 30 s, paleta neutra, música clásica, 6 escenas |

---

## 7. PRD consolidado

> Versión revisada y resumida de `PRD_PLATAFORMA_UNIFICADA.md` (61 KB). Aquí va el PRD ejecutivo en una pieza.

### 7.1 Visión

**Guion Studio** — la primera plataforma de video con IA hecha en español para emprendedores LATAM con producto físico. De la idea al reel descargable en 15 minutos, sin editor de video.

### 7.2 Tagline y propuesta de valor

> *"De la idea al reel, en 15 minutos, sin editor de video."*

| Para el usuario (emprendedor LATAM) | Para el negocio |
|---|---|
| No necesita saber editar video | TAM: >5M emprendedores pymes en LATAM con producto físico |
| Salida en español por default | Costo marginal: ~$1/video vs. $200–500 agencia |
| Consistencia facial y de producto sin prompts técnicos | Mercado vertical mal atendido por tooling en inglés |
| Descarga directa sin watermark en plan pago | Moat: pipeline narrativo en español + Master Stack v2 |

### 7.3 Personas y JTBD

**Persona A — Pyme retail** (e-commerce con 50–500 SKUs)
- JTBD: "Necesito 30 reels al mes para Instagram para no quedar fuera del feed, pero no puedo pagar agencia."

**Persona B — Creador de contenido** (afiliado / dropshipper / influencer micro)
- JTBD: "Quiero probar 10 ideas de reel por semana sin grabar. Si una pega, escalo."

**Persona C — Restaurante / Catering** (negocio físico local)
- JTBD: "Tengo plato del día. Necesito reel hoy, no en 3 días que tarda mi sobrina."

### 7.4 User journey principal (happy path)

```
1. Landing → "Probá gratis tu primer reel" → email
2. Onboarding 60s → "Subí tu selfie + foto del producto"
3. Caja de texto → "Describí la idea en una frase"
4. Click Generar → stepper visual con narrativa de creación
5. Preview Remotion (5 min) → "Aprobá o iterá"
6. Render HD (10 min) → MP4 1080×1920
7. Descarga directa (plan free: con watermark; plan pago: sin)
8. Upsell: "Generá 10 más por $10/mes"
```

### 7.5 Features MVP (P0)

1. **Onboarding sin fricción** — magic link email, sin contraseña.
2. **Upload selfie + producto** — drop-zone con validación cliente.
3. **Caja de idea en español** — sin prompts técnicos.
4. **Pipeline Guion_expert + OpenMontage cableado** — vía Ghost Agent.
5. **Preview Remotion zero-key** — para iterar gratis.
6. **Render HD** — 1080×1920, 15–60 s.
7. **Descarga MP4** — con watermark en free, sin en pago.
8. **Plan free (1 reel/mes) + plan Starter ($10/mes, 10 reels)**.

### 7.6 Features V2 (P1)

1. **Iteración modular** — cambiar música / cámara / paleta sin regenerar todo.
2. **Library de estilos preset** — "Apple", "TikTok viral", "Storytelling cinemático", etc.
3. **Multi-aspect** — generar 1080×1920 + 1080×1080 + 1920×1080 del mismo reel.
4. **Programación a redes** — publicar directo a Instagram/TikTok via API.
5. **Voces en LATAM** — selección de acentos (CL, AR, MX, CO, ES) en TTS.

### 7.7 Features V3 (P2)

1. **Webhooks → Shopify / WooCommerce** — generar reel automático cuando se sube SKU nuevo.
2. **Equipos** — múltiples usuarios por cuenta (agencias).
3. **API pública** — para integrar el motor en otras plataformas.
4. **Brand Kit** — logos, fuentes, paletas → se aplican automáticamente.
5. **Analytics post-publicación** — qué reel performó, qué tag funcionó.

### 7.8 Métricas de éxito (KPIs)

- **TTFI (Time To First Insight)** — guion preview visible en <10 s.
- **TTV (Time To Video)** — MP4 final descargable en <15 min wall-clock.
- **Conversión free → pago** — >5% en 30 días.
- **Costo marginal por reel** — <$1.50 con plan medio uso.
- **NPS** — >50 en cohorte beta.
- **Retention M1** — >40% de usuarios pago activos al mes 1.

### 7.9 Decisión sobre arquitectura (de los 3 inputs del usuario)

El usuario respondió a las 3 preguntas:

| Pregunta | Respuesta |
|---|---|
| ¿Qué entendés por agente fantasma? | Fusión de Guion_expert + OpenMontage + UI consumer + extensibilidad. |
| ¿Qué profundidad querés del entregable? | Solo research + informe (Recomendado) — no build aún. |
| ¿Dónde vive el agente? | Lo decide [el sistema]. → **Decisión: Temporal worker en Hetzner CX22, control plane separado del execution plane (que es fal.ai + APIs externas)**. |

---

## 8. PRS — Especificación técnica

### 8.1 Requerimientos no-funcionales

| Requerimiento | Umbral |
|---|---|
| Fidelidad visual (Product Truth) | Retención de identidad >95% (medida por similarity entre input y frames clave del output, usando CLIP embeddings) |
| SLA latencia preview | TTFI guion <10 s · Preview Remotion <5 min wall-clock |
| SLA latencia render full | <15 min wall-clock para reel de 30 s con 6 escenas |
| Disponibilidad | 99.5% (control plane) — execution plane absorbe caídas vía conmutación |
| Tolerancia a fallos | Reintentos automáticos hasta 3× con backoff exponencial; conmutación a proveedor secundario al 2do fallo del primario |
| Validación pre-vuelo del Master Stack v2 | 100% de jobs pasan validación schema antes de gastar API |
| Auditabilidad | 100% de decisiones autónomas (reintentos, fallbacks, routing) registradas en OpenTelemetry inmutable |
| Costo unitario por reel | <$1.50 promedio en uso normal |
| Escalabilidad horizontal | Control plane escalable a 10K usuarios concurrentes en Hetzner CX22 + workers Temporal en cluster |

### 8.2 Esquemas JSON críticos (validados por Ghost Agent)

| Schema | Ubicación | Función |
|---|---|---|
| `brief.schema.json` | `webapp/schemas/brief.py` (Pydantic) | Valida input del usuario antes de arrancar pipeline |
| `master_stack_v2.schema.json` | `webapp/schemas/cinematic.py:394` | Valida cada escena antes de gastar API de generación |
| `scene_plan.schema.json` | derivado de `cinematic.py` | Valida plan completo antes de handoff a OpenMontage |
| `checkpoint.schema.json` | derivado | Valida control de estado del pipeline |
| `asset_manifest.schema.json` | OpenMontage repo | Hoy NO se valida estricto; gap conocido |

### 8.3 Diagrama de despliegue

```
┌──────────────────────────────────────────────────────────────┐
│ HETZNER CX22 (Frankfurt) — Control Plane                     │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Next.js 14  │  │ Flask +     │  │ Temporal worker     │  │
│  │ (frontend)  │◄─┤ SocketIO    │◄─┤ (Ghost Agent)       │  │
│  │             │  │ (API)       │  │                     │  │
│  └─────────────┘  └──────┬──────┘  └──────────┬──────────┘  │
│                          │                    │             │
│                   ┌──────▼─────┐       ┌──────▼─────┐       │
│                   │ Postgres   │       │ Temporal   │       │
│                   │ (state)    │       │ Server     │       │
│                   └────────────┘       └────────────┘       │
│                                                              │
│                   ┌────────────┐       ┌────────────┐       │
│                   │ Redis      │       │ R2 / S3    │       │
│                   │ (cache,    │       │ (assets)   │       │
│                   │  pubsub)   │       │            │       │
│                   └────────────┘       └────────────┘       │
└──────────────────────────────┬───────────────────────────────┘
                               │ HTTPS + webhooks
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ EXECUTION PLANE (proveedores externos, pago por uso)         │
│                                                              │
│  fal.ai      Anthropic     ElevenLabs   Suno (self-host)     │
│  - FLUX      - Claude      - TTS        - Cookie Premium     │
│  - Kling     - Haiku 4.5   voces ES                          │
│  - Runway                  LATAM        Replicate            │
│  - WAN                                  (fallback)           │
│  - mmaudio   (si pivot a                                     │
│  - LoRA      Veo / Sora /                                    │
│   training   Hailuo: APIs                                    │
│              directas)                                       │
└──────────────────────────────────────────────────────────────┘
```

### 8.4 Estrategia de routing por especialidad (multi-proveedor)

| Tipo de escena | Proveedor primario | Fallback 1 | Fallback 2 |
|---|---|---|---|
| Producto estático cinemático | FLUX.1 Pro (fal.ai) | DALL·E 3 (OpenAI) | SDXL (Replicate) |
| Persona en movimiento | Kling 2.5 Pro (fal.ai) | Veo 3.1 (Google direct) | Runway Gen-4.5 |
| Paisaje / ambiente | Runway Gen-3 (fal.ai) | Veo 3.1 | Hailuo 02 (Minimax) |
| Cámara lenta contemplativa | WAN 2.1 14B (fal.ai) | Hailuo 02 | LTX-Video 2.3 |
| Música | Suno (self-host) | Udio (API) | MusicGen (Replicate) |
| TTS español LATAM | ElevenLabs | Azure Neural Voice | Google Cloud TTS |
| SFX | mmaudio v2 (fal.ai) | AudioGen (Replicate) | Freesound API + curado |

### 8.5 Endpoints HTTP del control plane (mínimo MVP)

```
POST   /api/v1/auth/magic-link          → email magic link
POST   /api/v1/auth/verify              → verify token, return JWT
POST   /api/v1/uploads/selfie           → multipart, returns asset_id
POST   /api/v1/uploads/product          → multipart, returns asset_id
POST   /api/v1/jobs                     → body: {selfie_id, product_id, idea, platform, duration}
                                          → returns job_id, starts Temporal workflow
GET    /api/v1/jobs/:id                 → returns status + preview_url + video_url
POST   /api/v1/jobs/:id/iterate         → body: {modular_change}
                                          → re-renders only affected nodes
GET    /api/v1/jobs/:id/download        → presigned URL, expires 7d
WS     /ws/jobs/:id                     → real-time progress events
```

### 8.6 Eventos del WebSocket (UI ↔ Ghost Agent)

```json
{ "type": "stage_started", "stage": "scriptwriting", "label": "Escribiendo el guion en español..." }
{ "type": "stage_progress", "stage": "scriptwriting", "pct": 45 }
{ "type": "stage_completed", "stage": "scriptwriting", "preview_text": "..." }
{ "type": "preview_ready", "preview_url": "https://r2.../preview.mp4" }
{ "type": "render_started" }
{ "type": "render_progress", "scene": 3, "of": 6 }
{ "type": "render_completed", "video_url": "https://r2.../final.mp4" }
{ "type": "error", "code": "PROVIDER_DOWN", "fallback_to": "veo3" }
```

### 8.7 Datos a persistir (Postgres)

```sql
users (id, email, plan, created_at, ...)
assets (id, user_id, type [selfie|product], r2_key, sha256, ...)
loras (id, user_id, asset_id, fal_lora_id, trained_at, ...)
jobs (id, user_id, brief_json, status, master_stack_v2_json, costs_usd, started_at, completed_at, ...)
job_events (id, job_id, type, payload_json, ts) -- timeline para debug y UX
billing (id, user_id, period, reels_generated, cost_provider_usd, billed_usd, ...)
```

---

## 9. Landscape competitivo: 10 empresas IA aplicadas a cine

> Síntesis del research del usuario. Útil para posicionamiento y para decisiones de routing/integración.

### 9.1 Tabla comparativa (atributos clave)

| Empresa | Foco principal | Resolución max | FPS max | Audio | Integración cine |
|---|---|---|---|---|---|
| **OpenAI** | Texto, imagen, voz, video (Sora 2 con filtros) | DALL·E 3 alta (no spec) · Sora 1080p | Sora ~24 fps | TTS realista, Whisper STT | API only, sin NLE/DAW nativo |
| **Google** | Multimodal Gemini, Veo 3.1, MusicLM | Veo 1080p | Veo 24 fps | MusicGen, AudioLM | Vertex AI APIs, sin NLE propio |
| **Microsoft** | Copilot + Azure (depende de OpenAI) | (de DALL·E) | N/A | Azure Speech, Neural Voice | Plugins Office, Premiere via partnerships |
| **AWS** | Infra (Bedrock, SageMaker) + Polly + Transcribe + Nimble Studio (VFX) | (de proveedores Bedrock) | N/A | Polly TTS, Transcribe STT | XMesh para 3D, Nimble Studio para VFX |
| **Meta** | Investigación: Voicebox, MusicGen, Make-A-Video, MovieGen | Make-A-Video baja res | ~14–25 fps | MusicGen producción, Voicebox alta calidad | Open weights research, sin producto comercial |
| **NVIDIA** | Hardware GPUs + Omniverse (USD/Alembic) + LATTE3D + Audio2Face + NeMo | Depende de modelo + GPU | Depende | NeMo TTS, Audio2Face lipsync | **Mejor integración cine**: Omniverse USD/Alembic nativo, ControlNet + IP-Adapter end-to-end |
| **Adobe** | Firefly + Creative Cloud + AI Assistant + 30+ modelos partner | Variable (Runway 4.5 integrado) | Variable | Audio Enhance, voces sintéticas | **Mejor integración con NLE/DAW**: Premiere + After Effects + Audition con Firefly nativo |
| **Stability AI** | Stable Diffusion + Stable Video Diffusion + Stable3D + Brand Studio | SD 1024×1024 default, escalable | SVD 14–25 fps | (Warner partnership en música, sin producto vivo) | Open-source, plugins comunitarios para Photoshop/Resolve |
| **Synthesia** | Avatares hablantes en 100+ idiomas | 1080p HD | 24–30 fps | Voces sintéticas integradas (powered by ElevenLabs) | LMS/CMS embed, no NLE — formato cerrado |
| **ElevenLabs** | TTS hiperrealista en 70+ idiomas + Music + SFX | N/A (audio) | N/A | **Líder en voz**: clonación, control emocional, español LATAM excelente | Plugins API para Premiere, Audition, Reaper, ProTools |

### 9.2 Mapeo a roles cinematográficos

| Rol | Mejor herramienta hoy (2026) | Alternativa |
|---|---|---|
| Director / Guionista | ChatGPT GPT-4 / Claude Haiku 4.5 (lo que usamos) | Gemini |
| Director de Fotografía (DP) | DALL·E 3 / FLUX (lo que usamos) | Imagen 3 / Stable Diffusion |
| Iluminación (Gaffer) virtual | NVIDIA Omniverse (RTXGI) | After Effects + Firefly |
| Diseño de arte / Props | FLUX + Stable3D / LATTE3D | Adobe Firefly |
| Editor (Montaje) | Adobe Premiere + Firefly AI Assistant | Runway Gen-4.5 timeline |
| VFX Supervisor | NVIDIA Omniverse + PhysX | After Effects + Firefly |
| Colorista | DaVinci Resolve + Firefly Color | Lumetri en Premiere |
| Sonidista / SFX | mmaudio v2 (lo que usamos) | AudioCraft (Meta) / Adobe Podcast |
| Compositor / Score | **Suno** (lo que usamos) | Udio · MusicGen · Stable Music |
| ADR / Voice actor | **ElevenLabs** (lo que usamos) | Voicebox (Meta) / Azure Neural |

### 9.3 Por qué nuestro stack es el correcto

Lo que tenemos hoy en Guion_expert + OpenMontage cubre el 80% de lo que necesita un reel comercial vertical:

- **Guionista IA**: Claude Haiku 4.5 ✓
- **DP / arte**: FLUX.1 Pro ✓
- **I2V**: Kling 2.5 Pro / Runway Gen-3 / WAN 2.1 14B ✓
- **Sonido SFX**: mmaudio v2 ✓
- **Música**: Suno self-hosted ✓
- **Voz**: ElevenLabs ✓
- **Edit final**: Remotion + FFmpeg ✓

Lo que falta es la capa de **orquestación (Ghost Agent) + UI consumer**, no más modelos.

### 9.4 Modelos a sumar en V2 (multi-proveedor)

- **Veo 3.1 (Google)** — para escenas donde Kling falla por filtros o calidad humano-en-movimiento.
- **Hailuo 02 (Minimax)** — para volumen barato (10× más barato que Kling).
- **LTX-Video 2.3 (Lightricks)** — para previews ultra-rápidos (1–3 s render).
- **Runway Gen-4.5 con References** — para consistencia de personaje en multi-escena.

---

## 10. Roadmap de ejecución (3 fases)

### 10.1 Fase 1 — Estabilización y fusión (4–6 semanas)

**Goal:** cablear lo que ya está escrito, sin nuevas features.

- PR a `main` de `feature/llm-provider-unified` (12 commits).
- Deploy a Hetzner CX22 (control plane).
- Cablear `bridge/asset_generator.py` (commit 11) en reemplazo de los 4 drivers one-off.
- Normalizar `asset_plan.json` para cumplir `asset_manifest.schema.json`.
- Quitar paths macOS hardcoded → usar `pathlib.Path` y env vars.
- Implementar Ghost Agent v0 con Temporal: 1 workflow lineal (sin fallbacks ni iteración modular).
- IP-Adapter + ControlNet sobre FLUX como capa base de Product Truth.
- Test e2e con 10 productos reales (perfumes, cremas, platos): medir Product Truth >95%.

### 10.2 Fase 2 — UI consumer + multi-proveedor (6–8 semanas)

**Goal:** UX consumer end-to-end + resiliencia.

- Frontend Next.js 14 con las 5 etapas de UI (§6.2).
- Magic link email auth.
- Upload + LoRA training automático en background.
- Preview Remotion zero-key con WebSocket progress.
- Render full I2V con routing multi-proveedor (Kling primario, Veo/Runway/Hailuo fallback).
- Iteración modular (cambiar música / cámara / paleta sin re-render full).
- Plan free + plan Starter ($10/mes) con Stripe.
- Telemetría OpenTelemetry → Grafana.
- Beta privada con 50 usuarios LATAM.

### 10.3 Fase 3 — Escala + features V2 (8–12 semanas)

**Goal:** producto comercial.

- Library de presets de estilo ("Apple", "TikTok viral", "Storytelling cinemático").
- Multi-aspect (1080×1920 + 1080×1080 + 1920×1080).
- Voces TTS por país (CL/AR/MX/CO/ES).
- Programación a Instagram/TikTok via API.
- Webhooks Shopify / WooCommerce.
- Brand Kit (logos, fuentes, paletas auto-aplicadas).
- Equipos / sub-cuentas para agencias.
- API pública para integradores.
- Analytics post-publicación (qué reel performó).

---

## 11. Deuda técnica, riesgos y gaps abiertos

### 11.1 Deuda técnica conocida (heredada del estado actual)

| Item | Severidad | Bloqueante | Origen |
|---|---|---|---|
| Paths macOS hardcoded en drivers Python | Alta | Sí (Hetzner) | INFORME_HANDOFF_OM §4 |
| `asset_plan.json` no cumple `asset_manifest.schema.json` | Media | No (hoy se permite) | INFORME_HANDOFF_OM §4 |
| Skills cinematic NO consumen `master_stack v2` completo | Alta | Sí (perdemos calidad) | INFORME_HANDOFF_OM §4 |
| `bridge/asset_generator.py` escrito pero no cableado | Media | Sí (drivers one-off frágiles) | commit 11 sin tests |
| 12vo commit `c64a37c` no es propio (HEAD) | Baja | No | git status |
| `prompts/` uncommitted en working tree | Baja | No | git status |
| PR a `main` pendiente | Media | Sí | flujo |
| Suno cookie Premium vence — no rotación automática | Media | Sí (a medio plazo) | INFORME_GUION_EXPERT §3 |
| 1 expert (`director_flow`) aún no migrado 100% a Haiku 4.5 | Baja | No | INFORME_GUION_EXPERT §3.3 |

### 11.2 Riesgos de producto

| Riesgo | Mitigación |
|---|---|
| Filtros de contenido bloquean producto comercial (Veo / Sora) | Routing primario en Kling/Runway/FLUX; Veo/Sora solo en fallback selectivo |
| Costo de I2V escala mal con uso heavy | Plan freemium con cap; iteración modular; Hailuo 02 para volumen |
| Product Truth <95% en productos translúcidos (vidrio, líquido) | LoRA training específico por producto (one-shot $1.50, reusable) |
| Latencia >15 min frustra al usuario | Preview zero-key Remotion en <5 min; narrativa de creación durante espera |
| Suno cae o cambia API self-host | Fallback a Udio API (cuando salga) o MusicGen Replicate |
| ElevenLabs encarece pricing | Azure Neural Voice como fallback (calidad menor pero estable) |
| Competencia (Krea / Higgsfield) lanza versión LATAM | Moat: pipeline narrativo + Master Stack v2 + UX consumer; difícil de copiar rápido |

### 11.3 Riesgos legales / éticos

- **Deepfake de voz** — clonación de voz del usuario solo con consentimiento explícito + watermark digital (ElevenLabs ya lo hace).
- **Uso de productos de terceros** — disclaimer al subir foto: "Solo subí productos de los que tenés derechos".
- **Generación con rostros de menores** — bloqueo automático con detector facial cliente.
- **Copyright en imágenes de referencia** — IP-Adapter usa solo la imagen subida por el usuario, no entrena con ella.

---

## 12. Decisiones pendientes (asks al usuario)

Estas son las decisiones que quedaron abiertas en la conversación y que necesitan resolverse antes de empezar build:

### 12.1 Producto

1. **¿Plan free con 1 reel/mes con watermark, o trial de 7 días sin límite?** — Define la estrategia de adquisición.
2. **¿Lanzamos en CL (mercado de Leo) o multi-país LATAM desde día 1?** — Define localización TTS y monedas.
3. **¿Onboarding sin login (magic link en descarga) o login obligatorio desde subida?** — Trade-off fricción vs. data.
4. **¿Mostramos el "guion en español" al usuario antes del preview, o lo escondemos?** — Más control vs. más fricción.

### 12.2 Técnico

5. **Temporal self-hosted en Hetzner o Temporal Cloud?** — Cost ($0 vs. ~$200/mes) vs. ops burden.
6. **Frontend: Next.js o seguir con Flask + Jinja templates de Guion_expert?** — Velocidad UI moderna vs. continuidad código.
7. **R2 o S3 para object storage?** — R2 sin egress (mejor si servimos previews); S3 más maduro.
8. **¿Pago directo Anthropic / fal.ai / ElevenLabs o agregadores tipo OpenRouter?** — Control vs. simplicidad de billing.

### 12.3 Diseño

9. **Brand y nombre final** — "Guion Studio" es trabajado; ¿lo confirmamos o iteramos?
10. **Idioma del producto** — ¿solo español, o español + inglés para expansión futura?

---

## 13. Apéndices

### 13.1 Glosario

| Término | Definición |
|---|---|
| **Guion_expert** | Repo Python que aloja el motor cognitivo (LLM + experts + bridge). |
| **OpenMontage** | Repo separado que aloja el pipeline de ensamblaje (Remotion + FFmpeg + skills agentic). |
| **Master Stack v2** | Schema JSON que captura toda la intención cinematográfica de una escena: FLUX prompt, camera, motion intent, sonic, post production. |
| **Ghost Agent / Agente Fantasma** | Patrón de orquestación stateful en background que une Guion_expert + OpenMontage sin que el usuario vea complejidad. No genera contenido, solo orquesta. |
| **Product Truth** | Fidelidad >95% del producto subido por el usuario en todos los frames del video (forma, color, marca). |
| **IP-Adapter** | Técnica de inyección de features visuales en cross-attention del U-Net de un modelo de difusión. |
| **ControlNet** | Técnica de bloqueo topológico (depth/canny) para forzar geometría 3D respetada. |
| **LoRA** | Low-Rank Adaptation — ajuste de pesos parcial de un modelo grande para personalización. |
| **Anchor frame** | Frame estático perfecto generado por FLUX que sirve como input al modelo I2V. |
| **Temporal inflation** | Técnica de I2V que mantiene constante la semilla de ruido y aplica vectores de cámara para generar video sin alucinar. |
| **Zero-key preview** | Preview en navegador con Remotion, sin gastar API de generación de video (solo keyframes baratos). |
| **TTFI** | Time To First Insight — tiempo hasta que el usuario ve algo útil (guion preview). |
| **TTV** | Time To Video — tiempo hasta MP4 final descargable. |
| **Brain & Brawn** | Patrón de arquitectura: control plane (CPU ligero, alta concurrencia) separado de execution plane (GPUs caras, on-demand). |
| **Durable workflow** | Workflow que persiste estado antes de cada llamada externa, idempotente, resistente a reinicios. |

### 13.2 Variables de entorno necesarias (env vars del control plane)

```bash
# Anthropic
ANTHROPIC_API_KEY=...

# fal.ai (multi-modelo)
FAL_KEY=...

# ElevenLabs
ELEVENLABS_API_KEY=...

# Suno (self-host)
SUNO_COOKIE=...                  # rotar manualmente cada ~30d
SUNO_API_BASE_URL=http://...    # gcui-art/suno-api self-hosted

# Object storage
R2_ACCOUNT_ID=...
R2_ACCESS_KEY=...
R2_SECRET_KEY=...
R2_BUCKET=guion-studio-prod

# Database
DATABASE_URL=postgres://...

# Temporal
TEMPORAL_HOST=temporal:7233
TEMPORAL_NAMESPACE=guion-studio

# Auth
JWT_SECRET=...
EMAIL_PROVIDER=resend
RESEND_API_KEY=...

# Observabilidad
OTEL_EXPORTER_OTLP_ENDPOINT=http://...
GRAFANA_API_KEY=...

# Stripe
STRIPE_SECRET_KEY=...
STRIPE_WEBHOOK_SECRET=...
```

### 13.3 IDs de modelos fal.ai usados

```
fal-ai/flux-pro/v1.1                # keyframes
fal-ai/flux-lora                    # con LoRA de identidad
fal-ai/flux-lora-fast-training      # train LoRA
fal-ai/kling-video/v2.5-pro/image-to-video    # I2V humanos
fal-ai/runway-gen3/turbo/image-to-video       # I2V paisajes
fal-ai/wan-pro/image-to-video                 # I2V cámara lenta
fal-ai/mmaudio-v2                             # SFX
fal-ai/real-esrgan                            # upscale
```

### 13.4 Comandos útiles

```bash
# Levantar todo en local
cd /sessions/bold-great-goldberg/mnt/ESCRIBE/Guion_expert
./iniciar.sh

# Estado del pipeline
./status.sh

# Detener
./detener.sh

# Ejecutar pipeline manualmente con un prompt
python -m webapp.cli --idea "perfume como recuerdo de verano" --duration 30 --platform reels

# Bridge a OpenMontage
python -m bridge.openmontage_export --run output/<timestamp>

# Asset generator (commit 11, no cableado aún)
python -m bridge.asset_generator --project OpenMontage/projects/<slug>

# Drivers one-off (legacy, reemplazar por asset_generator)
python OpenMontage/run_asset_director.py --project <slug>
python OpenMontage/train_lora.py --asset <id>
python OpenMontage/run_audio_director.py --project <slug>
python OpenMontage/run_edit_director.py --project <slug>
```

### 13.5 Archivos críticos de referencia

```
Guion_expert/
├── webapp/
│   ├── server.py                          (779 líneas — Flask + SocketIO)
│   ├── schemas/
│   │   ├── cinematic.py                   (394 líneas — Master Stack v2 Pydantic)
│   │   └── ...
│   └── integrations/
│       ├── fal.py                         (816 líneas — cliente fal.ai)
│       └── suno.py                        (548 líneas — cliente Suno self-host)
├── bridge/
│   ├── openmontage_export.py              (1705 líneas — handoff determinístico)
│   └── asset_generator.py                 (1013 líneas — orquestador, no cableado)
├── config/
│   └── config.py                          (318 líneas — Pydantic-settings)
├── INFORME_GUION_EXPERT.md                (56 KB — deep-dive del repo)
├── INFORME_HANDOFF_OM.md                  (47 KB — handoff Guion_expert ↔ OM)
├── PRD_PLATAFORMA_UNIFICADA.md            (61 KB — PRD r2 con multi-proveedor)
└── INFORME_MEMORIA_COMPLETA.md            (este archivo — consolidación)

OpenMontage/
├── cinematic.yaml                         (manifiesto agentic, 7 stages)
├── projects/3SM/
│   ├── stages/{brief,script,scene_plan,checkpoint,remotion-cuts}.json
│   └── output/FINAL_3SM_REEL.mp4          (9.4 MB, prueba e2e funcional)
├── run_asset_director.py                  (driver one-off)
├── train_lora.py                          (driver one-off)
├── run_audio_director.py                  (driver one-off)
└── run_edit_director.py                   (driver one-off)
```

### 13.6 Checklist de entrega del informe

- [x] Cubre las 4 piezas en memoria de la conversación.
- [x] Cita SHAs y line counts verificados contra los informes previos.
- [x] PRD ejecutivo + PRS técnico en una sola pieza.
- [x] Roadmap accionable en 3 fases.
- [x] Decisiones pendientes claramente listadas.
- [x] Glosario para onboarding rápido.
- [x] Variables de entorno y comandos para el dev que entra.
- [x] Cross-reference a los 3 informes previos sin duplicar contenido.

---

**Fin del informe.**

> Este documento es el punto único de entrada al proyecto. Para profundizar en un área específica, ir a:
> - **Repo Guion_expert** → `INFORME_GUION_EXPERT.md`
> - **Contrato handoff** → `INFORME_HANDOFF_OM.md`
> - **Plataforma comercial** → `PRD_PLATAFORMA_UNIFICADA.md`
> - **Síntesis y memoria de conversación** → este archivo
