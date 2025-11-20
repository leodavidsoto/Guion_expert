#!/bin/bash
set -e
cd "$(dirname "$(dirname "$0")")"
source scripts/lib.sh
source config/models.conf

[ -z "$1" ] && echo "Uso: ./tools/director_flow.sh <escena_file>" && exit 1

ESCENA_FILE="$1"
OUT_DIR="$(dirname "$ESCENA_FILE")/flow"
mkdir -p "$OUT_DIR"

log_section "DIRECTOR FLOW - TABLA DE RODAJE"

if [ ! -f "$ESCENA_FILE" ]; then
    log_error "Archivo no encontrado: $ESCENA_FILE"
    exit 1
fi

ESCENA_CONTENT=$(cat "$ESCENA_FILE")

log_info "Generando tabla de rodaje cinematográfica..."

ollama_run_robust "$MODEL_DIRECTOR_FLOW" \
    "$(cat prompts/11_director_flow.txt)" \
    "$ESCENA_CONTENT" \
    "$OUT_DIR/tabla_rodaje.txt"

log_success "Tabla de rodaje generada"

# Extraer planos individuales
grep -n "🎥 PLANO" "$OUT_DIR/tabla_rodaje.txt" | while IFS=: read -r line_num content; do
    plano_num=$(echo "$content" | grep -oE "#[0-9]+" | tr -d '#')
    
    # Extraer el bloque completo de este plano
    next_line=$((line_num + 1))
    
    # Buscar siguiente plano o fin de archivo
    next_plano=$(grep -n "🎥 PLANO" "$OUT_DIR/tabla_rodaje.txt" | awk -F: -v current="$line_num" '$1 > current {print $1; exit}')
    
    if [ -z "$next_plano" ]; then
        # Es el último plano
        tail -n +$line_num "$OUT_DIR/tabla_rodaje.txt" > "$OUT_DIR/plano_$(printf %03d $plano_num).txt"
    else
        # Extraer desde línea actual hasta siguiente plano
        end_line=$((next_plano - 1))
        sed -n "${line_num},${end_line}p" "$OUT_DIR/tabla_rodaje.txt" > "$OUT_DIR/plano_$(printf %03d $plano_num).txt"
    fi
done

# Extraer solo los prompts para Flow
grep -A 10 "FLOW PROMPT" "$OUT_DIR/tabla_rodaje.txt" | grep -v "^--$" | grep -v "FLOW PROMPT" | sed '/^$/d' > "$OUT_DIR/prompts_flow.txt" 2>/dev/null || true

NUM_PLANOS=$(ls -1 "$OUT_DIR"/plano_*.txt 2>/dev/null | wc -l)
log_success "$NUM_PLANOS planos generados"

echo ""
echo "Ver tabla completa:"
echo "  cat $OUT_DIR/tabla_rodaje.txt"
echo ""
echo "Prompts para Flow:"
echo "  cat $OUT_DIR/prompts_flow.txt"
