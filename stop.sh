#!/bin/bash

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🛑 GUION EXPERTS SUITE V2 - DETENIENDO"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

pkill -f "python3 server.py" && echo "✓ Servidor web detenido" || echo "- No había servidor"
pkill -f "ejecutar.sh" && echo "✓ Pipelines detenidos" || echo "- No había pipelines"

echo "✅ Sistema detenido"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
