#!/bin/bash
cd "$(dirname "$0")"
source scripts/lib.sh

if [ -z "$1" ]; then
    cat << 'HELP'
╔═══════════════════════════════════════════════════╗
║   GUION EXPERTS SUITE V2                          ║
╚═══════════════════════════════════════════════════╝

Uso: ./ejecutar.sh "tu idea"

El sistema detecta AUTOMÁTICAMENTE el formato y estructura.

Ejemplos:
  ./ejecutar.sh "short de youtube sobre robots"
  ./ejecutar.sh "película sobre una banda"
  ./ejecutar.sh "promocionar evento en bar"
HELP
    exit 1
fi

if ! pgrep ollama > /dev/null; then
    log_info "Iniciando Ollama..."
    ollama serve > /tmp/ollama.log 2>&1 &
    sleep 5
fi

./scripts/pipeline.sh "$1"

OUT=$(cat /tmp/last_project.txt 2>/dev/null)
[ -z "$OUT" ] && OUT=$(cat /tmp/last_short.txt 2>/dev/null)

if [ -n "$OUT" ]; then
    echo ""
    echo "Proyecto: $OUT"
    echo ""
fi
