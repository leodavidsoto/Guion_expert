#!/bin/bash
cd "$(dirname "$0")"

[ -z "$1" ] && echo "Uso: ./ejecutar_con_storyboard.sh \"tu idea\"" && exit 1

if ! pgrep ollama > /dev/null; then
    ollama serve > /tmp/ollama.log 2>&1 &
    sleep 5
fi

echo "Verificando SD..."
if ! curl -s -m 3 -f http://127.0.0.1:7860/sdapi/v1/sd-models > /dev/null 2>&1; then
    echo ""
    echo "✗ SD no detectado"
    echo ""
    echo "Abre otra terminal:"
    echo "  cd ~/stable-diffusion-webui"
    echo "  ./webui.sh --api --listen"
    echo ""
    exit 1
fi

echo "✓ SD detectado"
echo ""

./scripts/pipeline.sh "$1"

OUT=$(cat /tmp/last_project.txt 2>/dev/null)
./scripts/storyboard.sh "$OUT"

open "$OUT/storyboard.html" 2>/dev/null

echo ""
echo "✓ TODO COMPLETADO"
echo ""
echo "Proyecto: $OUT"
echo "Storyboard: $OUT/storyboard.html"
echo ""
