# PRD — Plataforma Unificada Guion Studio

**Fusión Guion_expert ⊕ OpenMontage + UI/UX consumer + Ghost Agent**

**Fecha**: 2026-04-22 · **Revisión 2** (re-pipeline + unit economics realistas)
**Estado**: Research + Design
**Audiencia**: Producto, ingeniería, diseño
**Alcance**: Requerimientos producto, arquitectura multi-proveedor, plan de PRs
**Complementa**: `INFORME_GUION_EXPERT.md` (arquitectura interna), `INFORME_HANDOFF_OM.md` (contrato bridge)

> **Cambios r2 vs r1**: Eliminado Veo como modelo principal (caro y filtros bloquean productos). Sustituido fal.ai como único proveedor por estrategia multi-proveedor con routing por especialidad. Unit economics recalculadas con precios directos de API (fal.ai cobra +20-50% markup). Añadida §9.6 (routing por especialidad) y §16.6 (comparativa top-10 modelos).

---

## Índice

1. Visión del producto
2. Problema y mercado
3. Personas y jobs-to-be-done
4. User journey principal (happy path)
5. Features MVP (P0)
6. Features V2 (P1)
7. Features V3 (P2)
8. Concepto del "Ghost Agent"
9. Arquitectura propuesta (fusión + stack + **§9.6 routing por especialidad** + **§9.7 multi-proveedor**)
10. Decisiones técnicas clave (10 ADRs)
11. Requerimientos no-funcionales
12. Comparativa con competencia (Krea, Higgsfield, Runway, Pika)
13. Riesgos y mitigaciones
14. Métricas de éxito
15. Plan de PRs (sprints + atómicos)
16. Apéndices (incluye **§16.6 top-10 modelos comparativa**)

---

## 1. Visión del producto

**Guion Studio** es una plataforma de creación de videos con IA para emprendedores y creadores de contenido de e-commerce. El usuario sube **una selfie** + **una foto de su producto** (perfume, crema, plato de comida, ropa, etc.), escribe **una idea en español** ("quiero un reel mostrando mi perfume como un recuerdo de verano"), hace clic en **Generar**, y recibe un **video terminado** (1080×1920, 15-60 s, con música + SFX + consistencia de rostro y producto) listo para descargar y publicar en Instagram/TikTok.

Dos pipelines hoy separados — Guion_expert (guión) + OpenMontage (render) — se fusionan en un solo producto con una UI consumer y un orquestador backend ("Ghost Agent") que resuelve todo el workflow sin que el usuario vea artifacts intermedios.

### Tagline

> *"De la idea al reel, en 15 minutos, sin editor de video."*

### Propuesta de valor

| Para el usuario (emprendedor LATAM) | Para el negocio |
|---|---|
| No necesita saber editar video | Mercado LATAM mal atendido (tooling es en inglés) |
| Salida en español por default | Costo marginal por video: ~$1 (vs. $200-500 agencia) |
| Consistencia facial y de producto sin prompts técnicos | TAM: >5M emprendedores pymes en LATAM con producto físico |
| Descarga directa sin watermark en plan pago | Moat: pipeline narrativo en español + Master Stack v2 |

---

## 2. Problema y mercado

### Problema

Los emprendedores LATAM con productos físicos:

1. No pueden pagar agencia de video ($200-500/reel).
2. No saben editar (Premiere, Final Cut, CapCut les exceden).
3. Las herramientas AI existentes (Krea, Higgsfield, Runway, Pika) son **en inglés**, piden prompts técnicos ("cinematic, 85mm lens, golden hour"), y **no entienden narrativa** — solo generan clips sueltos.
4. Necesitan **consistencia**: el rostro en todas las escenas debe ser el suyo, el producto debe verse idéntico.

### Mercado

- **Sora 2 / Sora 2 Pro** sigue vivo (OpenAI) pero con filtros de contenido estrictos (bloquea productos, rostros de no-consentidos, branding) + waitlist API.
- **Kling 3.0** (Kuaishou, feb 2026) y **Veo 3.1** (Google) son los líderes de calidad; **Minimax Hailuo 02** es el líder de costo/volumen; **Runway Gen-4.5** (feb 2026) domina la consistencia de personaje con References.
- **Hunyuan Video 1.5** (Tencent) y **Wan 2.2** (Alibaba) + **LTX-Video 2.3** (Lightricks) son los open-source de calidad production-grade.
- Mercado global de AI video 2026: ~$2.4B. Agencias profesionales usan multi-model (Kling = hero, Hailuo = volumen, LTX = previews). Los usuarios amateur **no tienen una plataforma vertical para ellos**.
- Krea y Higgsfield son los más cercanos pero son "creative suites" generalistas: carecen de pipeline narrativo en español y de onboarding consumer.

### Posicionamiento

```
            Generalista
                │
  Krea ─────────┼───────── Higgsfield
                │
────────────────┼──────────────── (este cuadrante es donde vive Guion Studio)
                │                  • narrativa en español
  Runway ───────┼───────── Pika    • productos físicos LATAM
                │                  • onboarding 3-clicks
          Profesional            • sin prompts técnicos
```

---

## 3. Personas y jobs-to-be-done

### Persona A — Emprendedor LATAM (primary)

**Sofía, 34, dueña de marca de cremas artesanales en Bogotá.**

- Vende en Instagram + mercado de fin de semana.
- Factura $2,000/mes con 3 productos.
- No tiene equipo de marketing. Ella es fotógrafa, community manager y producción.
- Quiere 3-4 reels/semana pero solo alcanza a hacer 1 (cuesta ~4 horas).

**Jobs-to-be-done**:
- Cuando lanzo un producto nuevo, quiero un reel aspiracional en 15 min para publicar hoy.
- Cuando agoto un stock, quiero un reel de "últimas unidades" sin rediseñar todo.

### Persona B — Músico / Banda (secundary)

**Leo, 40, bajista de 3SM (banda cover de Concepción).**

- Ya tocó el uso real (el reel del proyecto 3SM — 9.4 MB, 52s).
- Necesita promocionar shows en Instagram.
- El producto no es físico — es una performance.

**Jobs-to-be-done**: narrativa cinematográfica con intriga, no un clip suelto.

### Persona C — Chef / Restaurante (tertiary, V2+)

Plato de comida como "producto". Necesita foto del plato + frase ("mi arepa con queso costeño como la recuerda tu abuela") → reel con close-ups cinematográficos del plato.

---

## 4. User journey principal (happy path MVP)

```
 ┌────────────────────────────────────────────────────────────────────┐
 │                          LANDING / LOGIN                           │
 │   Hero: "Tu producto, un reel, 15 minutos."                       │
 │   CTA: Empezar gratis (3 reels/mes sin watermark)                 │
 └────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │                    STEP 1 — SUBIR SELFIE (30s)                     │
 │                                                                    │
 │   [📸 Drag & drop tu selfie]   o   [Toma una foto ahora]          │
 │                                                                    │
 │   Preview circular + "Esta será tu imagen en el video."           │
 │   Opcional: "Subir 5-10 fotos más" → activa entrenamiento LoRA    │
 │   (más consistencia, +3 min de espera)                             │
 │                                                                    │
 │                                             [Siguiente →]          │
 └────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │                  STEP 2 — SUBIR PRODUCTO (30s)                     │
 │                                                                    │
 │   [📦 Drag & drop foto de tu producto]                             │
 │   Categoría: [Perfume ▼] [Crema] [Comida] [Ropa] [Otro]           │
 │   Nombre: "Crema de calendula Fenix"                               │
 │                                                                    │
 │   Preview + "Esto aparecerá en cada escena."                      │
 │                                                                    │
 │   [← Atrás]                                 [Siguiente →]          │
 └────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │                  STEP 3 — TU IDEA (60s)                            │
 │                                                                    │
 │   ┌───────────────────────────────────────────────────────────┐   │
 │   │  Contá qué sentís con tu producto...                      │   │
 │   │                                                           │   │
 │   │  [Ejemplos: "quiero mostrar mi crema como un recuerdo de  │   │
 │   │  la playa donde fui con mi abuela"]                       │   │
 │   └───────────────────────────────────────────────────────────┘   │
 │                                                                    │
 │   Formato: ◉ Reel Instagram (30s)  ○ TikTok (60s)  ○ Story (15s) │
 │   Tono:    ◉ Cinematográfico       ○ Divertido    ○ Intrigante   │
 │                                                                    │
 │   [← Atrás]                               [🎬 Generar video]       │
 └────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │                  STEP 4 — GENERANDO (5-15 min)                     │
 │                                                                    │
 │   ●────●────●────●────○    (progress bar en 5 fases)              │
 │   Guión  Escenas  Arte  Video  Listo                               │
 │                                                                    │
 │   🎥 Escribiendo el guión en español...    [✓]                     │
 │   🖼️  Generando la escena 1 de 4 con FLUX...                       │
 │   🎬 Animando escena 1 a video...                                  │
 │   🎵 Componiendo la música hero...                                 │
 │   🔊 Añadiendo sonido diegético...                                 │
 │                                                                    │
 │   Estimado: 8 min restantes.  Podés cerrar esta página; te       │
 │   avisamos por email cuando esté listo.                           │
 └────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │                  STEP 5 — VER + DESCARGAR                          │
 │                                                                    │
 │   ┌──────────────────────────────────────┐                        │
 │   │                                      │                        │
 │   │        [▶ Video player 9:16]         │                        │
 │   │                                      │                        │
 │   └──────────────────────────────────────┘                        │
 │                                                                    │
 │   [⬇ Descargar MP4]   [📱 Compartir a IG]   [🔄 Rehacer con cambios]│
 │                                                                    │
 │   ¿No te gustó algo? "Cambiar color dominante a azul"              │
 │                                                                    │
 └────────────────────────────────────────────────────────────────────┘
```

