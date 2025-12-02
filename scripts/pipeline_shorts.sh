#!/bin/bash
set -e
cd "$(dirname "$(dirname "$0")")"
source scripts/lib.sh
source config/models.conf

[ -z "$1" ] && cat << 'HELP' && exit 1
╔═══════════════════════════════════════════════════╗
║   PIPELINE PARA FORMATOS CORTOS                   ║
╚═══════════════════════════════════════════════════╝

Uso: ./scripts/pipeline_shorts.sh "idea" [plataforma]

Plataformas:
  youtube    - YouTube Shorts (60s)
  instagram  - Instagram Reels (15-90s)
  tiktok     - TikTok (15-180s)
  multi      - Versión para todas (auto-adapta)

Ejemplo:
  ./scripts/pipeline_shorts.sh "tutorial maquillaje" instagram
HELP

IDEA="$1"
PLATAFORMA="${2:-multi}"
OUT="output/short_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT"/{clasificacion,script,prompts_vertical,thumbnails}

log_section "PIPELINE SHORTS INICIADO"
log "Idea: $IDEA"
log "Plataforma: $PLATAFORMA"
log "Output: $OUT"

# Clasificación
log_info "[1/3] Clasificando contenido..."

if ! pgrep -x "ollama" > /dev/null; then
    log_error "Ollama no está corriendo"
    exit 1
fi

ollama_run_robust "$MODEL_CLASIFICADOR" \
    "$(cat prompts/00_clasificador_completo.txt)" \
    "PLATAFORMA OBJETIVO: $PLATAFORMA
IDEA: $IDEA" \
    "$OUT/clasificacion/result.txt"

TIPO=$(grep -i "FORMATO:" "$OUT/clasificacion/result.txt" | head -1 | sed 's/.*FORMATO:\s*//;s/\*//g' | tr -d ' \r\n')
DURACION=$(grep -i "DURACION_SEGUNDOS:" "$OUT/clasificacion/result.txt" | head -1 | sed 's/.*:\s*//' | tr -d ' \r\n')

log_success "Tipo: $TIPO ($DURACION segundos)"

# Seleccionar prompt según tipo
case $TIPO in
    YOUTUBE_SHORT) PROMPT_FILE="prompts/07_youtube_short.txt" ;;
    REEL_INSTAGRAM) PROMPT_FILE="prompts/08_reel_instagram.txt" ;;
    TIKTOK) PROMPT_FILE="prompts/09_tiktok.txt" ;;
    *) PROMPT_FILE="prompts/07_youtube_short.txt" ;;
esac

# Generar script
log_info "[2/3] Generando script para $TIPO..."

# Leer contexto de clasificación
CONTEXTO_CLASIFICACION=$(cat "$OUT/clasificacion/result.txt")

ollama_run_robust "$MODEL_CONCEPTO" \
    "$(cat $PROMPT_FILE)" \
    "IDEA ORIGINAL DEL USUARIO: $IDEA
DURACIÓN OBJETIVO: $DURACION segundos

CONTEXTO Y SUGERENCIAS DEL CLASIFICADOR:
$CONTEXTO_CLASIFICACION" \
    "$OUT/script/full_script.txt"

log_success "Script generado"

# Generar prompts visuales
log_info "[3/3] Generando prompts visuales..."

# Extraer descripciones visuales del script
grep -i "VISUAL:" "$OUT/script/full_script.txt" | sed 's/.*VISUAL:\s*//' > "$OUT/prompts_vertical/visuals_raw.txt" 2>/dev/null || echo "default visual" > "$OUT/prompts_vertical/visuals_raw.txt"

# Generar prompts numerados
counter=1
while IFS= read -r visual; do
    if [ -n "$visual" ]; then
        prompt_num=$(printf "%02d" $counter)
        echo "vertical 9:16 smartphone video frame, $visual, mobile content, sharp focus, vibrant colors, high contrast" > "$OUT/prompts_vertical/prompt_${prompt_num}.txt"
        counter=$((counter + 1))
    fi
done < "$OUT/prompts_vertical/visuals_raw.txt"

# Si no se generó ninguno, crear uno por defecto
if [ $counter -eq 1 ]; then
    echo "vertical 9:16 smartphone video, dynamic content, vibrant colors, mobile first" > "$OUT/prompts_vertical/prompt_01.txt"
    counter=2
fi

log_success "$((counter - 1)) prompts visuales generados"

log_section "✓ SHORT COMPLETADO"
echo ""
log_success "Script: $OUT/script/full_script.txt"
log_info "Duración: $DURACION segundos"
log_info "Prompts verticales: $((counter - 1))"
echo ""
echo "Ver script:"
echo "  cat $OUT/script/full_script.txt"
echo ""
echo "$OUT" > /tmp/last_short.txt
