#!/bin/bash
source scripts/lib.sh

echo "Templates disponibles:"
echo ""
ls -1 templates/*.txt | nl
echo ""
read -p "Selecciona template (número): " num

TEMPLATE=$(ls -1 templates/*.txt | sed -n "${num}p")

if [ -z "$TEMPLATE" ]; then
    log_error "Template inválido"
    exit 1
fi

log_info "Template: $(basename $TEMPLATE .txt)"
echo ""
cat "$TEMPLATE"
echo ""
echo "─────────────────────────────────────────"
echo ""
read -p "Tu idea basada en este template: " IDEA

./ejecutar.sh "$IDEA"