---

## 5. Features MVP (P0)

### Upload wizard 3 pasos

- U-01: upload de selfie con preview (JPG/PNG/WebP, max 10 MB).
- U-02: upload de producto + categoría + nombre.
- U-03: idea en texto libre (español, 20-500 chars) + formato + tono.

### Ghost Agent orquestador

- G-01: crea un `job_id` y dispara el workflow completo (guión → escenas → assets → render).
- G-02: progress streaming vía SSE (Server-Sent Events, elegido sobre WebSocket — ver § 10 ADR-03).
- G-03: persistencia del job en Postgres; resumable tras reinicio.
- G-04: budget cap por usuario ($3/reel en MVP).

### Generación de video (routing por especialidad — ver §9.6)

- V-01: **FLUX.2 Pro** (Black Forest Labs) vía Replicate para frames ancla — I2V-ready.
- V-02: **FLUX.2 LoRA fast training** opcional (≥5 fotos) → `<trigger>` del usuario. Se cachea 30 días.
- V-03: **Minimax Hailuo 02 Fast** (direct API) como modelo **volumen** de I2V (~$0.017/s).
- V-04: **Kling 2.1 Master** vía **Atlas Cloud** (-29% vs direct) como modelo **hero** de I2V (~$0.07/s all-in) — solo en tomas climax que paga el plan Pro.
- V-05: **LTX-Video 2.3** self-hosted (RunPod H100 spot) como **preview** en wizard (<5s latencia).
- V-06: **MMAudio v2** (self-hosted o Replicate) para foley diegético sincronizado.
- V-07: **Suno v5** (API reseller a $0.03/canción) para música hero 30s.
- V-08: **Cartesia Sonic-3** para TTS en español (5× más barato que ElevenLabs, calidad par).
- V-09: **LatentSync 1.6** (self-host) para lip-sync si la toma habla.
- V-10: **moviepy** concat + libx264/aac → MP4 1080×1920. Upscale opcional vía Topaz Replicate solo en plan Pro.

### Player + descarga

- P-01: video player HTML5 inline.
- P-02: botón descarga MP4 directo (signed URL).
- P-03: share links a IG/TikTok (deep link en V2).

### Auth + billing

- A-01: login con email + magic link (passwordless).
- A-02: plan free (3 reels/mes + watermark opcional).
- A-03: plan pro ($19/mes, 30 reels + sin watermark).
- A-04: Stripe subscription + webhooks.

### Library

- L-01: lista de reels pasados del usuario.
- L-02: re-run con cambios (cambiar color, tono, sin re-subir fotos).
- L-03: delete con confirmación.

---

## 6. Features V2 (P1) — post-MVP

- **Fine-control camera**: UI para seleccionar `dolly_in`, `handheld`, etc. (vocabulario OpenMontage `shot_language`).
- **Style presets**: "Estilo Wong Kar-Wai", "Estilo Ghibli", "Estilo brutalist techno" (mapa a `style_playbook`).
- **Multi-producto**: subí 3 productos para un carousel reel.
- **Series**: 3-4 reels con misma estética (LoRA compartida) = campaña.
- **Voice-over**: TTS con clonación de voz del usuario (ElevenLabs).
- **Subtítulos automáticos**: whisperX + overlay estilo Instagram.
- **A/B hooks**: 3 variantes del primer segundo, métrica de CTR real en IG.
- **Brand kit**: paleta + tipografía persistente para la cuenta.

---

## 7. Features V3 (P2) — moonshots

- **Render directamente a IG/TikTok** (OAuth + API publishing).
- **Marketplace de style playbooks** (creadores venden sus estéticas).
- **Feedback loop con performance en IG** (reels que rindieron mejor → ajuste del prompt narrativo).
- **Live editing** (rehacé una escena específica sin regenerar todo).
- **Multi-idioma salida** (inglés, portugués BR, francés).
- **Avatar 3D persistente** (Gaussian splatting del usuario, no solo LoRA 2D).

---

## 8. Concepto del "Ghost Agent"

El Ghost Agent es el **orquestador backend** que une los dos pipelines hoy separados. Se llama "fantasma" porque el usuario **nunca lo ve** — solo ve la barra de progreso y el video final. Todo lo que hoy es manual (bridge export, drivers Python, edit final) lo hace el Ghost Agent solo.

### Responsabilidades

1. **Ingestar inputs**: recibe selfie + producto + idea + formato del frontend.
2. **Disparar Guion_expert**: crea un job "generar guión" que produce `output/<id>/` con la narrativa.
3. **Disparar bridge.openmontage_export**: convierte a artifacts JSON de OpenMontage.
4. **Disparar bridge.asset_generator**: renderiza FLUX + I2V + SFX + música con budget tracker.
5. **Disparar compose final**: concat con moviepy → MP4 final.
6. **Upload a storage**: sube el MP4 a S3/R2 → signed URL al frontend.
7. **Notificar**: emite SSE "job_completed" + email opcional.

### Arquitectura del Ghost Agent

```
┌─────────────────── FastAPI ───────────────────┐
│  POST /api/jobs  →  crea job, encola tarea    │
│  GET /api/jobs/:id/stream  →  SSE progress    │
│  GET /api/jobs/:id  →  estado + result URL    │
└────────────────┬──────────────────────────────┘
                 │ enqueue
                 ▼
┌─────────────── ARQ worker pool ───────────────┐
│                                               │
│  job_orchestrator(job_id):                    │
│    state = load_state(job_id)                 │
│    if not state.script:      run_guion()      │
│    if not state.scene_plan:  run_bridge()     │
│    if not state.assets:      run_asset_gen()  │
│    if not state.mp4:         run_compose()    │
│    publish_result()                           │
│                                               │
│  ↓ idempotente, cada paso checkpointea        │
│  ↓ retries automáticos con exponential backoff│
│  ↓ cada paso emite SSE vía Redis pub/sub      │
└───────────────────────────────────────────────┘
                 │
                 ▼
         PostgreSQL (job state) + Redis (queue + pubsub) + S3 (assets)
```

### Por qué "ghost" y no solo "orchestrator"

- No tiene UI propia — el usuario no habla con el agente, solo con la wizard.
- Es resiliente: si el backend reinicia, el agente reanuda desde el último checkpoint.
- Es **idempotente por diseño** (cada step verifica si su output ya existe antes de ejecutar).
- En V2+, un LLM puede vivir dentro del agente para decidir retries inteligentes ("Kling falló con duración 10s, retry con 5s").

### LLM opcional en el Ghost Agent (V2)

Hoy la orquestación es determinista (if/else). En V2 se puede injertar Claude Haiku como "operador" que decida:

