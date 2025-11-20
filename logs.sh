#!/bin/bash

echo "📝 Logs en tiempo real..."
echo "Presiona Ctrl+C para salir"
echo ""

LATEST_LOG=$(ls -t logs/server_*.log 2>/dev/null | head -1)

if [ -n "$LATEST_LOG" ]; then
    tail -f "$LATEST_LOG"
else
    echo "❌ No hay logs disponibles"
    echo "   El servidor no se ha iniciado aún"
fi
