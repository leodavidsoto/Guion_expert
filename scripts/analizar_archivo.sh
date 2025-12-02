#!/bin/bash
source scripts/lib.sh

FILE="$1"

if [ -z "$FILE" ]; then
    log_error "Uso: ./scripts/analizar_archivo.sh <archivo>"
    exit 1
fi

if [ ! -f "$FILE" ]; then
    log_error "Archivo no encontrado: $FILE"
    exit 1
fi

EXTENSION="${FILE##*.}"
EXTENSION=$(echo "$EXTENSION" | tr '[:upper:]' '[:lower:]')

log_info "Detectando tipo de archivo: .$EXTENSION"

case "$EXTENSION" in
    pdf)
        ./scripts/analizar_pdf.sh "$FILE"
        ;;
    srt|vtt)
        ./scripts/analizar_sub.sh "$FILE"
        ;;
    txt|fountain)
        # Por ahora tratamos txt/fountain como PDF (extracción directa)
        # Podríamos hacer un script específico si es necesario
        ./scripts/analizar_pdf.sh "$FILE"
        ;;
    *)
        log_error "Formato no soportado: .$EXTENSION"
        exit 1
        ;;
esac