- Cuándo re-prompt un FLUX que salió borroso.
- Cuándo hacer fallback de Kling → Runway si el primer modelo timeout.
- Cuándo sugerir al usuario cambiar el producto o la idea si el pipeline detecta ambigüedad.

Esto usa el patrón **"agent loop"** de Anthropic tool-use con `tool_choice={"type":"any"}`.

---

## 9. Arquitectura propuesta (fusión + stack)

### 9.1 Estrategia de fusión

**Opción recomendada**: **monorepo con servicios independientes** bajo `guion-studio/` usando **pnpm workspaces** + **uv** (Python). Ni fusión atómica (demasiado grande) ni seguir dos repos (cero sinergia).

```
guion-studio/                      # monorepo root
├── apps/
│   ├── web/                       # Next.js 15 frontend (app router + RSC)
│   ├── api/                       # FastAPI + ARQ worker
│   └── ghost-agent/               # orchestrator daemon (Python)
├── packages/
│   ├── guion-expert/              # ex-Guion_expert (Python lib ahora)
│   ├── openmontage/               # ex-OpenMontage (Python lib)
│   ├── bridge/                    # ex-bridge/ (ya existe)
│   ├── ui/                        # shadcn/ui + Tailwind kit compartido (TS)
│   └── types/                     # TS types + Pydantic cross-boundary
├── infra/
│   ├── docker-compose.yml         # desarrollo local (web + api + redis + postgres + minio)
│   ├── Dockerfile.api
│   ├── Dockerfile.web
│   └── terraform/                 # Hetzner/Fly.io IaC
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   └── RUNBOOK.md
├── pnpm-workspace.yaml
├── pyproject.toml                 # uv workspace Python
└── README.md
```

**Por qué monorepo y no microservicios independientes**:

- Contratos (Pydantic + TS types) se comparten vía `packages/types/`.
- Un solo pipeline CI para todo.
- Deploys atómicos: una versión del frontend coincide siempre con una versión del backend.
- Developer experience: `pnpm dev` levanta todo.

**Por qué no fusionar en un solo paquete Python**:

- Guion_expert y OpenMontage tienen responsabilidades distintas (narrativa vs. render).
- Mantener el bridge explícito es un **feature**, no un bug — permite swappear OpenMontage por otro renderer (Remotion standalone, por ejemplo) sin re-escribir Guion_expert.

### 9.2 Stack técnico

| Capa | Tecnología | Razón |
|---|---|---|
| **Frontend** | Next.js 15 (App Router, RSC) + React 19 | SEO + streaming + patrón BFF nativo |
| **Styling** | Tailwind CSS v4 + shadcn/ui | consistencia + velocidad |
| **State client** | TanStack Query + Zustand | async + simple |
| **File upload** | UploadThing o S3 presigned + multipart | <10s para 10 MB selfie |
| **Real-time** | **SSE** (Server-Sent Events) | simplicidad > WebSocket (ADR-03) |
| **API** | **FastAPI** (reemplaza Flask) | async-nativo, OpenAPI, Pydantic |
| **Background jobs** | **ARQ** (no Celery) | async-nativo, menos boilerplate |
| **Queue** | Redis 7 | ARQ lo usa nativo; pub/sub para SSE |
| **DB** | PostgreSQL 16 | jobs + usuarios + billing |
| **ORM** | SQLModel | unifica Pydantic + SQLAlchemy |
| **Auth** | Clerk o NextAuth v5 | magic links + social |
| **Billing** | Stripe Billing + webhooks | standard del mercado |
| **Object storage** | R2 (Cloudflare) o S3 | costo-eficiente para MP4s |
| **AI video (volumen)** | Minimax Hailuo 02 Fast (API directa) | $0.017/s, líder costo/calidad |
| **AI video (hero)** | Kling 2.1 Master vía Atlas Cloud | -29% vs direct, líder motion |
| **AI video (preview)** | LTX-Video 2.3 self-host en RunPod H100 spot | real-time, ~$2/hr pod |
| **AI image / LoRA** | FLUX.2 Pro + LoRA via Replicate | $0.05/img, $2-5/LoRA |
| **AI audio música** | Suno v5 via reseller / Premier plan | $0.03/canción |
| **AI audio TTS** | Cartesia Sonic-3 | 5× más barato que ElevenLabs |
| **AI audio SFX** | MMAudio v2 (self-host o Replicate) | líder V2A sync |
| **AI LLM (narrativa)** | Anthropic Claude Haiku 4.5 | ya cableado en Guion_expert |
| **Observability** | structlog + Sentry + Grafana Cloud | ya hay structlog en Guion_expert |
| **Deploy** | Hetzner CX22 (api) + Cloudflare Pages (web) + RunPod H100 spot (GPU self-host) | costo <$60/mes infra MVP |
| **CI/CD** | GitHub Actions + turbo | standard, cache |

### 9.3 Data model (Postgres)

```sql
-- Users
users (id uuid pk, email text unique, stripe_customer_id text, plan text, created_at timestamptz)

-- Project (un reel)
projects (
  id uuid pk,
  user_id uuid fk,
  idea text,
  format text,              -- REEL_INSTAGRAM, YOUTUBE_SHORT, ...
  tone text,                -- cinematic, playful, intriguing
  selfie_url text,
  product_url text,
  product_category text,
  product_name text,
  lora_dataset_urls text[], -- si subió múltiples fotos
  created_at timestamptz
)

-- Job (ejecución del pipeline)
jobs (
  id uuid pk,
  project_id uuid fk,
  state text,               -- queued, running, completed, failed, cancelled
  current_step text,        -- guion, bridge, assets, compose, upload
  progress_pct int,
  total_cost_usd decimal,
  result_mp4_url text,
  error_message text,
  started_at timestamptz,
  completed_at timestamptz,
  metadata jsonb            -- scene_plan, asset_manifest paths dentro del storage
)

-- Assets (cada archivo generado)
assets (
  id uuid pk,
  job_id uuid fk,
  type text,                -- flux_image, kling_video, foley, music, final_mp4
  scene_id text,
  path text,                -- s3://... o ruta storage
  cost_usd decimal,
  model text,               -- flux-pro-1.1, kling-2.5-pro, ...
  duration_seconds decimal,
  created_at timestamptz
)
```

### 9.4 Flujo end-to-end concreto

```
1. Usuario completa wizard → POST /api/projects
   Frontend: sube selfie + producto a R2 vía presigned PUT.
   Backend: crea row en projects, devuelve project_id.

2. Usuario click "Generar" → POST /api/jobs {project_id}
   Backend: crea row en jobs (state=queued), encola arq_job("run_pipeline", job_id).
   Devuelve job_id + URL SSE.

3. Frontend abre EventSource(`/api/jobs/{job_id}/stream`)
   Recibe eventos: "step_started" { step: "guion" }, "progress" { pct: 12 },
                   "step_completed", "job_completed" { mp4_url: "..." }.

4. ARQ worker ejecuta ghost_agent.run_pipeline(job_id):
   a. State.step=guion     → Guion_expert.run_full_pipeline(project.idea, format)
                              → /tmp/output/{id}/
   b. State.step=bridge    → bridge.export_project_to_openmontage(tmp_dir, om_root)
                              → /tmp/openmontage/projects/{pid}/stages/*.json
   c. State.step=lora      → if len(project.lora_dataset_urls) >= 5:
                                 fal.submit("flux-lora-fast-training", ...) → lora_url
   d. State.step=assets    → bridge.asset_generator.generate_all_assets(
                                 scene_plan_path, budget=3.00, lora_url=lora_url)
                              → assets/{scene_id}-{flux,video,foley}.*
   e. State.step=compose   → moviepy concat → {job_id}-final.mp4
   f. State.step=upload    → R2.put_object(final_mp4) → signed_url
   g. State.completed      → UPDATE jobs SET state='completed', result_mp4_url=...
                              pubsub "job:{id}" message "job_completed"

5. SSE stream del paso 3 recibe "job_completed" → frontend muestra player + descarga.
```

### 9.5 Decisiones de desarrollo

