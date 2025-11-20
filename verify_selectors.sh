#!/bin/bash

echo "═══════════════════════════════════════════════"
echo "🔍 VERIFICACIÓN DE SELECTORES"
echo "═══════════════════════════════════════════════"
echo ""

HTML_FILE="webapp/templates/index.html"

if [ ! -f "$HTML_FILE" ]; then
    echo "❌ Archivo no encontrado: $HTML_FILE"
    exit 1
fi

# Contar options de formato (excluir auto-detectar)
FORMATO_COUNT=$(grep -o '<option value="[A-Z_]*">' "$HTML_FILE" | grep -A1 'id="formatoSelect"' | grep -v 'value=""' | wc -l)

# Contar options de estructura (excluir auto-detectar)  
ESTRUCTURA_COUNT=$(grep -o '<option value="[A-Z_]*">' "$HTML_FILE" | grep -A1 'id="estructuraSelect"' | grep -v 'value=""' | wc -l)

# Contar optgroups
FORMATO_GROUPS=$(grep -c '<optgroup label.*Formato' "$HTML_FILE" || true)
ESTRUCTURA_GROUPS=$(grep -c '<optgroup label.*Estructura' "$HTML_FILE" || true)

echo "📺 FORMATOS:"
echo "   Total opciones: $FORMATO_COUNT"
echo "   Grupos (optgroups): $FORMATO_GROUPS"
echo ""

echo "📖 ESTRUCTURAS:"
echo "   Total opciones: $ESTRUCTURA_COUNT"
echo "   Grupos (optgroups): $ESTRUCTURA_GROUPS"
echo ""

# Verificar contra JSON
if [ -f "config/formats.json" ]; then
    JSON_FORMATOS=$(python3 -c "import json; data=json.load(open('config/formats.json')); print(sum(len(v) for v in data.values()))")
    echo "📊 Formatos en JSON: $JSON_FORMATOS"
fi

if [ -f "config/structures.json" ]; then
    JSON_ESTRUCTURAS=$(python3 -c "import json; data=json.load(open('config/structures.json')); print(sum(len(v) for v in data.values()))")
    echo "📊 Estructuras en JSON: $JSON_ESTRUCTURAS"
fi

echo ""
echo "═══════════════════════════════════════════════"

if [ "$ESTRUCTURA_COUNT" -ge 50 ] && [ "$FORMATO_COUNT" -ge 60 ]; then
    echo "✅ Selectores completos cargados correctamente"
else
    echo "⚠️  Faltan opciones en los selectores"
    echo "   Esperado: ~53 estructuras, ~70 formatos"
    echo "   Encontrado: $ESTRUCTURA_COUNT estructuras, $FORMATO_COUNT formatos"
fi
