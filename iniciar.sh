#!/bin/bash

clear

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎬 GUION EXPERTS SUITE V2 - INICIO"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Verificar que estamos en el directorio correcto
if [ ! -f "ejecutar.sh" ]; then
    echo "❌ Error: No estás en el directorio guion_experts_suite_v2"
    echo "   Ejecuta: cd ~/guion_experts_suite_v2 && ./iniciar.sh"
    exit 1
fi

echo "📂 Directorio de trabajo: $(pwd)"
echo ""

# 1. Verificar Ollama
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 PASO 1: Verificando Ollama"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama no está instalado"
    echo "   Instala desde: https://ollama.ai"
    exit 1
fi

if ! pgrep -x "ollama" > /dev/null; then
    echo "⚠️  Ollama no está corriendo. Iniciando..."
    ollama serve > /tmp/ollama.log 2>&1 &
    sleep 3
    
    if pgrep -x "ollama" > /dev/null; then
        echo "✅ Ollama iniciado"
    else
        echo "❌ No se pudo iniciar Ollama"
        exit 1
    fi
else
    echo "✅ Ollama está corriendo"
fi

# Verificar modelos
echo ""
echo "📦 Verificando modelos..."
REQUIRED_MODELS=("llama3.2:3b" "qwen2.5:7b" "qwen2.5:14b")
MISSING_MODELS=()

for model in "${REQUIRED_MODELS[@]}"; do
    if ollama list | grep -q "$model"; then
        echo "  ✓ $model"
    else
        echo "  ✗ $model (falta)"
        MISSING_MODELS+=("$model")
    fi
done

if [ ${#MISSING_MODELS[@]} -gt 0 ]; then
    echo ""
    echo "⚠️  Faltan modelos. ¿Descargar ahora? (y/n)"
    read -t 10 answer || answer="n"
    
    if [ "$answer" = "y" ]; then
        for model in "${MISSING_MODELS[@]}"; do
            echo "📥 Descargando $model..."
            ollama pull "$model"
        done
    else
        echo "⚠️  Advertencia: Algunos modelos faltan. El sistema puede fallar."
    fi
fi

echo ""

# 2. Verificar Python y dependencias
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🐍 PASO 2: Verificando Python"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 no está instalado"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "✅ Python $PYTHON_VERSION"

# Verificar pip packages
echo ""
echo "📦 Verificando dependencias..."
REQUIRED_PACKAGES=("flask" "flask-socketio" "python-socketio")

for package in "${REQUIRED_PACKAGES[@]}"; do
    if python3 -c "import ${package//-/_}" 2>/dev/null; then
        echo "  ✓ $package"
    else
        echo "  ✗ $package (falta)"
        echo "    Instalando..."
        pip3 install "$package" --quiet
    fi
done

echo ""

# 3. Verificar estructura de directorios
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📁 PASO 3: Verificando estructura"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

REQUIRED_DIRS=("output" "prompts" "config" "scripts" "webapp/templates" "webapp/static")

for dir in "${REQUIRED_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        echo "  ✓ $dir"
    else
        echo "  ✗ $dir (creando...)"
        mkdir -p "$dir"
    fi
done

# Verificar archivos críticos
CRITICAL_FILES=(
    "ejecutar.sh"
    "webapp/server.py"
    "webapp/templates/index.html"
    "config/structures.json"
    "config/formats.json"
)

echo ""
echo "📄 Verificando archivos críticos..."
MISSING_FILES=0

for file in "${CRITICAL_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✓ $file"
    else
        echo "  ✗ $file (FALTA)"
        MISSING_FILES=$((MISSING_FILES + 1))
    fi
done

if [ $MISSING_FILES -gt 0 ]; then
    echo ""
    echo "❌ Faltan $MISSING_FILES archivos críticos"
    echo "   Ejecuta los scripts de configuración primero"
    exit 1
fi

echo ""

# 4. Detener procesos previos
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔄 PASO 4: Limpiando procesos previos"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Matar servidores previos
if pgrep -f "python3 server.py" > /dev/null; then
    echo "⚠️  Deteniendo servidor previo..."
    pkill -f "python3 server.py"
    sleep 2
    echo "  ✓ Servidor detenido"
fi

# Limpiar puertos
if lsof -i :5001 > /dev/null 2>&1; then
    echo "⚠️  Puerto 5001 en uso. Liberando..."
    lsof -ti :5001 | xargs kill -9 2>/dev/null
    sleep 1
    echo "  ✓ Puerto liberado"
fi

echo ""

# 5. Iniciar servidor
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 PASO 5: Iniciando servidor web"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd webapp

# Iniciar en background
python3 server.py > ../logs/server.log 2>&1 &
SERVER_PID=$!

echo "⏳ Esperando a que el servidor inicie..."
sleep 3

# Verificar que está corriendo
if ps -p $SERVER_PID > /dev/null; then
    echo "✅ Servidor iniciado (PID: $SERVER_PID)"
else
    echo "❌ Error al iniciar servidor"
    echo "   Ver logs: tail -f logs/server.log"
    exit 1
fi

# Verificar que responde
if curl -s http://localhost:5001/api/health > /dev/null; then
    echo "✅ Servidor respondiendo en puerto 5001"
else
    echo "⚠️  Servidor iniciado pero no responde aún"
    echo "   Espera unos segundos más..."
fi

cd ..

echo ""

# 6. Resumen final
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ SISTEMA INICIADO"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🌐 URL:        http://localhost:5001"
echo "📁 Directorio: $(pwd)"
echo "🔧 PID Server: $SERVER_PID"
echo "📊 Logs:       tail -f logs/server.log"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 ESTADÍSTICAS DEL SISTEMA"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Contar estructuras
if [ -f "config/structures.json" ]; then
    STRUCT_COUNT=$(python3 -c "import json; print(sum(len(v) for v in json.load(open('config/structures.json')).values()))" 2>/dev/null || echo "?")
    echo "📖 Estructuras: $STRUCT_COUNT"
fi

# Contar formatos
if [ -f "config/formats.json" ]; then
    FORMAT_COUNT=$(python3 -c "import json; print(sum(len(v) for v in json.load(open('config/formats.json')).values()))" 2>/dev/null || echo "?")
    echo "📺 Formatos:    $FORMAT_COUNT"
fi

# Contar prompts
PROMPT_COUNT=$(ls -1 prompts/*.txt 2>/dev/null | wc -l | tr -d ' ')
echo "🤖 Expertos:    $PROMPT_COUNT"

# Contar proyectos
if [ -d "output" ]; then
    PROJECT_COUNT=$(ls -1d output/*/ 2>/dev/null | wc -l | tr -d ' ')
    echo "📂 Proyectos:   $PROJECT_COUNT"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📖 COMANDOS ÚTILES"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Ver logs en tiempo real:"
echo "    tail -f logs/server.log"
echo ""
echo "  Detener servidor:"
echo "    kill $SERVER_PID"
echo "    # o"
echo "    ./detener.sh"
echo ""
echo "  Reiniciar todo:"
echo "    ./iniciar.sh"
echo ""
echo "  Pipeline desde terminal:"
echo "    ./ejecutar.sh \"tu idea aquí\""
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🎬 Abriendo navegador en 3 segundos..."
sleep 3

# Abrir navegador (Mac)
if command -v open &> /dev/null; then
    open http://localhost:5001
# Linux
elif command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:5001
else
    echo "   Abre manualmente: http://localhost:5001"
fi

echo ""
echo "✅ Sistema listo. ¡A crear guiones!"
echo ""

# Guardar PID para detener después
echo $SERVER_PID > .server.pid
