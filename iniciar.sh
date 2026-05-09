#!/bin/bash

clear

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎬 GUION EXPERTS SUITE V2 — Claude Haiku 4.5"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Verificar directorio
if [ ! -f "ejecutar.sh" ]; then
    echo "❌ Error: No estás en el directorio correcto del proyecto"
    echo "   Ejecuta: cd ~/Desktop/ESCRIBE/Guion_expert && ./iniciar.sh"
    exit 1
fi

echo "📂 Directorio: $(pwd)"
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. VERIFICAR .ENV (API KEY DE ANTHROPIC)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔑 PASO 1/5: Verificando configuración Claude"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ ! -f ".env" ]; then
    echo "❌ No se encontró .env"
    echo "   Copia .env.example a .env y pegá tu API key de Anthropic"
    exit 1
fi

if grep -q "PEGAR_TU_API_KEY_AQUI\|REEMPLAZAR_CON_TU_KEY" .env; then
    echo "❌ El archivo .env todavía tiene un placeholder de API key"
    echo "   Editá .env y reemplazá ANTHROPIC_API_KEY con tu key real"
    exit 1
fi

if ! grep -q "^ANTHROPIC_API_KEY=sk-ant-" .env; then
    echo "⚠️  ANTHROPIC_API_KEY no parece válida (debería empezar con sk-ant-)"
fi

echo "✅ .env configurado"
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. VERIFICAR PYTHON + DEPENDENCIAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🐍 PASO 2/5: Verificando Python"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 no está instalado"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "✅ Python $PYTHON_VERSION"

# Activar venv si existe
if [ -d "venv" ]; then
    echo "📦 Activando entorno virtual..."
    source venv/bin/activate
fi

echo ""
echo "📦 Verificando dependencias Python..."

if [ -f "requirements.txt" ]; then
    pip3 install -r requirements.txt --quiet
    echo "✅ Dependencias instaladas/actualizadas"
else
    echo "⚠️  No se encontró requirements.txt"
fi

# Chequeo explícito de anthropic + dotenv
python3 -c "import anthropic, dotenv" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠️  Faltan paquetes clave. Instalando..."
    pip3 install anthropic python-dotenv --quiet
fi

echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. VERIFICAR ESTRUCTURA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📁 PASO 3/5: Verificando estructura"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

mkdir -p output logs webapp/uploads

REQUIRED_FILES=(
    "ejecutar.sh"
    "webapp/server.py"
    "webapp/llm_provider.py"
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
    exit 1
fi

echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. LIMPIAR PROCESOS PREVIOS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔄 PASO 4/5: Limpiando procesos previos"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if pgrep -f "python3 server.py" > /dev/null; then
    echo "⚠️  Deteniendo servidor previo..."
    pkill -f "python3 server.py"
    sleep 2
fi

if lsof -i :5001 > /dev/null 2>&1; then
    echo "⚠️  Liberando puerto 5001..."
    lsof -ti :5001 | xargs kill -9 2>/dev/null
    sleep 1
fi

echo "✅ Procesos limpiados"
echo ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. INICIAR SERVIDOR
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 PASO 5/5: Iniciando servidor"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd webapp

LOG_FILE="../logs/server_$(date +%Y%m%d_%H%M%S).log"

echo "📝 Log: $LOG_FILE"
echo ""

python3 -u server.py > "$LOG_FILE" 2>&1 &
SERVER_PID=$!

echo $SERVER_PID > ../.server.pid

echo "⏳ Esperando a que el servidor inicie..."
sleep 3

if ps -p $SERVER_PID > /dev/null 2>&1; then
    echo "✅ Servidor iniciado (PID: $SERVER_PID)"
else
    echo "❌ Error al iniciar servidor"
    echo ""
    echo "Ver logs:"
    echo "  tail -f $LOG_FILE"
    exit 1
fi

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
echo "✅ SISTEMA INICIADO — Claude Haiku 4.5"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🌐 URL:           http://localhost:5001"
echo "📁 Directorio:    $(pwd)"
echo "🔧 PID Server:    $SERVER_PID"
echo "📊 Log:           tail -f $LOG_FILE"
echo "🤖 LLM:           Claude Haiku 4.5 (Anthropic API)"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📖 COMANDOS ÚTILES"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Ver logs:        ./logs.sh    (o tail -f $LOG_FILE)"
echo "  Estado:          ./status.sh"
echo "  Detener:         ./stop.sh"
echo "  Reiniciar:       ./restart.sh"
echo "  Health check:    curl http://localhost:5001/api/health"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "🎬 Abriendo navegador..."
sleep 2

if command -v open &> /dev/null; then
    open http://localhost:5001
elif command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:5001
else
    echo "   Abre manualmente: http://localhost:5001"
fi

echo ""
echo "✅ ¡Listo!"
echo ""
