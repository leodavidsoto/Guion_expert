#!/bin/bash
source scripts/lib.sh

[ -z "$1" ] && echo "Uso: ./scripts/validar.sh [output_dir]" && exit 1

OUT="$1"

log_section "VALIDACIÓN DE CALIDAD"

puntos=0
total=0

# Validar concepto
if [ -f "$OUT/concepto/result.txt" ]; then
    lineas=$(wc -l < "$OUT/concepto/result.txt")
    if [ $lineas -gt 30 ]; then
        log_success "Concepto: $lineas líneas ✓"
        puntos=$((puntos + 20))
    else
        log_error "Concepto muy corto: $lineas líneas"
    fi
else
    log_error "Concepto faltante"
fi
total=$((total + 20))

# Validar escenas
num_esc=$(ls "$OUT"/escenas/*.txt 2>/dev/null | wc -l)
if [ $num_esc -ge 15 ]; then
    log_success "Escenas: $num_esc archivos ✓"
    puntos=$((puntos + 30))
elif [ $num_esc -ge 10 ]; then
    log_info "Escenas: $num_esc archivos (aceptable)"
    puntos=$((puntos + 20))
else
    log_error "Pocas escenas: $num_esc"
fi
total=$((total + 30))

# Validar prompts
num_sd=$(ls "$OUT"/prompts_sd/*.txt 2>/dev/null | wc -l)
if [ $num_sd -eq $num_esc ]; then
    log_success "Prompts SD: $num_sd ✓"
    puntos=$((puntos + 25))
else
    log_error "Prompts SD incompletos: $num_sd de $num_esc"
fi
total=$((total + 25))

num_veo=$(ls "$OUT"/prompts_veo/*.json 2>/dev/null | wc -l)
if [ $num_veo -eq $num_esc ]; then
    log_success "Prompts Veo: $num_veo ✓"
    puntos=$((puntos + 25))
else
    log_error "Prompts Veo incompletos: $num_veo de $num_esc"
fi
total=$((total + 25))

# Calcular calificación
porcentaje=$((puntos * 100 / total))

echo ""
log_section "CALIFICACIÓN FINAL"
echo ""
echo "  Puntos: $puntos / $total"
echo "  Porcentaje: $porcentaje%"
echo ""

if [ $porcentaje -ge 90 ]; then
    echo "  🌟 EXCELENTE"
elif [ $porcentaje -ge 70 ]; then
    echo "  ✓ BUENO"
elif [ $porcentaje -ge 50 ]; then
    echo "  ⚠️  ACEPTABLE"
else
    echo "  ✗ NECESITA MEJORAS"
fi
echo ""
