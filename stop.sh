#!/bin/bash

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🛑 DETENIENDO GUION EXPERTS SUITE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Detener por PID guardado
if [ -f ".server.pid" ]; then
    SERVER_PID=$(cat .server.pid)
    if ps -p $SERVER_PID > /dev/null 2>&1; then
        echo "⚠️  Deteniendo servidor (PID: $SERVER_PID)..."
        kill $SERVER_PID
        sleep 2
        
        if ps -p $SERVER_PID > /dev/null 2>&1; then
            echo "   Forzando detención..."
            kill -9 $SERVER_PID
        fi
        
        echo "✅ Servidor detenido"
    else
        echo "ℹ️  Servidor ya estaba detenido"
    fi
    rm .server.pid
fi

# Detener procesos restantes
if pgrep -f "python3 server.py" > /dev/null; then
    echo "⚠️  Deteniendo procesos adicionales..."
    pkill -f "python3 server.py"
    pkill -f "ollama run"
    sleep 1
    echo "✅ Procesos detenidos"
fi

# Liberar puerto
if lsof -i :5001 > /dev/null 2>&1; then
    echo "⚠️  Liberando puerto 5001..."
    lsof -ti :5001 | xargs kill -9 2>/dev/null
    sleep 1
    echo "✅ Puerto liberado"
fi

echo ""
echo "✅ Sistema detenido completamente"
echo ""
