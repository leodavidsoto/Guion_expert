#!/bin/bash

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 ESTADO DEL SISTEMA"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Ollama
echo "🔹 Ollama:"
if pgrep -x "ollama" > /dev/null; then
    echo "   ✅ Corriendo (PID: $(pgrep -x ollama))"
else
    echo "   ❌ No está corriendo"
fi

echo ""

# Servidor
echo "🔹 Servidor Web:"
if [ -f ".server.pid" ]; then
    SERVER_PID=$(cat .server.pid)
    if ps -p $SERVER_PID > /dev/null 2>&1; then
        echo "   ✅ Corriendo (PID: $SERVER_PID)"
        
        # Test de conexión
        if curl -s http://localhost:5001/api/health > /dev/null 2>&1; then
            echo "   ✅ Respondiendo en http://localhost:5001"
        else
            echo "   ⚠️  Puerto escuchando pero no responde"
        fi
    else
        echo "   ❌ No está corriendo"
    fi
else
    echo "   ❌ No hay PID guardado"
fi

echo ""

# Puerto
echo "🔹 Puerto 5001:"
if lsof -i :5001 > /dev/null 2>&1; then
    echo "   ✅ En uso"
else
    echo "   ⭕ Libre"
fi

echo ""

# Modelos
echo "🔹 Modelos Ollama:"
ollama list 2>/dev/null | grep -E "(llama3.2:3b|qwen2.5:7b|qwen2.5:14b)" | while read line; do
    echo "   ✓ $line"
done

echo ""

# Proyectos
if [ -d "output" ]; then
    PROJECT_COUNT=$(ls -1d output/*/ 2>/dev/null | wc -l | tr -d ' ')
    echo "🔹 Proyectos generados: $PROJECT_COUNT"
    
    if [ $PROJECT_COUNT -gt 0 ]; then
        echo "   Último: $(ls -td output/*/ 2>/dev/null | head -1 | xargs basename)"
    fi
fi

echo ""

# Logs recientes
if [ -d "logs" ]; then
    LATEST_LOG=$(ls -t logs/server_*.log 2>/dev/null | head -1)
    if [ -n "$LATEST_LOG" ]; then
        LOG_SIZE=$(du -h "$LATEST_LOG" | cut -f1)
        echo "🔹 Último log: $LATEST_LOG ($LOG_SIZE)"
    fi
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
