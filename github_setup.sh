#!/bin/bash

echo "🚀 GITHUB SETUP HELPER"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Pedir usuario de GitHub
read -p "👤 Tu usuario de GitHub: " GITHUB_USER

# Pedir nombre del repo (con default)
read -p "📦 Nombre del repo [guion-experts-suite-v2]: " REPO_NAME
REPO_NAME=${REPO_NAME:-guion-experts-suite-v2}

# Construir URL
REPO_URL="https://github.com/$GITHUB_USER/$REPO_NAME.git"

echo ""
echo "📋 Configuración:"
echo "   Usuario: $GITHUB_USER"
echo "   Repo: $REPO_NAME"
echo "   URL: $REPO_URL"
echo ""

read -p "¿Continuar? (y/n): " confirm

if [ "$confirm" != "y" ]; then
    echo "❌ Cancelado"
    exit 1
fi

echo ""
echo "⚙️  Configurando..."

# Remover remote anterior si existe
git remote remove origin 2>/dev/null

# Agregar nuevo remote
git remote add origin "$REPO_URL"

# Verificar
if git remote -v | grep -q "origin"; then
    echo "✅ Remote configurado correctamente"
else
    echo "❌ Error configurando remote"
    exit 1
fi

echo ""
echo "📤 Subiendo a GitHub..."

# Push
git branch -M main
git push -u origin main

if [ $? -eq 0 ]; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✅ ÉXITO - Proyecto subido a GitHub"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "🌐 Ver tu proyecto:"
    echo "   https://github.com/$GITHUB_USER/$REPO_NAME"
    echo ""
    echo "📋 Próximos pasos sugeridos:"
    echo ""
    echo "1. Agregar topics al repo:"
    echo "   • ai"
    echo "   • screenwriting"
    echo "   • ollama"
    echo "   • python"
    echo "   • flask"
    echo ""
    echo "2. Configurar GitHub Pages (para docs):"
    echo "   Settings → Pages → Source: main → /docs"
    echo ""
    echo "3. Agregar badges al README:"
    echo "   • Stars"
    echo "   • Forks"
    echo "   • Issues"
    echo "   • License"
    echo ""
    echo "4. Configurar Discussions:"
    echo "   Settings → Features → Discussions: ✓"
    echo ""
    echo "5. Proteger rama main:"
    echo "   Settings → Branches → Add rule"
    echo "   → Require PR reviews before merging"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
else
    echo ""
    echo "❌ Error subiendo a GitHub"
    echo ""
    echo "Posibles causas:"
    echo "1. El repositorio no existe en GitHub"
    echo "2. No tienes permisos de escritura"
    echo "3. Necesitas autenticación (Personal Access Token)"
    echo ""
    echo "Solución:"
    echo "1. Crea el repo en GitHub primero: https://github.com/new"
    echo "2. Configura tu token: gh auth login"
    echo "3. Intenta de nuevo"
fi
