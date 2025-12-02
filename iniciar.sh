#!/bin/bash

clear

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎬 GUION EXPERTS SUITE V2"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Verificar directorio
if [ ! -f "ejecutar.sh" ]; then
    echo "❌ Error: No estás en el directorio correcto"
    echo "   Ejecuta: cd ~/guion_experts_suite_v2 && ./iniciar.sh"
    exit 1
fi

echo "📂 Directorio: $(pwd)"
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. VERIFICAR OLLAMA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 PASO 1/6: Verificando Ollama"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama no está instalado"
    echo ""
    echo "Instálalo desde: https://ollama.ai"
    echo "O ejecuta: curl -fsSL https://ollama.ai/install.sh | sh"
    exit 1
fi

if ! pgrep -x "ollama" > /dev/null; then
    echo "⚠️  Ollama no está corriendo. Iniciando..."
    ollama serve > /tmp/ollama_$(date +%s).log 2>&1 &
    sleep 5
    
    if pgrep -x "ollama" > /dev/null; then
        echo "✅ Ollama iniciado"
    else
        echo "❌ No se pudo iniciar Ollama"
        echo "   Intenta manualmente: ollama serve"
        exit 1
    fi
else
    echo "✅ Ollama está corriendo"
fi

echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. VERIFICAR MODELOS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📦 PASO 2/6: Verificando modelos"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Cargar modelos desde config
if [ -f "config/models.conf" ]; then
    source config/models.conf
    REQUIRED_MODELS=("$MODEL_CLASIFICADOR" "$MODEL_CONCEPTO" "$MODEL_ARQUITECTO")
    # Eliminar duplicados
    REQUIRED_MODELS=($(echo "${REQUIRED_MODELS[@]}" | tr ' ' '\n' | sort -u | tr '\n' ' '))
else
    echo "⚠️  No se encontró config/models.conf, usando defaults..."
    REQUIRED_MODELS=("llama3.2:3b" "qwen2.5:7b" "qwen2.5:14b")
fi

MISSING_MODELS=()
ALL_MODELS_OK=true

for model in "${REQUIRED_MODELS[@]}"; do
    if ollama list | grep -q "^${model}"; then
        echo "  ✓ $model"
    else
        echo "  ✗ $model (falta)"
        MISSING_MODELS+=("$model")
        ALL_MODELS_OK=false
    fi
done

if [ "$ALL_MODELS_OK" = false ]; then
    echo ""
    echo "⚠️  Faltan ${#MISSING_MODELS[@]} modelo(s)"
    echo ""
    echo "¿Descargar ahora? (y/n) [timeout 15s]"
    read -t 15 answer || answer="n"
    
    if [ "$answer" = "y" ]; then
        for model in "${MISSING_MODELS[@]}"; do
            echo ""
            echo "📥 Descargando $model..."
            ollama pull "$model"
        done
    else
        echo "⚠️  Continuando sin todos los modelos"
        echo "   El sistema puede fallar en algunos expertos"
    fi
fi

echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. VERIFICAR PYTHON
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🐍 PASO 3/6: Verificando Python"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 no está instalado"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "✅ Python $PYTHON_VERSION"

# Verificar dependencias
echo ""
echo "📦 Verificando dependencias Python..."

if [ -f "requirements.txt" ]; then
    pip3 install -r requirements.txt --quiet
    echo "✅ Dependencias instaladas/actualizadas"
else
    echo "⚠️  No se encontró requirements.txt"
    PACKAGES=("flask" "flask_socketio" "python_socketio")
    for package in "${PACKAGES[@]}"; do
        pip3 install "$package" --quiet
    done
fi

echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. VERIFICAR ESTRUCTURA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📁 PASO 4/6: Verificando estructura"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Crear directorios necesarios
mkdir -p output logs webapp/uploads

REQUIRED_FILES=(
    "ejecutar.sh"
    "webapp/server.py"
    "webapp/templates/index.html"
    "config/structures.json"
    "config/formats.json"
)

MISSING_FILES=0
for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✓ $file"
    else
        echo "  ✗ $file (FALTA)"
        MISSING_FILES=$((MISSING_FILES + 1))
    fi
