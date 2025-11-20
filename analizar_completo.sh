#!/bin/bash
source scripts/lib.sh

[ -z "$1" ] && cat << 'HELP' && exit 1
╔═══════════════════════════════════════════════════╗
║   ANÁLISIS COMPLETO DE GUION                      ║
╚═══════════════════════════════════════════════════╝

Uso: ./analizar_completo.sh archivo.pdf

Genera:
  • Análisis estructural
  • Presupuesto estimado
  • Reporte completo

Requisitos:
  brew install poppler
  O
  pip3 install PyPDF2 --break-system-packages
HELP

PDF="$1"

log_section "ANÁLISIS COMPLETO DE GUION"

# Análisis base
./scripts/analizar_pdf.sh "$PDF"

if [ $? -ne 0 ]; then
    log_error "Error en análisis base"
    exit 1
fi

# Obtener directorio del análisis
ANALYSIS=$(cat /tmp/last_analysis.txt)

echo ""
log_info "Ejecutando análisis adicionales..."
echo ""

# Presupuesto
log_info "[1/1] Generando presupuesto..."
./tools/generar_presupuesto.sh "$ANALYSIS"

echo ""
log_section "✓ ANÁLISIS COMPLETO TERMINADO"
echo ""
echo "📁 Directorio: $ANALYSIS"
echo ""
echo "📊 Reportes:"
echo "  1. ANALYSIS_REPORT.md - Análisis general"
echo "  2. BUDGET_ESTIMATE.md - Presupuesto"
echo ""
echo "Ver reporte:"
echo "  cat $ANALYSIS/ANALYSIS_REPORT.md"
echo ""