- **Migración Flask → FastAPI**: incremental. Se empieza con rutas nuevas en FastAPI y se van portando las viejas en orden de uso.
- **UI vieja**: deprecarla en favor del Next.js. Se conserva como admin-only.
- **Bridge**: promocionado a paquete `@guion-studio/bridge` (npm) con types compartidos + `guion_studio.bridge` (PyPI).
- **Tests**: stack con pytest + vitest + Playwright E2E (nuevo — hoy hay 0).

### 9.6 Routing por especialidad (matriz de modelos)

**Principio**: ningún modelo domina en todo. El Ghost Agent decide **por tipo de escena + tier del usuario** qué proveedor disparar. Esta matriz es la **única fuente de verdad** para `packages/bridge/router.py`.

| Rol en el pipeline | Modelo recomendado | Proveedor más barato | Precio real | Racional |
|---|---|---|---|---|
| **Frame ancla (I2V start)** | FLUX.2 Pro | Replicate direct | ~$0.05/img | Mejor balance foto-realismo + I2V-warming. No usar fal (markup 20%). |
| **Hero shot (climax, Pro tier)** | Kling 2.1 Master | Atlas Cloud reseller | ~$0.07/s → $0.35/5s | Mejor motion/física del mercado. Atlas Cloud -29% vs direct. |
| **Volume shots (resto de escenas)** | Minimax Hailuo 02 Fast | Minimax direct API | $0.017/s → $0.10/6s | 9/10 en costo, 8/10 en calidad. No tiene markup via direct. |
| **Preview en wizard (loop iterativo)** | LTX-Video 2.3 | Self-host RunPod H100 spot | ~$0.002/clip | Real-time en H100. Preview <5s antes de comprometerse al render. |
| **Consistencia de personaje (V2+)** | Runway Gen-4.5 References | Runway direct | $0.15/s → $0.75/5s | Único con 3-ref images nativo. Usar solo en plan Enterprise. |
| **Producto con reflejos/textura** | Wan 2.2 S2V | Self-host 8-24GB VRAM | ~$0.01/clip | One-shot subject lock ideal para perfumes/cremas/platos. |
| **Dialogue + audio sincronizado** | Veo 3.1 Fast (opcional) | Vertex AI direct | $0.10-0.15/s | Solo si el guión tiene voice-over diegético. No default (censor + precio). |
| **LoRA training** | FLUX.2 Klein 9B LoRA | fal-ai/flux-lora-fast-training | $2-5 por LoRA (one-time) | Se amortiza en 50+ reels del mismo usuario. |
| **Image-to-image / subject ref** | OmniGen2 o IP-Adapter FaceID v2 | Replicate | $0.04/img | Alternativa a LoRA para usuarios 1-shot. |
| **Música 30s** | Suno v5 | sunoapi.org reseller / Premier plan | ~$0.03/canción | Udio $10/mo flat también viable. Self-host no compite. |
| **TTS / voice-over** | Cartesia Sonic-3 | Cartesia direct | $0.006/min → ~$0.003/reel | **5× más barato** que ElevenLabs Flash. Calidad española par. |
| **Foley / sound FX** | MMAudio v2 | Self-host o Replicate | ~$0.01/clip | Líder V2A, 1.23s latencia, sync perfecto. |
| **Lip-sync (si habla)** | LatentSync 1.6 | Self-host | ~$0.02/clip | Mejor ID preservation. Sieve Sonic ($0.10) es el fallback comercial. |
| **Upscale 1080p→4K (Pro tier)** | Topaz Video AI | Replicate `topazlabs/video-upscale` | $0.04/s → $1.20/30s | Solo habilitado en plan Pro + add-on "Cinematic". |
| **Frame interpolation** | RIFE v4.22 | Self-host / fal | ~$0.001/frame | Opcional. Eleva 24fps → 60fps sin costo perceptible. |

**Reglas del router** (`packages/bridge/router.py`):

```python
def pick_video_model(scene, user_tier):
    if user_tier == "free":
        return "hailuo-02-fast"                    # todos los clips
    if scene.role == "hero":
        return "kling-2.1-master" if scene.has_motion else "veo-3.1-fast"
    if scene.subject_type == "product":
        return "wan-2.2-s2v"                       # specular/textura
    return "hailuo-02-fast"                        # default
```

**Fallback chains** (cada modelo tiene un sustituto en caso de error/timeout):

- Kling Master → Hailuo 02 Pro → LTX-2.3
- FLUX.2 Pro → FLUX.2 Dev → SDXL
- Suno → Udio → Stable Audio 2.5
- Cartesia → ElevenLabs Flash → OpenAI TTS-1-HD

### 9.7 Estrategia multi-proveedor (no single vendor lock-in)

El sistema **no depende de fal.ai**. Cada capability tiene ≥2 providers configurables vía YAML:

```yaml
# packages/bridge/config/providers.yaml
video:
  hailuo-02-fast:
    primary: minimax_direct
    fallback: [atlas_cloud, fal]
  kling-2.1-master:
    primary: atlas_cloud          # -29% vs direct
    fallback: [kling_direct, piapi]
  ltx-2.3:
    primary: runpod_self_host
    fallback: [fal]
image:
  flux-2-pro:
    primary: replicate
    fallback: [fal, black_forest_direct]
audio:
  suno-v5:
    primary: sunoapi_reseller
    fallback: [udio]
  cartesia-sonic:
    primary: cartesia_direct
    fallback: [elevenlabs_flash]
```

Ventajas: (1) sobrevivir outages de un provider, (2) arbitraje de precios continuo, (3) cumplir GDPR/residencia de datos según región (Atlas Cloud EU, Runway US, etc.), (4) cero vendor lock-in.

---

## 10. Decisiones técnicas clave (ADRs)

### ADR-01: Monorepo (turborepo/pnpm + uv) vs multi-repo

**Decisión**: Monorepo.
**Contexto**: 3 apps (web, api, ghost-agent) + 5 packages.
**Consecuencias**:
- ✅ Tipos Pydantic ↔ TS se mantienen sincronizados.
- ✅ Un solo CI pipeline.
- ⚠️ Herramientas: turbo para Node; uv workspaces para Python; requiere ambas.

### ADR-02: FastAPI vs mantener Flask

**Decisión**: FastAPI, migración gradual.
**Contexto**: webapp actual es Flask + Flask-SocketIO (vanilla, 1 HTML + 1 JS file).
**Consecuencias**:
- ✅ Async-nativo (el pipeline hace I/O: fal, Suno, S3).
- ✅ OpenAPI auto-generado → frontend genera cliente TS tipado.
- ✅ Pydantic compartido con Guion_expert (ya lo usa).
- ⚠️ Costo de migración: ~2 semanas (2 desarrolladores).

### ADR-03: SSE vs WebSocket para progress streaming

**Decisión**: **SSE** (Server-Sent Events).
**Contexto**: el usuario solo **recibe** updates de progreso. No envía nada al backend durante el render.
**Consecuencias**:
- ✅ Más simple: texto plano sobre HTTP, reconexión automática del navegador.
- ✅ Atraviesa proxies y firewalls como HTTP normal.
- ✅ Compatible con Cloudflare sin config extra (WebSocket requiere plan pago).
- ⚠️ Si en V2+ se necesita bidirección (ej. "pausa el render"), se sube a WebSocket.
- Alternativa considerada: Flask-SocketIO actual. Descartada por bundle JS innecesariamente grande.

### ADR-04: ARQ vs Celery para background jobs

**Decisión**: **ARQ**.
**Contexto**: ARQ es async-nativo; Celery pre-fecha async-python.
**Consecuencias**:
- ✅ Fits FastAPI (no shim de sync/async).
- ✅ Menos moving parts (no beat scheduler separado).
- ✅ Redis-only (no rabbit + backend).
- ⚠️ Comunidad más chica; menos plugins third-party.

### ADR-05: Next.js + RSC vs SPA tradicional

**Decisión**: **Next.js 15 con App Router + RSC**.
**Contexto**: patrón dominante 2026 según research (JetBI, dev.to).
**Consecuencias**:
- ✅ SEO por default (landing + marketing pages).
- ✅ Streaming de componentes React directo desde el BFF.
- ✅ Edge functions de Cloudflare Pages → TTFB ~50ms LATAM.
- ⚠️ Mental model más complejo para devs sin exposición previa.

### ADR-06: Persistent state para jobs (Postgres) vs Redis-only

