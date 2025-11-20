# 📖 GUÍA COMPLETA - GUION EXPERTS SUITE V2

## 🎬 GENERACIÓN DE PROYECTOS

### Uso básico
```bash
./ejecutar.sh "tu idea aquí"
```

### Con storyboard (requiere Stable Diffusion)
```bash
./ejecutar_con_storyboard.sh "tu idea"
```

---

## 🔍 ANÁLISIS DE GUIONES PDF

### Análisis completo
```bash
./analizar_completo.sh guion.pdf
```

### Solo análisis base
```bash
./scripts/analizar_pdf.sh guion.pdf
```

---

## 📊 MONITOREO

### Ver progreso en tiempo real
```bash
./scripts/monitor.sh
```

Presiona Ctrl+C para salir.

---

## 🛠️ HERRAMIENTAS

### Validar proyecto generado
```bash
./scripts/validar.sh output/[timestamp]
```

### Exportar a PDF/Markdown
```bash
./scripts/exportar.sh output/[timestamp]
```

### Comparar proyectos
```bash
./scripts/comparar.sh
```

---

## 📁 ESTRUCTURA DE ARCHIVOS
```
output/[timestamp]/
├── clasificacion/    # Tipo de proyecto
├── concepto/         # Pitch completo
├── estructura/       # Beat points
├── escaleta/         # Lista de escenas
├── escenas/          # Escenas escritas
├── prompts_sd/       # Para Stable Diffusion
└── prompts_veo/      # Para Veo 3.1
```

---

## ⚙️ REQUISITOS

### Para generación:
- Ollama instalado y corriendo
- Modelos descargados

### Para análisis de PDFs:
```bash
brew install poppler
```

O
```bash
pip3 install PyPDF2 --break-system-packages
```

### Para storyboard:
- Stable Diffusion WebUI
- Ejecutar con: `./webui.sh --api --listen`

---

## 🆘 SOLUCIÓN DE PROBLEMAS

### Ollama no responde
```bash
pkill -9 ollama
ollama serve > /tmp/ollama.log 2>&1 &
```

### Ver logs
```bash
tail -f /tmp/ollama.log
```

### Proyecto incompleto
```bash
./scripts/validar.sh output/[timestamp]
```