done

if [ $MISSING_FILES -gt 0 ]; then
    echo ""
    echo "❌ Faltan $MISSING_FILES archivo(s) crítico(s)"
    echo "   El repositorio puede estar incompleto"
    exit 1
fi

echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. LIMPIAR PROCESOS PREVIOS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔄 PASO 5/6: Limpiando procesos previos"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Detener servidor previo
if pgrep -f "python3 server.py" > /dev/null; then
    echo "⚠️  Deteniendo servidor previo..."
    pkill -f "python3 server.py"
    sleep 2
fi

# Limpiar puerto 5001
if lsof -i :5001 > /dev/null 2>&1; then
    echo "⚠️  Liberando puerto 5001..."
    lsof -ti :5001 | xargs kill -9 2>/dev/null
    sleep 1
fi

echo "✅ Procesos limpiados"
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. INICIAR SERVIDOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 PASO 6/6: Iniciando servidor"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd webapp

# Crear log con timestamp
LOG_FILE="../logs/server_$(date +%Y%m%d_%H%M%S).log"

echo "📝 Log: $LOG_FILE"
echo ""

# Iniciar servidor en background
python3 -u server.py > "$LOG_FILE" 2>&1 &
SERVER_PID=$!

# Guardar PID
echo $SERVER_PID > ../.server.pid

echo "⏳ Esperando a que el servidor inicie..."
sleep 3

# Verificar que está corriendo
if ps -p $SERVER_PID > /dev/null 2>&1; then
    echo "✅ Servidor iniciado (PID: $SERVER_PID)"
else
    echo "❌ Error al iniciar servidor"
    echo ""
    echo "Ver logs:"
    echo "  tail -f $LOG_FILE"
    exit 1
fi

# Verificar que responde
echo "⏳ Verificando respuesta del servidor..."
sleep 2

if curl -s http://localhost:5001/api/health > /dev/null 2>&1; then
    echo "✅ Servidor respondiendo correctamente"
else
    echo "⚠️  Servidor iniciado pero no responde aún"
    echo "   Dale unos segundos más..."
fi

cd ..

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ SISTEMA INICIADO"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🌐 URL:           http://localhost:5001"
echo "📁 Directorio:    $(pwd)"
echo "🔧 PID Server:    $SERVER_PID"
echo "📊 Log:           tail -f $LOG_FILE"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 ESTADÍSTICAS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Contar recursos
if [ -f "config/structures.json" ]; then
    STRUCT_COUNT=$(python3 -c "import json; print(sum(len(v) for v in json.load(open('config/structures.json')).values()))" 2>/dev/null || echo "?")
    echo "📖 Estructuras:   $STRUCT_COUNT"
fi

if [ -f "config/formats.json" ]; then
    FORMAT_COUNT=$(python3 -c "import json; print(sum(len(v) for v in json.load(open('config/formats.json')).values()))" 2>/dev/null || echo "?")
    echo "📺 Formatos:      $FORMAT_COUNT"
fi

PROMPT_COUNT=$(ls -1 prompts/*.txt 2>/dev/null | wc -l | tr -d ' ')
echo "🤖 Expertos:      $PROMPT_COUNT"

if [ -d "output" ]; then
    PROJECT_COUNT=$(ls -1d output/*/ 2>/dev/null | wc -l | tr -d ' ')
    echo "📂 Proyectos:     $PROJECT_COUNT"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📖 COMANDOS ÚTILES"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Ver logs en tiempo real:"
echo "    ./logs.sh"
echo ""
echo "  Verificar estado:"
echo "    ./status.sh"
echo ""
echo "  Detener sistema:"
echo "    ./stop.sh"
echo ""
echo "  Reiniciar:"
echo "    ./restart.sh"
echo ""
echo "  Pipeline desde terminal:"
echo "    ./ejecutar.sh \"tu idea aquí\""
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🎬 Abriendo navegador..."
sleep 2

# Abrir navegador
if command -v open &> /dev/null; then
    open http://localhost:5001
elif command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:5001
else
    echo "   Abre manualmente: http://localhost:5001"
fi

echo ""
echo "✅ ¡Listo! El sistema está funcionando"
echo ""
