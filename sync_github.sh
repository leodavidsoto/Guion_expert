#!/bin/bash

echo "🔄 Sincronizando con GitHub..."

# Intentar pull simple
git pull origin main --no-edit

if [ $? -eq 0 ]; then
    echo "✅ Pull exitoso"
    
    # Ahora push
    git push origin main
    
    if [ $? -eq 0 ]; then
        echo "✅ Push exitoso"
        echo "🌐 https://github.com/leodavidsoto/Guion_expert"
    else
        echo "❌ Error en push"
    fi
else
    echo "⚠️ Conflictos detectados"
    echo ""
    echo "Opciones:"
    echo "1. Resolver manualmente"
    echo "2. Forzar push (sobrescribe remoto)"
    echo ""
    read -p "¿Forzar push? (y/n): " answer
    
    if [ "$answer" = "y" ]; then
        git push origin main --force
        echo "✅ Push forzado exitoso"
    else
        echo "Resuelve conflictos manualmente y ejecuta:"
        echo "  git add ."
        echo "  git commit -m 'Resolve conflicts'"
        echo "  git push origin main"
    fi
fi
