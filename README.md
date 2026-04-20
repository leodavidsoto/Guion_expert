# 🎬 Guion Experts Suite V2

<div align="center">

![Banner](https://img.shields.io/badge/AI-Screenwriting-blueviolet?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python)
![Claude](https://img.shields.io/badge/Claude-Haiku_4.5-orange?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)

**Suite completa de IA para escritura de guiones cinematográficos**

Sistema automatizado que genera guiones profesionales usando 8 expertos especializados,
53 estructuras narrativas y soporte para 70+ formatos de video.

> 🚧 **Estado actual (2026-04-20)**: migración en curso a **Claude Haiku 4.5** +
> integración Master Stack con fal.ai (FLUX/Kling/Runway/WAN) + Suno self-hosted.
> Ver **[`HANDOFF.md`](HANDOFF.md)** para retomar sesión y
> **[`CHANGELOG.md`](CHANGELOG.md)** para el log de commits.
> Rama activa: `feature/llm-provider-unified`.

[Características](#-características) •
[Instalación](#-instalación-rápida) •
[Uso](#-uso) •
[Documentación](#-documentación) •
[Contribuir](#-contribuir)

</div>

---

## 🌟 Características

### 🤖 **8 Expertos de IA Especializados**
- **Clasificador**: Detecta automáticamente formato y estructura óptima
- **Conceptor**: Desarrolla concepto narrativo completo
- **Arquitecto**: Genera estructura con beats detallados
- **Escaletista**: Crea escaleta profesional de escenas
- **Dialoguista**: Escribe diálogos cinematográficos
- **Localizador**: Adapta a español chileno regional
- **Prompts SD**: Genera prompts para Stable Diffusion
- **Director Flow**: Crea tablas de rodaje para Google Veo

### 📖 **53 Estructuras Narrativas**
- **Hollywood Clásico**: Save The Cat, Three Act, Five Act, etc.
- **Viaje Mítico**: Hero's Journey, Virgin's Promise, Writer's Journey
- **TV y Series**: Story Circle, Procedural, Cold Open, etc.
- **No Lineal**: Rashomon, In Media Res, Fractured Narrative
- **Internacional**: Kishōtenketsu, Bollywood Masala, Three Kingdoms
- **Experimental**: Hyperlink Cinema, Stream of Consciousness
- **Formato Corto**: Simple, Problema-Solución, AIDA
- **Documental**: Expositivo, Observacional, Personal Essay
- **Teatro**: Well-Made Play, Absurdist, Epic Theatre

### 📺 **70+ Formatos de Video**
- Redes Sociales: TikTok, Reels, Shorts, Stories
- Streaming: Series, Sitcoms, Miniseries
- Cine: Corto, Medio, Largometraje
- Musical: Videoclips, Concert Films
- Educativo: Tutoriales, Masterclass, Webinars
- Comercial: Spots, Branded Content, Corporativos
- Gaming: Trailers, Reviews, Let's Plays

### 🎥 **Director Flow + Master Stack (v2, Commit 7)**
- **Tool use estructurado** con Anthropic — schema Pydantic validado, fail-fast sin regex.
- **Pipeline de 3 fases**:
  - *Fase 1* — Ancla visual (FLUX.1 Pro vía fal.ai).
  - *Fase 2* — Inyección de movimiento (routing determinístico:
    Kling 2.5 Pro / Runway Gen-3 / WAN 2.1 según `subject_type`).
  - *Fase 3* — Post-producción (RIFE slow-mo + Real-ESRGAN 4K).
- **Atmósfera sonora baked-in** al dialoguista — bloque estructurado
  (MOOD/MÚSICA/SFX/DIÉGESIS/SILENCIO) que alimenta **Suno** (música) +
  **mmaudio** (SFX).
- **Bridge a OpenMontage** con `scene.master_stack` completo (visual_anchor +
  camera + motion_intent + sonic + post_production + chosen_video_model).

### 🌐 **Interfaz Web Moderna**
- WebUI en tiempo real con WebSockets
- Auto-detección inteligente de formato/estructura
- Workspace dedicado por estructura
- Vista de expertos individuales
- Historial de proyectos

---

## 🚀 Instalación Rápida

### Prerrequisitos
- **macOS** (M1/M2/Intel) o **Linux** (Ubuntu 22.04+)
- **Python 3.11+**
- **ANTHROPIC_API_KEY** (Claude Haiku 4.5 como default; Ollama queda como fallback)
- **FAL_API_KEY** (para FLUX, Kling, Runway, WAN, Real-ESRGAN — pendiente Commit 8+)
- **SUNO_COOKIE** (Suno self-hosted vía `gcui-art/suno-api` — pendiente Commit 10)
- **4GB RAM mínimo** (ya no se corre Qwen 14B localmente)

### Instalación (stack actual, post-migración Claude)
```bash
# 1. Clonar repositorio
git clone https://github.com/leodavidsoto/guion-experts-suite-v2.git
cd guion-experts-suite-v2

# 2. Instalar dependencias Python (incluye anthropic, pydantic, structlog)
pip3 install -r requirements.txt

# 3. Configurar .env
cp .env.example .env
# Editar .env y agregar ANTHROPIC_API_KEY (y FAL/SUNO cuando estén)

# 4. Iniciar con Docker (recomendado)
docker compose up -d

# 5. O en dev local
./iniciar.sh
```

El navegador se abrirá automáticamente en `http://localhost:5001`

### Instalación Manual

<details>
<summary>Ver pasos detallados</summary>
```bash
# 1. Crear directorios
mkdir -p output logs config prompts scripts webapp/templates webapp/static

# 2. Instalar Python packages
pip3 install flask flask-socketio python-socketio werkzeug

# 3. Iniciar Ollama
ollama serve &

# 4. Iniciar servidor
cd webapp
python3 server.py
```

</details>

---

## 🎯 Uso

### Modo 1: Web UI (Recomendado)
```bash
# Iniciar sistema
./iniciar.sh

# Abre navegador en http://localhost:5001
```

1. **Selecciona modo**: Auto-detección o manual
2. **Escribe tu idea**: "Thriller psicológico sobre inteligencia artificial"
3. **Presiona Generar**: El sistema procesa automáticamente
4. **Descarga resultado**: Guion completo en `/output`

### Modo 2: Línea de Comandos
```bash
# Generar proyecto completo
./ejecutar.sh "Una comedia romántica sobre dos programadores en Silicon Valley"

# Ver resultado
ls -lh output/$(ls -t output | head -1)
```

### Modo 3: Experto Individual
```bash
# Solo arquitectura narrativa
./scripts/run_expert.sh arquitecto "Historia de ciencia ficción"

# Solo diálogos
./scripts/run_expert.sh dialoguista "Escena de confrontación"
```

---

## 📊 Outputs Generados

Por cada proyecto se generan:
```
output/proyecto_TIMESTAMP/
├── clasificacion/
│   └── result.txt          # Formato y estructura detectados
├── concepto/
│   └── result.txt          # Concepto narrativo desarrollado
├── estructura/
│   └── beats.txt           # Estructura completa con beats
├── escaleta/
│   └── lista.txt           # Lista numerada de escenas
├── escenas/
│   ├── escena_001.txt      # Escena con diálogos
│   ├── escena_002.txt
│   └── ...
├── prompts_sd/
│   ├── prompt_001.txt      # Prompts Stable Diffusion
│   └── ...
├── prompts_veo/
│   ├── veo_001.json        # Prompts para video AI
│   └── ...
└── flow/
    ├── tabla_rodaje.txt    # Tabla completa Google Flow
    └── plano_XXX.txt       # Planos individuales
```

---

## 🛠️ Configuración

### Cambiar Modelos

Edita `config/models.conf`:
```bash
MODEL_CLASIFICADOR="llama3.2:3b"
MODEL_CONCEPTO="qwen2.5:7b"
MODEL_ARQUITECTO="qwen2.5:14b"
# ... más modelos
```

### Agregar Estructuras Personalizadas

Edita `config/structures.json`:
```json
{
  "custom": {
    "MI_ESTRUCTURA": {
      "name": "Mi Estructura",
      "author": "Tu Nombre",
      "beats": 10,
      "duration": "90-120 min",
      "best_for": "Drama",
      "description": "Tu descripción"
    }
  }
}
```

### Crear Prompts Personalizados

Agrega archivo en `prompts/12_mi_experto.txt` y registra en `config/models.conf`

---

## 📚 Documentación

### Documentos clave (empezar acá)
- **[HANDOFF.md](HANDOFF.md)** — Retomar sesión de desarrollo.
- **[CLAUDE.md](CLAUDE.md)** — Contexto auto-cargado por Claude Code/Cowork.
- **[CHANGELOG.md](CHANGELOG.md)** — Log detallado de commits.

### Guías Completas (legacy)
- [📖 Guía de Estructuras Narrativas](docs/ESTRUCTURAS.md)
- [🎬 Guía de Director Flow](docs/DIRECTOR_FLOW.md)
- [🎨 Guía de Formatos](docs/FORMATOS.md)
- [🔧 Configuración Avanzada](docs/CONFIG.md)
- [🚀 Deploy y Producción](docs/DEPLOY.md)

### API Reference
- [📡 API Endpoints](docs/API.md)
- [🔌 WebSockets](docs/WEBSOCKETS.md)
- [🧩 Sistema de Skills](docs/SKILLS.md)

---

## 🐳 Docker
```bash
# Build
docker-compose build

# Run
docker-compose up -d

# Logs
docker-compose logs -f

# Stop
docker-compose down
```

---

## 🌐 Deploy Online

### Railway (Recomendado)
```bash
railway init
railway up
```

### Vercel (Frontend)
```bash
cd frontend
vercel
```

### DigitalOcean
Ver [DEPLOY_GUIDE.md](DEPLOY_GUIDE.md)

---

## 🧪 Testing
```bash
# Test pipeline completo
./test_pipeline.sh

# Test experto individual
python3 -m pytest tests/

# Verificar instalación
./verificar_sistema.sh
```

---

## 📈 Roadmap

### V2.1 (Próximo)
- [ ] Integración con Stable Diffusion API
- [ ] Integración con Google Veo API
- [ ] Export a Final Draft (.fdx)
- [ ] Export a PDF formateado
- [ ] Multi-idioma (Inglés, Francés, Alemán)

### V2.2
- [ ] Colaboración multi-usuario en tiempo real
- [ ] Versionado de guiones (Git-like)
- [ ] Templates predefinidos por género
- [ ] Análisis de mercado automático

### V3.0
- [ ] Casting automático con IA
- [ ] Breakdown de producción
- [ ] Presupuestado automático
- [ ] Calendario de rodaje

---

## 🤝 Contribuir

¡Las contribuciones son bienvenidas!

1. Fork el proyecto
2. Crea tu rama (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add: AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

Ver [CONTRIBUTING.md](CONTRIBUTING.md) para más detalles.

---

## 📝 Changelog

### [2.0.0] - 2025-01-19

#### Agregado
- 🎬 Director Flow para Google Veo
- 📖 53 estructuras narrativas
- 📺 70+ formatos de video
- 🌐 Interfaz web moderna
- 🤖 8 expertos especializados
- 🐳 Soporte Docker
- 🔐 Sistema multi-usuario
- 📊 Sistema de colas

#### Mejorado
- ⚡ Performance de generación (30% más rápido)
- 🎨 UI/UX completa renovación
- 📝 Documentación extensa

Ver [CHANGELOG.md](CHANGELOG.md) completo.

---

## ❓ FAQ

<details>
<summary><b>¿Por qué usar LLMs locales en vez de OpenAI?</b></summary>

- ✅ **Privacidad total**: Tus ideas no salen de tu máquina
- ✅ **Sin costos por uso**: Genera infinitos proyectos sin pagar por tokens
- ✅ **Sin censura**: No hay restricciones de contenido
- ✅ **Offline**: Funciona sin internet
</details>

<details>
<summary><b>¿Cuánto tarda en generar un guion completo?</b></summary>

- Cortometraje (10 min): ~10-15 minutos
- Largometraje (90 min): ~25-35 minutos
- Serie TV (45 min): ~20-25 minutos

Depende de tu CPU/GPU y los modelos usados.
</details>

<details>
<summary><b>¿Puedo usar modelos más grandes?</b></summary>

Sí, edita `config/models.conf`:
```bash
MODEL_ARQUITECTO="qwen2.5:32b"  # Mejor calidad, más lento
```
</details>

<details>
<summary><b>¿Funciona en Windows?</b></summary>

Actualmente solo macOS y Linux. Para Windows usa WSL2 o Docker.
</details>

---

## 📄 Licencia

Este proyecto está bajo la Licencia MIT - ver [LICENSE](LICENSE) para detalles.

---

## 🙏 Agradecimientos

- **Ollama Team** - Por hacer LLMs locales accesibles
- **Qwen Team** - Modelos Qwen 2.5 excelentes
- **Meta** - Llama 3.2 para clasificación rápida
- **Blake Snyder** - Estructura Save The Cat
- **Joseph Campbell** - El viaje del héroe
- **Dan Harmon** - Story Circle
- **Google Labs** - Flow/Veo para generación de video

---

## 📞 Contacto

- **Issues**: [GitHub Issues](https://github.com/leodavidsoto/guion-experts-suite-v2/issues)
- **Discussions**: [GitHub Discussions](https://github.com/leodavidsoto/guion-experts-suite-v2/discussions)
- **Email**: leodavidsoto@gmail.com

---

## 🌟 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=leodavidsoto/guion-experts-suite-v2&type=Date)](https://star-history.com/#leodavidsoto/guion-experts-suite-v2&Date)

---

<div align="center">

**Hecho con ❤️ para escritores y creadores**

[⬆ Volver arriba](#-guion-experts-suite-v2)

</div>
