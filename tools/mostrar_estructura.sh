#!/bin/bash
source scripts/lib.sh

[ -z "$1" ] && PROYECTO=$(cat /tmp/last_project.txt 2>/dev/null) || PROYECTO="$1"

[ -z "$PROYECTO" ] && echo "Uso: ./tools/mostrar_estructura.sh [proyecto_dir]" && exit 1

log_section "ESTRUCTURA DETECTADA"

echo "Proyecto: $(basename $PROYECTO)"
echo ""

if [ -f "$PROYECTO/clasificacion/result.txt" ]; then
    echo "═══════════════════════════════════════"
    cat "$PROYECTO/clasificacion/result.txt"
    echo "═══════════════════════════════════════"
fi

echo ""
echo "Estructura completa:"
echo "  cat $PROYECTO/estructura/result.txt"
