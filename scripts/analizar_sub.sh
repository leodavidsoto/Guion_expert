#!/bin/bash
source scripts/lib.sh

SUB="$1"
[ ! -f "$SUB" ] && log_error "Archivo no encontrado: $SUB" && exit 1

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ANALYSIS_DIR="analyzer/analysis_$TIMESTAMP"
mkdir -p "$ANALYSIS_DIR"

log_section "ANALIZADOR DE SUBTÍTULOS"
log "Archivo: $(basename "$SUB")"
log "Output: $ANALYSIS_DIR"
echo ""

# Extracción de texto
log_info "[1/5] Extrayendo texto del subtítulo..."

python3 - "$SUB" "$ANALYSIS_DIR" << 'PYEOF'
import sys
import re

sub_file = sys.argv[1]
analysis_dir = sys.argv[2]

def clean_srt(content):
    content = re.sub(r'^\d+$', '', content, flags=re.MULTILINE)
    content = re.sub(r'\d{2}:\d{2}:\d{2}[,.]\d{3} --> \d{2}:\d{2}:\d{2}[,.]\d{3}', '', content)
    content = re.sub(r'<[^>]+>', '', content)
    content = re.sub(r'\n{3,}', '\n\n', content)
    return content.strip()

def clean_vtt(content):
    content = re.sub(r'^WEBVTT.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'\d{2}:\d{2}:\d{2}[,.]\d{3} --> \d{2}:\d{2}:\d{2}[,.]\d{3}.*', '', content)
    content = re.sub(r'<[^>]+>', '', content)
    return content.strip()

try:
    with open(sub_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    if sub_file.lower().endswith('.vtt'):
        text = clean_vtt(content)
    else:
        text = clean_srt(content)
        
    with open(f'{analysis_dir}/raw_text.txt', 'w', encoding='utf-8') as f:
        f.write(text)
        
    print("✓ Texto extraído y limpiado")
    
except Exception as e:
    print(f"✗ Error: {e}")
    sys.exit(1)
PYEOF

if [ $? -ne 0 ]; then
    log_error "Error procesando subtítulo"
    exit 1
fi

# Análisis básico
log_info "[2/5] Analizando contenido..."

python3 - "$ANALYSIS_DIR" << 'PYEOF'
import sys, json
from collections import Counter

analysis_dir = sys.argv[1]

with open(f'{analysis_dir}/raw_text.txt', 'r', encoding='utf-8') as f:
    text = f.read()

words = text.split()
lines = [l for l in text.split('\n') if l.strip()]

stats = {
    'total_words': len(words),
    'total_lines': len(lines),
    'estimated_duration_minutes': len(words) / 150,
    'format': 'SUBTITLE'
}

with open(f'{analysis_dir}/stats.json', 'w') as f:
    json.dump(stats, f, indent=2)

print(f"✓ {len(words)} palabras")
print(f"✓ Duración est: {stats['estimated_duration_minutes']:.1f} min")
PYEOF

# Detectar estructura
log_info "[3/5] Detectando estructura..."

python3 - "$ANALYSIS_DIR" << 'PYEOF'
import sys, json

analysis_dir = sys.argv[1]
with open(f'{analysis_dir}/stats.json', 'r') as f:
    stats = json.load(f)

duration = stats['estimated_duration_minutes']

analysis = {
    'detected_structure': 'UNKNOWN',
    'confidence': 70,
    'breakdown': {}
}

if duration < 2:
    analysis['detected_structure'] = 'MICRO_CONTENT'
    analysis['confidence'] = 90
elif duration < 15:
    analysis['detected_structure'] = 'SHORT_VIDEO'
    analysis['confidence'] = 85
    analysis['breakdown'] = {
        'Hook': '0-15%',
        'Body': '15-85%',
        'CTA/Outro': '85-100%'
    }
else:
    analysis['detected_structure'] = 'LONG_FORM'
    analysis['confidence'] = 80

with open(f'{analysis_dir}/structure_analysis.json', 'w') as f:
    json.dump(analysis, f, indent=2)

print(f"✓ Estructura: {analysis['detected_structure']}")
PYEOF

# Generar reporte
log_info "[5/5] Generando reporte..."

STATS_CONTENT=$(python3 - "$ANALYSIS_DIR" << 'PYEOF'
import sys, json
analysis_dir = sys.argv[1]
with open(f"{analysis_dir}/stats.json", 'r') as f:
    data = json.load(f)
print(f"- **Palabras:** {data['total_words']}")
print(f"- **Líneas:** {data['total_lines']}")
print(f"- **Duración estimada:** {data['estimated_duration_minutes']:.1f} min")
PYEOF
)

STRUCTURE_CONTENT=$(python3 - "$ANALYSIS_DIR" << 'PYEOF'
import sys, json
analysis_dir = sys.argv[1]
with open(f"{analysis_dir}/structure_analysis.json", 'r') as f:
    data = json.load(f)
print(f"**Tipo:** {data['detected_structure']}")
print(f"**Confianza:** {data['confidence']}%")
if 'breakdown' in data and data['breakdown']:
    print('\n**Desglose sugerido:**')
    for k, v in data['breakdown'].items():
        print(f"- {k}: {v}")
PYEOF
)

cat > "$ANALYSIS_DIR/ANALYSIS_REPORT.md" << MDEOF
# 📊 ANÁLISIS DE SUBTÍTULO

**Archivo:** $(basename "$SUB")
**Fecha:** $(date '+%Y-%m-%d %H:%M:%S')

---

## 📈 ESTADÍSTICAS

$STATS_CONTENT

---

## 🏗️ ESTRUCTURA DETECTADA

$STRUCTURE_CONTENT

---

## 📝 CONTENIDO (Primeras 20 líneas)

\`\`\`text
$(head -20 "$ANALYSIS_DIR/raw_text.txt")
\`\`\`

---

*Análisis generado automáticamente por Guion Experts Suite V2*
MDEOF

log_section "✓ ANÁLISIS COMPLETADO"
echo ""
log_success "Reporte: $ANALYSIS_DIR/ANALYSIS_REPORT.md"
echo "$ANALYSIS_DIR" > /tmp/last_analysis.txt