**Decisión**: Postgres como source of truth; Redis como caché + queue.
**Contexto**: los jobs tardan 5-15 min. Si Redis cae, no se pierde trabajo.
**Consecuencias**:
- ✅ Sobrevive reinicios, migrations.
- ✅ Queries de admin sobre histórico.
- ⚠️ Doble write en el worker (Redis + PG) — manejado con outbox pattern.

### ADR-07: LoRA training on-demand vs pre-trained

**Decisión**: On-demand, solo si el usuario sube 5+ fotos.
**Contexto**: FLUX.2 Klein 9B LoRA fast training cuesta ~$2-5 y tarda 12-15 min en H100.
**Consecuencias**:
- ✅ Usuario ocasional (1 selfie) salta LoRA → 8 min total render, $1.50 costo.
- ✅ Usuario pro (dataset) obtiene consistencia perfecta → 23 min total, +$3.
- ✅ LoRA se cachea por `user_id` por 30 días; hit-rate >80% en reels 2-N.
- ⚠️ Primer reel paga la LoRA; segundo en adelante la reusa (amortización real: $3/50 reels ≈ $0.06/reel).

### ADR-08: Routing multi-proveedor (no vendor lock-in)

**Decisión**: **Strategy pattern** con YAML de providers (ver §9.7). El router elige el más barato disponible y tiene fallback chain.
**Contexto**: En la revisión 1, todo dependía de fal.ai (+20-50% markup y single point of failure). Usuario reportó $40 en 4 reels (~$10/reel) con stack fal+Veo.
**Consecuencias**:
- ✅ -40-60% en costo variable vs fal.ai-only.
- ✅ Sobrevive outages: si Minimax cae, el router usa Atlas Cloud.
- ✅ Arbitraje de precios continuo (cron job detecta si Replicate bajó más que fal).
- ⚠️ Más secretos que rotar (8 providers). Manejado con Infisical/Vault.
- ⚠️ Homogeneizar respuestas exige un adapter por provider (~50 LoC cada uno).

### ADR-09: Specialty routing por tipo de escena

**Decisión**: El Ghost Agent elige modelo por `scene.role` (`hero`/`volume`/`preview`) + `scene.subject_type` (`character`/`product`/`scene`) + `user_tier` (ver §9.6).
**Contexto**: Ningún modelo gana en todo. Kling es 10/10 motion pero 7/10 costo; Hailuo es 9/10 costo pero 8/10 motion; Wan S2V es perfecto producto pero débil en movimiento.
**Consecuencias**:
- ✅ Free tier 100% Hailuo 02 Fast → costo/reel <$0.80.
- ✅ Pro tier usa Kling Master solo en 1-2 "hero shots" del climax → experiencia premium sin romper margen.
- ✅ Add-on "Cinematic" ($0.99) desbloquea Kling en todas las escenas + upscale Topaz.
- ⚠️ Requiere que Guion_expert etiquete `scene.role` en el scene_plan (ya casi existe vía `is_climax`).

### ADR-10: Remoción de Veo 3.1 del default stack

**Decisión**: Veo sólo se dispara en casos con dialogue diegético (opt-in en V2+).
**Contexto**: Veo 3.1 standard con audio = $0.35-0.50/s ($10-15 por un reel de 30s — insostenible). Además Google bloquea productos de marca, cosméticos y escenas "realistas" con heurísticas estrictas.
**Consecuencias**:
- ✅ Costo por reel baja de ~$10 a ~$1.50-2.00.
- ✅ Evita falsos positivos del content filter (mayoría de nuestros productos son cosmetics/food).
- ⚠️ Para reels que explícitamente requieren voz-en-escena, ofrecemos Veo 3.1 Fast como add-on premium ($2 extra).

---

## 11. Requerimientos no-funcionales

| Dimensión | Target MVP | Target V2 |
|---|---|---|
| **Latency wizard → "generando"** | <500ms | idem |
| **Tiempo render total** | <15 min p95 | <10 min p95 |
| **Costo por reel (free tier)** | <$0.80 | <$0.50 (LTX self-host al 100%) |
| **Costo por reel (pro tier)** | <$2.00 | <$1.50 (LoRA cache + arbitraje providers) |
| **Costo por reel (add-on Cinematic)** | <$4.50 | <$3.50 |
| **Concurrent jobs** | 10 simultáneos | 100 |
| **Disponibilidad** | 99.0% | 99.5% |
| **Datos personales** | selfies cifradas en reposo (R2 SSE-S3) | GDPR-compliant right-to-delete |
| **i18n** | ES (default), EN (opcional UI) | ES + PT-BR + EN |
| **Accessibility** | WCAG AA en wizard | AAA landing |
| **Security** | CSRF, rate limiting, file type validation | SOC2 type I |

---

## 12. Comparativa con competencia

| Capability | Guion Studio (target) | Krea | Higgsfield | Runway | Pika |
|---|---|---|---|---|---|
| Pipeline narrativo (idea → guión → escenas) | ✅ (Master Stack v2, es) | ❌ | ◐ (Click-to-Ad beta) | ❌ | ❌ |
| Consistencia facial (LoRA on-demand) | ✅ | ✅ | ✅ | ✅ Gen-4 Character | ❌ |
| Consistencia de producto | ✅ (escena + LoRA producto) | ✅ (product training) | ✅ | ◐ | ❌ |
| Onboarding 3-clicks | ✅ | ❌ (creative suite) | ❌ | ❌ | ❌ |
| Idioma español nativo | ✅ | ❌ | ❌ | ❌ | ❌ |
| Render con música + SFX | ✅ (Suno + MMAudio sincronizado) | ◐ | ◐ | ✅ (Veo 3.1 integrado) | ◐ |
| Formato vertical 9:16 default | ✅ | ✅ | ✅ | ✅ | ✅ |
| Descarga sin watermark | ✅ (plan pago) | ✅ | ✅ | ✅ | ✅ |
| Multi-proveedor sin vendor lock | ✅ (router §9.7) | ❌ | ❌ | ❌ | ❌ |
| Costo variable por reel | **$0.80-$2.00** (routing barato) | usa Kling/Veo a precio directo + markup plataforma | similar | similar | similar |
| Precio al usuario | Free 3/mes · Pro $19/mes 30 reels · add-on Cinematic $0.99 | $10-30/mes créditos | $9-49/mes créditos | $15-95/mes créditos | $10-70/mes créditos |

**Diferenciador principal**: pipeline narrativo en español + wizard consumer 3-pasos. Krea/Higgsfield asumen usuario que entiende "prompt + end frame + model selector". Guion Studio asume cero conocimiento técnico.

---

## 13. Riesgos y mitigaciones

| Riesgo | Impacto | Probabilidad | Mitigación |
|---|---|---|---|
| Provider principal (ej. Minimax) cambia precio o cae | medio | medio | router §9.7 tiene fallback chain por capability; arbitraje automático cada 24h |
| Atlas Cloud pierde el descuento de Kling | bajo | medio | fallback a direct Kling (+29%) o a Piapi; alerta en dashboard admin |
| RunPod H100 spot se acaba | bajo | bajo | fallback a on-demand ($2.69/hr) o Replicate hosted |
| LoRA training falla por mala foto del usuario | medio | alto | validación upload (resolución mínima, no blur); ofrecer fallback sin LoRA |
| Render tarda >15 min → usuario abandona | alto | medio | email/push notification cuando está listo; permite cerrar tab |
| Abuso (deepfakes, contenido prohibido) | crítico | alto | moderación automática en upload + TOS agresivo + watermark invisible |
| Contenido copyright (música Suno cover bands) | medio | medio | disclaimers; opción "sin música" |
| Runway/Veo compiten con vertical | alto | alto | moat: ES + narrativa + onboarding; no competimos en generalista |
| Costos escalan lineal con volumen | alto | bajo | batch + LoRA cache + degradar a I2V más barato para free tier |
| Dependencia de Guion_expert (LLM) | medio | bajo | abstracción `llm_provider.yaml` ya permite swap Anthropic ↔ OpenAI |

---

## 14. Métricas de éxito

### MVP (3 meses post-launch)

