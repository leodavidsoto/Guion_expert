#!/bin/bash
source scripts/lib.sh

INPUT="$1"

# Convertir a minúsculas para análisis
INPUT_LOWER=$(echo "$INPUT" | tr '[:upper:]' '[:lower:]')

# Detectar keywords explícitas
if [[ "$INPUT_LOWER" =~ (youtube short|short de youtube|short para youtube|short vertical) ]]; then
    echo "YOUTUBE_SHORT"
    exit 0
fi

if [[ "$INPUT_LOWER" =~ (reel|instagram reel|ig reel|reels de instagram) ]]; then
    echo "REEL_INSTAGRAM"
    exit 0
fi

if [[ "$INPUT_LOWER" =~ (tiktok|tik tok|video de tiktok) ]]; then
    echo "TIKTOK"
    exit 0
fi

if [[ "$INPUT_LOWER" =~ (story|historia efímera|stories) ]]; then
    echo "STORY"
    exit 0
fi

# Detectar duración mencionada
if [[ "$INPUT_LOWER" =~ ([0-9]+)\s*(segundo|seg|s|second) ]]; then
    SEGUNDOS="${BASH_REMATCH[1]}"
    
    if [ "$SEGUNDOS" -le 15 ]; then
        echo "STORY"
        exit 0
    elif [ "$SEGUNDOS" -le 60 ]; then
        echo "YOUTUBE_SHORT"
        exit 0
    elif [ "$SEGUNDOS" -le 180 ]; then
        echo "TIKTOK"
        exit 0
    fi
fi

# Si tiene keywords de vertical/móvil
if [[ "$INPUT_LOWER" =~ (vertical|móvil|movil|celular|teléfono|telefono|smartphone) ]]; then
    echo "YOUTUBE_SHORT"
    exit 0
fi

# Si menciona "rápido", "corto", "breve"
if [[ "$INPUT_LOWER" =~ (rápido|rapido|corto|breve|quick|fast) ]]; then
    echo "YOUTUBE_SHORT"
    exit 0
fi

# Default: dejar que Ollama decida
echo "UNKNOWN"
