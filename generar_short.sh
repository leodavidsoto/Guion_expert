#!/bin/bash
source scripts/lib.sh

cat << 'BANNER'
╔═══════════════════════════════════════════════════╗
║   GENERADOR DE CONTENIDO VERTICAL                 ║
║   YouTube Shorts • Reels • TikTok                 ║
╚═══════════════════════════════════════════════════╝
BANNER

echo ""
echo "Plataformas disponibles:"
echo "  1. YouTube Shorts (60s)"
echo "  2. Instagram Reels (15-90s)"
echo "  3. TikTok (15-180s)"
echo "  4. Multi-plataforma (adapta a todas)"
echo ""

read -p "Selecciona [1-4]: " opt

case $opt in
    1) PLAT="youtube" ;;
    2) PLAT="instagram" ;;
    3) PLAT="tiktok" ;;
    4) PLAT="multi" ;;
    *) echo "Opción inválida" && exit 1 ;;
esac

echo ""
read -p "Tu idea para $PLAT: " IDEA

if [ -z "$IDEA" ]; then
    echo "❌ Necesitas una idea"
    exit 1
fi

./scripts/pipeline_shorts.sh "$IDEA" "$PLAT"

if [ $? -eq 0 ]; then
    OUT=$(cat /tmp/last_short.txt)
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "✅ SHORT GENERADO"
    echo ""
    echo "📁 Ubicación: $OUT"
    echo ""
    echo "📄 Archivos:"
    echo "  • Script completo"
    echo "  • Timing por segundo"
    echo "  • Prompts visuales verticales"
    echo "  • Sugerencias de música"
    echo "  • Hashtags"
    echo ""
    echo "Ver script:"
    echo "  cat $OUT/script/full_script.txt"
    echo ""
fi