- 1,000 usuarios registrados (org) acquired vía redes + early access.
- 300 reels generados/mes (de los 3,000 disponibles en plan free).
- 10% conversion free → pro ($19/mes).
- NPS ≥ 40.
- Churn mensual ≤ 8%.
- Tiempo promedio render ≤ 10 min p50.
- Costo unit economics: CAC ≤ $15, LTV ≥ $60 (3 meses).

### V2 (6 meses)

- 10,000 usuarios.
- 5,000 reels/mes.
- 20% conversion free → pro.
- Expansión a PT-BR.
- Integración Instagram publishing (OAuth).

---

## 15. Plan de PRs (sprints atómicos)

Cada PR es ≤400 líneas de diff, cerrable en 1-3 días. Numeración `NNNN` por sprint (`0NNN` = sprint 0, `1NNN` = sprint 1, etc.).

### Sprint 0 — Fundación (semana 1)

| PR | Título | Output | Tests |
|---|---|---|---|
| #0001 | `chore: crear monorepo guion-studio con pnpm + uv workspaces` | estructura base, README | `pnpm build` pasa |
| #0002 | `infra: docker-compose dev stack (postgres + redis + minio)` | 1 comando levanta todo local | healthcheck responde en <30s |
| #0003 | `chore: mover Guion_expert → packages/guion-expert/` | imports actualizados, tests verdes | CI pasa igual que antes |
| #0004 | `chore: mover OpenMontage → packages/openmontage/` | idem | CI pasa |
| #0005 | `chore: mover bridge/ → packages/bridge/` | idem | `python -m bridge.asset_generator --help` ok |

### Sprint 1 — Backend fusion (semanas 2-3)

| PR | Título | Output | Tests |
|---|---|---|---|
| #0101 | `feat(api): FastAPI skeleton + /api/health` | `apps/api/`, uvicorn corre | e2e: GET /api/health = 200 |
| #0102 | `feat(api): Pydantic models Project/Job/Asset + SQLModel` | schema PG auto-migrate | pytest cobertura >80% |
| #0103 | `feat(api): POST /api/uploads/presign (R2 presigned PUT)` | frontend puede subir directo a R2 | integración con MinIO en CI |
| #0104 | `feat(api): POST /api/projects + CRUD básico` | crear/listar proyectos con auth stub | pytest |
| #0105 | `feat(api): POST /api/jobs + ARQ integration` | encola job, no ejecuta aún | pytest con arq mock |
| #0106 | `feat(api): GET /api/jobs/:id/stream (SSE endpoint)` | cliente recibe heartbeats + eventos test | integración con EventSource en navegador |
| #0107 | `feat(ghost-agent): skeleton del orchestrator (pasos mock)` | async def run_pipeline(job_id): 6 steps mockeados | pytest |
| #0108 | `feat(ghost-agent): paso 1 - dispara Guion_expert` | consume project, llama a `run_full_pipeline`, graba output_dir | integración con fixture project |
| #0109 | `feat(ghost-agent): paso 2 - dispara bridge.export` | llama `export_project_to_openmontage` | integración |
| #0110 | `feat(bridge): router.py con providers.yaml + fallback chain` | strategy pattern §9.7, 2 proveedores por capability | unit tests con provider mockeado caído |
| #0110b | `feat(ghost-agent): paso 3 - dispara bridge.asset_generator via router` | genera FLUX.2 + Hailuo/Kling + MMAudio + Suno | mock de cada provider |
| #0111 | `feat(ghost-agent): paso 4 - compose final con moviepy` | MP4 en `/tmp/{job_id}-final.mp4` | comparación con fixture |
| #0112 | `feat(ghost-agent): paso 5 - upload R2 + signed URL` | jobs.result_mp4_url poblado | integración MinIO |
| #0113 | `feat(ghost-agent): Redis pub/sub emite progress events` | SSE endpoint reenvía | integración e2e |
| #0114 | `feat(ghost-agent): idempotencia + checkpoint por paso` | reinicio del worker retoma sin repetir | test: kill -9 mid-job |

### Sprint 2 — Frontend base (semanas 4-5)

| PR | Título | Output |
|---|---|---|
| #0201 | `chore(web): Next.js 15 + tailwind + shadcn/ui` | landing placeholder |
| #0202 | `feat(web): auth con Clerk (magic link)` | /login, /signup, session middleware |
| #0203 | `feat(web): wizard step 1 - upload selfie` | drag&drop + preview + presign upload |
| #0204 | `feat(web): wizard step 2 - upload producto` | form con categoría + nombre |
| #0205 | `feat(web): wizard step 3 - idea + formato + tono` | textarea + radio buttons |
| #0206 | `feat(web): POST /api/projects + POST /api/jobs desde wizard` | navega a /jobs/:id |
| #0207 | `feat(web): /jobs/:id - SSE hook useJobStream(id)` | progreso en vivo |
| #0208 | `feat(web): progress bar 5 fases + log live` | UI matching mockup § 4 |
| #0209 | `feat(web): /jobs/:id - video player + botón descarga` | video HTML5 + download MP4 |
| #0210 | `feat(web): /library - lista de proyectos del usuario` | grid + thumbnail + estado |

### Sprint 3 — LoRA + producción (semanas 6-7)

| PR | Título | Output |
|---|---|---|
| #0301 | `feat(web): wizard step 1b - subir más fotos (LoRA)` | upload múltiple opcional |
| #0302 | `feat(ghost-agent): paso 1b - LoRA training on-demand (FLUX.2 Klein)` | si N>=5 fotos, entrena via fal-ai/flux-lora-fast-training + guarda lora_url |
| #0303 | `feat(ghost-agent): asset-gen con lora_url (trigger SOFIA_BRAND)` | inyecta trigger word en prompts FLUX.2 |
| #0304 | `feat(ghost-agent): LoRA cache Redis 30 días por user_id` | hit-rate >50% en V2 |
| #0305 | `feat(bridge): specialty routing por scene.role + user_tier` | ADR-09 implementado, tests por matriz |
| #0306 | `feat(bridge): self-host LTX-Video 2.3 en RunPod H100 spot` | pod spin-up automático, warm pool de 1, auto-shutdown 5min idle |
| #0307 | `feat(bridge): price-arbitrage cron (daily)` | consulta precios de 8 providers, sobreescribe providers.yaml si >10% delta |
| #0308 | `feat(api): budget enforcement por user + tier` | 400 si supera quota mensual |
| #0309 | `feat(infra): Sentry + structlog → Grafana Cloud` | dashboards render time + error rate + $ por reel |
| #0310 | `feat(api): rate limiting + CSRF middleware` | 100 req/min anónimo |
| #0311 | `test: Playwright e2e happy path wizard → video final` | CI verde con render mock |

### Sprint 4 — Billing (semana 8)

| PR | Título | Output |
|---|---|---|
| #0401 | `feat(api): Stripe Billing + /api/webhooks/stripe` | handles subscription.created/deleted |
| #0402 | `feat(web): /pricing + /settings/billing` | CTA upgrade + portal Stripe |
| #0403 | `feat(api): plan enforcement (free 3/mes, pro 30/mes)` | 402 si supera |
| #0404 | `feat(web): watermark en plan free` | overlay discreto "Hecho con Guion Studio" |
| #0405 | `feat(api): add-on "Cinematic" ($0.99) desbloquea Kling Master + upscale Topaz` | Stripe one-time charge + flag en job |

### Sprint 5 — Ghost Agent v2 (semanas 9-10)

| PR | Título | Output |
|---|---|---|
| #0501 | `feat(ghost-agent): retry con exponential backoff por paso` | Kling/FLUX fallan, reintenta 3× |
| #0502 | `feat(ghost-agent): LLM advisor (Claude Haiku) para decisiones` | tool-use pattern para fallbacks |
| #0503 | `feat(ghost-agent): dead-letter queue + alerting` | ops ven jobs atascados |
| #0504 | `feat(web): "rehacer con cambios" (re-run con idea editada)` | POST /api/jobs/:id/retry |

### Sprint 6+ — Features V2 (semanas 11+)

PR #0601-0699: camera control UI, style presets, multi-producto, series, TTS, subtítulos, brand kit, A/B hooks.

### Sprint N — Moonshots (V3)

PR #1001+: IG/TikTok publishing, marketplace de playbooks, live editing, Gaussian splatting avatar.

---

## 16. Apéndices

