#!/bin/bash
set -e

echo "🧪 TEST PIPELINE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Test simple
./ejecutar.sh "test rápido: poema visual experimental" &
PID=$!

echo "⏱️  PID: $PID"
echo "⏱️  Esperando 60 segundos..."

# Monitor por 60 segundos
for i in {1..12}; do
    sleep 5
    if ps -p $PID > /dev/null 2>&1; then
        echo "⏳ Segundo $((i*5)): Proceso activo"
    else
        echo "✅ Proceso terminó"
        wait $PID
        EXIT_CODE=$?
        echo "📊 Código de salida: $EXIT_CODE"
        break
    fi
done

# Si sigue corriendo después de 60s
if ps -p $PID > /dev/null 2>&1; then
    echo "⚠️  Proceso aún corriendo después de 60s"
    echo "📁 Ver último proyecto:"
    ls -lth output/ | head -3
    
    echo ""
    echo "¿Matar proceso? (y/n)"
    read -t 10 answer || answer="n"
    
    if [ "$answer" = "y" ]; then
        kill $PID
        echo "❌ Proceso terminado"
    fi
else
    echo "✅ Test completado"
    echo "📁 Último proyecto:"
    ls -lth output/ | head -3
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
