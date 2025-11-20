#!/bin/bash
source scripts/lib.sh

[ -z "$1" ] && echo "Uso: ./scripts/exportar.sh [output_dir] [formato]" && exit 1

OUT="$1"
FORMATO="${2:-pdf}"

log_section "EXPORTANDO A $FORMATO"

# Crear markdown completo
MD="$OUT/guion_completo.md"

cat > "$MD" << MDSTART
# GUION COMPLETO

**Fecha:** $(date '+%Y-%m-%d')
**Proyecto:** $(basename $OUT)

---

# CONCEPTO

$(cat $OUT/concepto/result.txt)

---

# ESTRUCTURA

$(cat $OUT/estructura/result.txt)

---

# ESCALETA

$(cat $OUT/escaleta/lista.txt)

---

# ESCENAS

MDSTART

# Agregar todas las escenas
for esc in "$OUT"/escenas/escena_*.txt; do
    [ ! -f "$esc" ] && continue
    num=$(basename "$esc" .txt | sed 's/escena_//')
    
    cat >> "$MD" << ESCMD

## ESCENA $num

\`\`\`
$(cat $esc)
\`\`\`

---

ESCMD
done

log_success "Markdown creado: $MD"

# Convertir a PDF con pandoc (si está instalado)
if command -v pandoc > /dev/null; then
    pandoc "$MD" -o "$OUT/guion.pdf" \
        --pdf-engine=pdflatex \
        -V geometry:margin=1in \
        -V fontsize=11pt 2>/dev/null && \
        log_success "PDF: $OUT/guion.pdf" || \
        log_info "PDF: requiere LaTeX instalado"
else
    log_info "Instala pandoc para generar PDF: brew install pandoc"
fi

echo ""
echo "Archivos disponibles:"
echo "  Markdown: $MD"
[ -f "$OUT/guion.pdf" ] && echo "  PDF: $OUT/guion.pdf"
echo ""