### 16.1 Comparativa real-time (SSE vs WebSocket vs RSC)

| Criterio | SSE | WebSocket | RSC streaming |
|---|---|---|---|
| Setup | 1 línea Starlette | lib extra + gestión conexión | Next.js built-in |
| Bidireccional | ❌ | ✅ | ❌ |
| Reconexión auto | ✅ | ❌ (custom) | ✅ |
| Proxy/CDN friendly | ✅ (HTTP) | ⚠️ (upgrade header) | ✅ |
| Overhead | bajo | medio | bajo |
| Fit Guion Studio | ✅ (solo server→client) | overkill | Next-native, pero no fits job polling |

### 16.2 Env vars de la plataforma

```bash
# Anthropic (Guion_expert LLM)
ANTHROPIC_API_KEY=...

# Video providers (multi-provider, ver §9.7)
MINIMAX_API_KEY=...            # Hailuo 02 direct (volumen)
ATLAS_CLOUD_API_KEY=...        # Kling 2.1 Master -29% vs direct (hero)
KLING_DIRECT_API_KEY=...       # fallback Kling
REPLICATE_API_TOKEN=...        # FLUX.2, Topaz upscale, MMAudio, LatentSync
FAL_KEY=...                    # LoRA training (fast-training) + fallbacks
RUNPOD_API_KEY=...             # self-host LTX-2.3 + Hunyuan/Wan
RUNWAY_API_KEY=...             # opcional V2 (References para enterprise)
VERTEX_AI_PROJECT_ID=...       # opcional: Veo 3.1 Fast como add-on

# Audio providers
SUNO_API_KEY=...               # reseller sunoapi.org
CARTESIA_API_KEY=...           # TTS Sonic-3
ELEVENLABS_API_KEY=...         # fallback TTS

# Infra
DATABASE_URL=postgresql://.../guion_studio
REDIS_URL=redis://redis:6379/0
R2_ENDPOINT=https://....r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...

# Auth
CLERK_PUBLISHABLE_KEY=...
CLERK_SECRET_KEY=...

# Billing
STRIPE_SECRET_KEY=...
STRIPE_WEBHOOK_SECRET=...
STRIPE_PRICE_PRO_MONTHLY=price_...

# Observability
SENTRY_DSN=...
GRAFANA_LOKI_URL=...
```

### 16.3 Comandos canónicos del dev loop

```bash
# Primera vez
pnpm install && uv sync
docker compose -f infra/docker-compose.yml up -d
pnpm db:migrate

# Dev loop
pnpm dev                 # levanta web + api + ghost-agent + worker en paralelo

# Tests
pnpm test                # unit + integración
pnpm test:e2e            # Playwright

# Deploy
pnpm build
pnpm deploy:staging
pnpm deploy:prod
```

### 16.4 Presupuesto de costos unit economics (MVP) — r2 realistic

> **Disclaimer**: La versión r1 de este PRD calculaba **$0.87/reel** con precios catálogo de fal.ai, pero el usuario reportó ~$10/reel real (4 reels = $40). La razón: fal.ai añade 20-50% markup, y si usas Veo o Kling Pro, el video solo ya cuesta $5-15/reel. Esta r2 usa precios **directos** (sin markup) y routing por especialidad.

#### Escenario A — Free tier (6 clips × 5s, 100% Hailuo 02 Fast, sin LoRA)

| Item | Costo | Fuente |
|---|---|---|
| 6× Hailuo 02 Fast I2V (5s c/u) | $0.51 | Minimax direct $0.017/s |
| 6× FLUX.2 Pro frame ancla | $0.30 | Replicate $0.05 × 6 |
| 1× MMAudio v2 foley (self-host) | $0.02 | compute Runpod |
| 1× Suno v5 música 30s | $0.03 | reseller / Premier amortizado |
| Claude Haiku guión (7 llamadas) | $0.03 | ~30k tokens |
| Infra overhead (R2 + compute) | $0.05 | allocation |
| Buffer retry 20% | **$0.18** | |
| **Total free tier** | **~$1.12** | *(objetivo <$0.80 al escalar)* |

#### Escenario B — Pro tier (6 clips, LoRA on-demand, 1 hero shot en Kling)

| Item | Costo | Fuente |
|---|---|---|
| LoRA training (amortizado en 50 reels) | $0.06 | FLUX.2 Klein LoRA $3 ÷ 50 |
| 6× FLUX.2 Pro frame ancla + LoRA | $0.30 | Replicate $0.05 × 6 |
| 1× Kling 2.1 Master hero (5s) | $0.35 | Atlas Cloud $0.07/s |
| 5× Hailuo 02 Fast volumen (5s) | $0.43 | Minimax direct $0.017/s × 5 × 5 |
| 1× Wan 2.2 S2V product close-up | $0.01 | self-host RunPod |
| 1× MMAudio v2 foley | $0.02 | self-host |
| 1× Cartesia Sonic TTS 20s | $0.002 | direct $0.006/min |
| 1× Suno v5 música 30s | $0.03 | reseller |
| 1× LatentSync lip-sync (si aplica) | $0.02 | self-host |
| Claude Haiku guión | $0.03 | |
| Infra overhead | $0.05 | |
| Buffer retry 20% | $0.27 | |
| **Total pro tier** | **~$1.60** | *(objetivo <$2.00)* |

#### Escenario C — Add-on "Cinematic" $0.99 (Kling Master en todo + upscale Topaz)

| Item | Costo | Fuente |
|---|---|---|
| 6× Kling 2.1 Master (5s c/u) | $2.10 | Atlas Cloud $0.07/s × 6 × 5 |
| 6× FLUX.2 Pro + LoRA | $0.30 | |
| Topaz upscale 30s → 1080p/4K | $1.20 | Replicate $0.04/s |
| Audio stack (MMAudio + Suno + Cartesia) | $0.05 | |
| LoRA amortizado | $0.06 | |
| Claude + infra + buffer | $0.35 | |
| **Total Cinematic** | **~$4.06** | |

#### Economía por plan (con 10 reels/mes de promedio)

| Plan | Precio al usuario | Costo variable | Gross margin | % |
|---|---|---|---|---|
| Free (3 reels, watermark) | $0 | 3 × $1.12 = $3.36 | -$3.36 | CAC |
| Pro $19/mes | $19 | 10 × $1.60 = $16.00 | $3.00 | **16%** |
| Pro + 2 add-ons Cinematic | $19 + $1.98 | $16 + 2 × ($4.06 - $1.60) = $20.92 | $0.06 | break-even |
| Enterprise $99/mes (30 reels) | $99 | 30 × $1.60 = $48.00 | $51.00 | **52%** |

**Observación honesta**: el margen de 16% en Pro es **tight**. Para hacerlo saludable hay que mover uno de estos 4 levers:

1. **Scale → self-host**: cuando el volumen pasa 500 reels/día, un pool dedicado de H100 con Hunyuan/LTX baja el Hailuo spend a <$0.30 por reel. Target V2: costo Pro baja a $1.00, margen sube a 47%.
2. **Subir Pro a $24**: benchmark Krea ($25) y Higgsfield ($29) lo justifica.
3. **Limitar reels en Pro a 8**: margen sube a 33%.
4. **Push add-on Cinematic**: cada usuario que compra 2 Cinematic/mes sube el ARPU +$2 con costo marginal neto +$1.

### 16.5 Roadmap de reducción de costo por trimestre

| Trimestre | Palanca | Costo/reel Pro objetivo |
|---|---|---|
| Q1 MVP | Routing multi-provider (§9.7) | $1.60 |
| Q2 V2 | Self-host pool Hunyuan en pod H100 dedicado | $1.00 |
| Q3 V2 | LoRA cache 80% hit-rate + CDN edge | $0.75 |
| Q4 V3 | Batch mode nocturno (10× clips en 1 request) | $0.50 |

### 16.6 Comparativa top-10 modelos generativos de video (abril 2026)

Esta es la **fuente de verdad** para decisiones de routing. Todos los precios son del API directo del proveedor (no fal.ai). Última verificación: 2026-04-22.

