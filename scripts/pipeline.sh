#!/bin/bash
set -e
cd "$(dirname "$(dirname "$0")")"
source scripts/lib.sh
source config/models.conf
source config/production.conf

[ -z "$1" ] && echo "Uso: ./scripts/pipeline.sh \"idea\"" && exit 1

IDEA="$1"
OUT="output/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT"/{clasificacion,concepto,estructura,escaleta,escenas,prompts_sd,prompts_veo}

log_section "PIPELINE CON AUTO-DETECCIÓN DE ESTRUCTURA"
log "Idea: $IDEA"

if ! pgrep -x "ollama" > /dev/null; then
    log_error "Ollama no está corriendo"
    exit 1
fi

# CLASIFICACIÓN COMPLETA (Formato + Estructura)
log_info "[1/7] CLASIFICACIÓN DUAL (Formato + Estructura)..."

if ! ollama_run_robust "$MODEL_CLASIFICADOR" \
    "$(cat prompts/00_clasificador_completo.txt)" \
    "$IDEA" \
    "$OUT/clasificacion/result.txt"; then
    log_error "Fallo en clasificación"
    exit 1
fi

# Extraer información
FORMATO=$(grep -i "FORMATO:" "$OUT/clasificacion/result.txt" | head -1 | sed 's/.*FORMATO:\s*//;s/\*//g' | tr -d ' \r\n')
ESTRUCTURA=$(grep -i "ESTRUCTURA_NARRATIVA:" "$OUT/clasificacion/result.txt" | head -1 | sed 's/.*ESTRUCTURA_NARRATIVA:\s*//;s/\*//g' | tr -d ' \r\n')
DURACION_MIN=$(grep -i "DURACION_MINUTOS:" "$OUT/clasificacion/result.txt" | head -1 | sed 's/.*:\s*//' | tr -d ' \r\n')

[ -z "$FORMATO" ] && FORMATO="CORTO"
[ -z "$ESTRUCTURA" ] && ESTRUCTURA="THREE_ACT"

log_success "Formato: $FORMATO"
log_success "Estructura: $ESTRUCTURA"
log_info "Duración: $DURACION_MIN minutos"

# Mostrar justificaciones
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
grep "JUSTIFICACION_" "$OUT/clasificacion/result.txt" | sed 's/.*: /  /'
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Si es formato corto, redirigir
if [[ "$ESTRUCTURA" == "SIMPLE" ]]; then
    log_info "Formato corto detectado, usando pipeline especializado..."
    exec ./scripts/pipeline_shorts.sh "$IDEA" "youtube"
    exit 0
fi

# CONCEPTO
log_info "[2/7] CONCEPTO"
if ! ollama_run_robust "$MODEL_CONCEPTO" \
    "$(cat prompts/01_concepto.txt)" \
    "FORMATO: $FORMATO
ESTRUCTURA: $ESTRUCTURA
IDEA: $IDEA" \
    "$OUT/concepto/result.txt"; then
    log_error "Fallo en concepto"
    exit 1
fi
log_success "Concepto: $(wc -l < $OUT/concepto/result.txt) líneas"

# ESTRUCTURA con prompt específico
log_info "[3/7] ESTRUCTURA: $ESTRUCTURA"

PROMPT_ESTRUCTURA=$(./scripts/selector_prompt_estructura.sh "$ESTRUCTURA")
log_info "Usando: $PROMPT_ESTRUCTURA"

if ! ollama_run_robust "$MODEL_ARQUITECTO" \
    "$(cat $PROMPT_ESTRUCTURA)" \
    "$(cat $OUT/concepto/result.txt)" \
    "$OUT/estructura/result.txt"; then
    log_error "Fallo en estructura"
    exit 1
fi
log_success "Estructura $ESTRUCTURA generada"

# ESCALETA
log_info "[4/7] ESCALETA"
NUM_ESC=$(num_escenas "$FORMATO")
log_info "Objetivo: $NUM_ESC escenas"

if ! ollama_run_robust "$MODEL_ESCALETISTA" \
    "$(cat prompts/03_escaletista.txt)

Genera EXACTAMENTE $NUM_ESC escenas basadas en la estructura $ESTRUCTURA." \
    "$(cat $OUT/estructura/result.txt)" \
    "$OUT/escaleta/result.txt"; then
    log_error "Fallo en escaleta"
    exit 1
fi

grep -E "^[0-9]+\." "$OUT/escaleta/result.txt" > "$OUT/escaleta/lista.txt" 2>/dev/null || \
    echo "1. INT. LUGAR - DÍA - Acción." > "$OUT/escaleta/lista.txt"

NUM_REAL=$(wc -l < "$OUT/escaleta/lista.txt")
log_success "$NUM_REAL escenas generadas"

# ESCENAS
log_info "[5/7] ESCRIBIENDO $NUM_REAL ESCENAS"
echo ""

c=0
while IFS= read -r linea; do
    c=$((c+1))
    num=$(printf "%03d" $c)
    printf "\r  Escena %d/%d" $c $NUM_REAL
    
    ollama_run_robust "$MODEL_DIALOGUISTA" \
        "$(cat prompts/04_dialoguista.txt)" \
        "$linea" \
        "$OUT/escenas/escena_${num}.txt" 2>/dev/null || \
        echo "ERROR" > "$OUT/escenas/escena_${num}.txt"
done < "$OUT/escaleta/lista.txt"

echo ""
log_success "$NUM_REAL escenas escritas"

# PROMPTS
log_info "[6/7] GENERANDO PROMPTS SD"
for esc in "$OUT"/escenas/escena_*.txt; do
    [ ! -f "$esc" ] && continue
    num=$(basename "$esc" .txt | sed 's/escena_//')
    
    ollama_run_robust "$MODEL_PROMPTS_SD" \
        "$(cat prompts/06_sd.txt)" \
        "$(head -c 400 $esc)" \
        "$OUT/prompts_sd/prompt_${num}.txt" 2>/dev/null || \
        echo "cinematic, 4k" > "$OUT/prompts_sd/prompt_${num}.txt"
done
log_success "Prompts SD: $(ls $OUT/prompts_sd/*.txt 2>/dev/null | wc -l)"

log_info "[7/7] GENERANDO PROMPTS VEO"
for esc in "$OUT"/escenas/escena_*.txt; do
    [ ! -f "$esc" ] && continue
    num=$(basename "$esc" .txt | sed 's/escena_//')
    
    ollama_run_robust "$MODEL_PROMPTS_VEO" \
        "$(cat prompts/05_veo_flow.txt)" \
        "$(cat $esc)" \
        "$OUT/prompts_veo/veo_${num}.json" 2>/dev/null || \
        echo '{"plano":"default"}' > "$OUT/prompts_veo/veo_${num}.json"
done
log_success "Prompts Veo: $(ls $OUT/prompts_veo/*.json 2>/dev/null | wc -l)"

echo ""
log_section "✓ PIPELINE COMPLETADO"
echo ""
echo "📁 Proyecto: $OUT"
echo "🎬 Formato: $FORMATO"
echo "📖 Estructura: $ESTRUCTURA"
echo "⏱️  Duración: $DURACION_MIN minutos"
echo "📄 Escenas: $NUM_REAL"
echo ""
echo "Ver estructura:"
echo "  cat $OUT/estructura/result.txt"
echo ""
echo "$OUT" > /tmp/last_project.txt
