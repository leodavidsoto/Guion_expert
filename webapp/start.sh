#!/bin/bash

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎬 GUION EXPERTS SUITE V2 - INICIO COMPLETO"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 1. Verificar Ollama
echo -e "${BLUE}1. Verificando Ollama...${NC}"
if pgrep -x "ollama" > /dev/null; then
    echo -e "${GREEN}   ✓ Ollama está corriendo${NC}"
else
    echo -e "${YELLOW}   ⚠ Iniciando Ollama...${NC}"
    ollama serve > /dev/null 2>&1 &
    sleep 3
    if pgrep -x "ollama" > /dev/null; then
        echo -e "${GREEN}   ✓ Ollama iniciado${NC}"
    else
        echo -e "${RED}   ✗ Error: No se pudo iniciar Ollama${NC}"
        exit 1
    fi
fi

# 2. Verificar modelos necesarios
echo -e "${BLUE}2. Verificando modelos...${NC}"
REQUIRED_MODELS=("llama3.2:3b" "qwen2.5:7b" "qwen2.5:14b")
MISSING_MODELS=()

for model in "${REQUIRED_MODELS[@]}"; do
    if ollama list | grep -q "$model"; then
        echo -e "${GREEN}   ✓ $model${NC}"
    else
        echo -e "${YELLOW}   ⚠ Falta: $model${NC}"
        MISSING_MODELS+=("$model")
    fi
done

if [ ${#MISSING_MODELS[@]} -gt 0 ]; then
    echo ""
    echo -e "${YELLOW}   Modelos faltantes. ¿Descargar ahora? (y/n)${NC}"
    read -t 10 answer || answer="n"
    
    if [ "$answer" = "y" ]; then
        for model in "${MISSING_MODELS[@]}"; do
            echo -e "${BLUE}   Descargando $model...${NC}"
            ollama pull "$model"
        done
    else
        echo -e "${YELLOW}   Continuando sin descargar modelos...${NC}"
    fi
fi

# 3. Verificar estructura de directorios
echo -e "${BLUE}3. Verificando estructura...${NC}"
REQUIRED_DIRS=(
    "output"
    "config"
    "prompts"
    "scripts"
    "webapp"
    "webapp/templates"
    "webapp/static"
    "tools"
)

for dir in "${REQUIRED_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        echo -e "${GREEN}   ✓ $dir${NC}"
    else
        echo -e "${YELLOW}   ⚠ Creando $dir${NC}"
        mkdir -p "$dir"
    fi
done

# 4. Verificar archivos críticos
echo -e "${BLUE}4. Verificando archivos...${NC}"
REQUIRED_FILES=(
    "ejecutar.sh"
    "config/structures.json"
    "config/formats.json"
    "webapp/server.py"
    "webapp/templates/index.html"
)

MISSING_FILES=()
for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}   ✓ $file${NC}"
    else
        echo -e "${RED}   ✗ Falta: $file${NC}"
        MISSING_FILES+=("$file")
    fi
done

if [ ${#MISSING_FILES[@]} -gt 0 ]; then
    echo -e "${RED}   Error: Faltan archivos críticos${NC}"
    echo -e "${YELLOW}   Ejecuta los scripts de setup primero${NC}"
    exit 1
fi

# 5. Limpiar procesos anteriores
echo -e "${BLUE}5. Limpiando procesos anteriores...${NC}"
pkill -f "python3 server.py" 2>/dev/null && echo -e "${GREEN}   ✓ Servidor web detenido${NC}" || echo -e "${YELLOW}   - No había servidor corriendo${NC}"
pkill -f "ejecutar.sh" 2>/dev/null && echo -e "${GREEN}   ✓ Pipelines detenidos${NC}" || echo -e "${YELLOW}   - No había pipelines corriendo${NC}"

# 6. Iniciar servidor web
echo -e "${BLUE}6. Iniciando servidor web...${NC}"
cd webapp
python3 server.py > ../logs/server.log 2>&1 &
SERVER_PID=$!
cd ..

sleep 3

if ps -p $SERVER_PID > /dev/null; then
    echo -e "${GREEN}   ✓ Servidor iniciado (PID: $SERVER_PID)${NC}"
else
    echo -e "${RED}   ✗ Error al iniciar servidor${NC}"
    cat logs/server.log
    exit 1
fi

# 7. Información final
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}✅ SISTEMA LISTO${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "${BLUE}🌐 Web UI:${NC}       http://localhost:5001"
echo -e "${BLUE}📊 Logs servidor:${NC} tail -f logs/server.log"
echo -e "${BLUE}📁 Proyectos:${NC}     ls -lth output/"
echo -e "${BLUE}🛑 Detener:${NC}       ./stop.sh"
echo ""
echo -e "${YELLOW}Presiona Ctrl+C para ver logs en tiempo real${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 8. Seguir logs en tiempo real
tail -f logs/server.log