| # | Modelo | Proveedor | Precio directo | Max dur. | Audio nativo | Mejor para | Evitar en | Score (10) |
|---|---|---|---|---|---|---|---|---|
| 1 | **Kling 3.0 / 2.1 Master** | Kuaishou | $0.084-0.168/s | 10s (chain 3min) | 3.0: sí | motion, física, dance, hero | cultura no-cn, Chinese phone (mejoró 2026) | 9 · 10 · 8 · 7 · 6 · 7 |
| 2 | **Minimax Hailuo 02 Fast** | MiniMax | $0.017/s | 10s | parcial | **volumen**, costo/calidad | acción rápida, 4K premium | 8 · 8 · 8 · 7 · 9 · 9 |
| 3 | **Runway Gen-4.5** | Runway | $0.05-0.15/s | 10s | no | consistencia personaje (References), cinemático | productos de marca (censor), cosmetics | 8 · 7 · 8 · 9 · 7 · 7 |
| 4 | **Google Veo 3.1** | Google Vertex AI | $0.10-0.50/s | 8s | **sí (líder)** | dialogue, lip-sync, texto en pantalla | productos, costo volumen | 9 · 8 · 10 · 7 · 6 · 5 |
| 5 | **OpenAI Sora 2 Pro** | OpenAI | $0.10-0.50/s | **25s** | sí | clips largos, Cameos para rostro | rostros no-consentidos, marcas, waitlist | 9 · 8 · 9 · 8 · 6 · 4 |
| 6 | **Luma Ray-2 Flash** | Luma | $0.06/s | 10s | no | rapidez, escenas natural, Flash ~20s | consistencia personaje, prompts complejos | 7 · 7 · 7 · 5 · 9 · 9 |
| 7 | **Pika 2.2** | Pika Labs | ~$0.09/s | 10s | SFX only | Pikascenes (composición multi-imagen), VFX | motion >5s, realismo estricto | 6 · 6 · 7 · 6 · 8 · 7 |
| 8 | **Tencent Hunyuan Video 1.5** | Tencent (open source) | self-host ~$0.01/s | 5s (chain) | Foley companion | **LoRA ecosystem**, calidad, sin censor | setup complex, slower que Kling | 7 · 7 · 7 · 9 · 5 · 10 |
| 9 | **Alibaba Wan 2.2 S2V** | Alibaba (open source) | self-host ~$0.01/s | 5-8s | no | **products** (S2V single-image), baja VRAM | prompts en inglés débiles, fragmented docs | 7 · 6 · 7 · 8 · 7 · 10 |
| 10 | **Lightricks LTX-Video 2.3** | Lightricks (open source) | self-host ~$0.002/clip | 4-8s, 4K | 2.3: sí | **preview real-time**, iteración | calidad, world knowledge | 5 · 6 · 6 · 6 · 10 · 10 |

**Leyenda scores**: Photorealism · Motion · Prompt adherence · Character consistency · Speed · Cost-efficiency

#### Pros y contras por modelo (TL;DR)

1. **Kling 3.0** — Pros: motion/física 10/10, Pro extiende a 3min, 4K en 3.0, start+end frame. Cons: content filter occidental, registro global mejorado pero todavía fricción, +20% markup en fal (usar Atlas Cloud -29%).
2. **Hailuo 02 Fast** — Pros: más barato de su tier, camera control "Director" sólido, direct API sin markup. Cons: weaker motion vs Kling, 4K a veces con artifacts, docs en chino.
3. **Runway Gen-4.5** — Pros: References (3 imgs → consistencia best-in-class), Aleph editing, mature tooling. Cons: **censura agresiva de branding/cosmetics** (killer para Guion Studio), sin audio native.
4. **Veo 3.1** — Pros: **único con audio sincronizado real** (dialogue+SFX), prompt adherence 10/10, typography decente. Cons: **los más caros** + filtros Google (bloquea minors, brands, realismo). Vertex AI quota approval tarda días.
5. **Sora 2** — Pros: 25s sin corte, Cameos, audio native, calidad. Cons: filtro más estricto de la industria, waitlist API, Pro tier caro.
6. **Luma Ray-2 Flash** — Pros: rápido y barato, clean motion. Cons: peor consistencia del tier-1, "dreamy" look leak, prompt adherence flaky.
7. **Pika 2.2** — Pros: Pikascenes (único modo composición), VFX presets. Cons: limitado >5s, no character-lock, "Pika look" cartoon.
8. **Hunyuan 1.5** — Pros: open source, LoRA-train, uncensored, commercial license. Cons: slower hasta que haces batch, motion detrás de Kling.
9. **Wan 2.2 S2V** — Pros: **ideal para productos** (subject lock 1-shot), runs en 8GB VRAM (!), LoRA activo. Cons: English prompting débil, calidad facial inferior a Hunyuan.
10. **LTX-2.3** — Pros: **el único cuasi-real-time** del stack, 4K en 2.3, costo despreciable self-host. Cons: calidad visible inferior, world-model pequeño.

#### Proveedores y markup (verificar antes de commit budget)

| Proveedor | Modelos cubiertos | Markup vs direct | Cuándo usar |
|---|---|---|---|
| **Direct API** (Minimax, Vertex AI, Runway, Kuaishou Kling Global) | el suyo | 0% | siempre por default |
| **Atlas Cloud** | Kling family | **-29%** | **siempre para Kling** |
| **Piapi / 302.ai** | Kling + varios | -10-20% | Kling si Atlas down |
| **Replicate** | 100+ open + algunos closed | -10-30% vs fal | FLUX, Hunyuan, Wan, LTX, Topaz |
| **fal.ai** | 200+ | **+20-50%** | LoRA training (líder), casos exóticos |
| **Self-host RunPod H100 spot** | open source (LTX, Hunyuan, Wan, MMAudio, LatentSync) | infra only | cuando volumen >100 reels/día |
| **sunoapi.org** | Suno | resell | ~$0.03/canción amortizado |
| **Cartesia direct** | Sonic-3 TTS | ~$0.006/min | **5× más barato que ElevenLabs** |

**Fuente research**: auditoría 2026-04-22 contra docs oficiales (runwayml.com, atlascloud.ai, platform.minimax.io, lumalabs.ai, pika.art, vertex AI, costgoat, runpod.io, replicate.com, cartesia.ai, elevenlabs.io).

### 16.7 Glosario

- **Ghost Agent**: orquestador invisible del pipeline end-to-end.
- **Master Stack v2**: schema narrativo+visual+sónico de Guion_expert.
- **LoRA**: Low-Rank Adaptation, fine-tuning de FLUX para consistencia.
- **Trigger word**: palabra-gatillo que activa el LoRA entrenado (ej. `SOFIA_BRAND`).
- **Playbook**: YAML con paleta+tipografía+motion params (flat-motion-graphics, etc.).
- **Bridge**: capa de traducción Guion_expert ↔ OpenMontage (ya existe).
- **Wizard**: form multi-step del frontend para capturar inputs.
- **SSE**: Server-Sent Events, streaming unidireccional HTTP.
- **BFF**: Backend-for-Frontend, patrón Next.js RSC + FastAPI data-layer.
- **Hero moment**: escena climax en el scene_plan.
- **S2V / I2V / T2V**: Subject-/Image-/Text-to-Video.
- **V2A**: Video-to-Audio (foley sincronizado con video existente, ej. MMAudio).
- **Routing por especialidad**: ADR-09 — cada modelo en el rol que mejor ejecuta.
- **Markup**: diferencia de precio entre provider direct y reseller/aggregator.

---

**Fin del PRD — revisión 2.** Próximos pasos sugeridos:

1. Revisar §9.6 (routing) y §16.6 (top-10) con el equipo técnico y confirmar providers.
2. Kick-off Sprint 0 (mover los 3 repos al monorepo).
3. Crear cuentas y API keys de los 8 proveedores listados en §16.2 (Cartesia, Atlas Cloud, Minimax directo, Replicate, RunPod, Suno reseller, fal solo para LoRA, Anthropic).
4. Validar el wizard de 3 pasos con 5 usuarios tipo-Sofía (entrevistas) antes de codear Sprint 2.
5. Decidir hosting final (Hetzner + Cloudflare Pages + RunPod H100 spot para self-host).
6. Benchmark real: correr 3 reels de prueba con la matriz §9.6 y verificar costo <$2 (vs los $10 actuales con fal.ai+Veo).
