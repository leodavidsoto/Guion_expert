# CLAUDE.md — Contexto para Claude Code / Cowork

> Este archivo se auto-carga cuando un agente entra al repo.
> Leer esto primero, antes de cualquier edit.

## Qué es este proyecto

**Guion_expert** es una suite de IA para escritura de guiones cinematográficos, en proceso de migración a **Claude Haiku 4.5** y hardening para producción en **Hetzner CX22**.

El loop completo es: `idea → guion estructurado → scene_plan.json con Master Stack → OpenMontage → video final con música original`.

## Estado actual

- Branch de trabajo: **`feature/llm-provider-unified`** (6 commits ahead de `main`).
- Último commit: `0cde548` — Master Stack schemas + tool use + bridge v2.
- Siguiente commit planeado: **Commit 8** — `.env.example` expandido + `webapp/integrations/base.py`.

**Leé `HANDOFF.md`** para el detalle completo de qué se hizo, qué falta y cómo retomar.

## Convenciones del repo

### Lenguaje
- Código: inglés (funciones, variables, comments).
- Docstrings + prompts + commit messages: español rioplatense ("vos", "hacés", "ok dale").
- Scripts de usuario (UX): español.

### Git
- Rama activa: `feature/llm-provider-unified`.
- Commits atómicos con mensaje Conventional Commit (`feat:`, `fix:`, `refactor:`, etc.).
- Cada commit co-authored con Claude: `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`.
- NUNCA force-push sin pedido explícito.
- Los mensajes de commit son largos y descriptivos (3+ párrafos).

### Arquitectura
- **LLM calls**: siempre por `webapp/llm_provider.py::generate()` con `role=` del expert. No llamar Anthropic SDK directo en otros módulos.
- **Config**: `webapp/config.py` con pydantic-settings (fail-fast si falta env var).
- **Per-expert tuning**: `config/llm_provider.yaml` (temperature, max_tokens).
- **Structured output**: `llm_provider.generate_structured()` con Anthropic tool use — fail-fast, sin regex, sin fallbacks silenciosos.
- **Bridge** (`bridge/`): puente determinístico a OpenMontage, **sin LLM calls**. Se mantiene desacoplado de `webapp/` — constantes compartidas como `VIDEO_MODEL_ROUTING` se duplican intencionalmente.

### Flujo de trabajo
1. Leer `HANDOFF.md` al inicio de cada sesión.
2. `git status` + `git log --oneline -10` para confirmar estado.
3. Trabajar commit por commit — un objetivo atómico por commit.
4. Smoke test antes de commit (`py_compile` mínimo; tests end-to-end cuando aplique).
5. Actualizar `HANDOFF.md` + `CHANGELOG.md` al final de cada commit relevante.

## Dónde vive qué

```
Guion_expert/
├── HANDOFF.md               ← retomar sesión (leer primero)
├── CLAUDE.md                ← este archivo
├── CHANGELOG.md             ← log detallado
├── README.md                ← readme público
├── config/
│   ├── llm_provider.yaml    ← per-expert tuning
│   ├── models.conf          ← legacy ollama (en deprecación)
│   └── structures.json      ← 53 estructuras narrativas
├── prompts/                 ← prompts de cada expert (01-11 numerados)
│   ├── 04_dialoguista.txt   ← emite bloque sonoro Suno
│   └── 05_veo_flow.txt      ← Master Stack philosophy
├── webapp/
│   ├── config.py            ← pydantic-settings (fail-fast)
│   ├── llm_provider.py      ← adapter Claude/Ollama + generate_structured
│   ├── pipeline_claude.py   ← orquestador del pipeline
│   ├── server.py            ← Flask + SocketIO
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── cinematic.py     ← Pydantic VeoPrompt + routing
│   └── integrations/        ← (pendiente Commit 8+)
│       ├── base.py          ← httpx client compartido (Commit 8)
│       ├── fal.py           ← flux/kling/runway/wan/mmaudio (Commit 9)
│       └── suno.py          ← gcui-art/suno-api (Commit 10)
├── bridge/
│   └── openmontage_export.py ← bridge determinístico, sin LLM
├── output/                  ← proyectos generados (gitignored)
├── Dockerfile               ← multi-stage build
├── docker-compose.yml       ← webapp + (suno-api en Commit 10)
├── .dockerignore
└── requirements.txt
```

## Comandos rápidos

```bash
# Dev local
source venv/bin/activate && cd webapp && python server.py

# Docker
docker compose build
docker compose up -d
docker compose logs -f

# Tests críticos
python -m py_compile webapp/schemas/*.py webapp/llm_provider.py webapp/pipeline_claude.py bridge/openmontage_export.py

# Export a OpenMontage
python -c "
from bridge import export_project_to_openmontage
from pathlib import Path
export_project_to_openmontage(
    project_dir=Path('output/20260420_123000'),
    openmontage_root=Path('/Users/leo/Desktop/ESCRIBE/OpenMontage'),
    idea='reel sobre AI generativa',
)"
```

## Decisiones de diseño tomadas

1. **Claude Haiku 4.5 como default** — por latencia + costo + calidad. Ollama sigue como fallback pero ya no es el driver.
2. **Tool use en lugar de parsear texto libre** para structured output — robusto, validable con Pydantic, fail-fast.
3. **Bridge desacoplado** de webapp — duplicación intencional de constantes (VIDEO_MODEL_ROUTING).
4. **Sound designer bake-in** al dialoguista — opción A sobre opción B (expert separado). Menos pipeline stages, más coherencia narrativa.
5. **Routing determinístico** I2V (no delegado al LLM) — tabla estática `subject_type → modelo`. El LLM elige el subject_type; la tabla hace el routing.
6. **Self-hosted Suno** vía `gcui-art/suno-api` (no hay API pública oficial). Leo paga Premium, la cookie se pasa como env var.
7. **fal.ai como proxy único** para FLUX + Kling + Runway + WAN + Real-ESRGAN + TTS — una sola key, un solo cliente httpx.

## Qué NO hacer

- No agregar `print()` en producción — usar `structlog` (ya configurado en Commit 3).
- No llamar al Anthropic SDK directamente fuera de `llm_provider.py`.
- No parsear JSON con regex — usar `generate_structured()` + Pydantic.
- No mezclar lógica de bridge con lógica de webapp — el bridge es puro + determinístico.
- No commitear secrets — `.env` está en `.gitignore`.
- No updatear el routing table en solo uno de los dos lugares (webapp/schemas/ + bridge/).
- No force-push a main ni a `feature/llm-provider-unified`.
