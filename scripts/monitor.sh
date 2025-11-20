#!/bin/bash

while true; do
    clear
    echo "╔═══════════════════════════════════════════════════╗"
    echo "║   📊 MONITOR EN TIEMPO REAL                       ║"
    echo "╚═══════════════════════════════════════════════════╝"
    echo ""
    echo "Presiona Ctrl+C para salir"
    echo ""

    ULTIMO=$(ls -td ~/guion_experts_suite_v2/output/*/ 2>/dev/null | head -1)

    if [ -n "$ULTIMO" ]; then
        echo "Proyecto: $(basename $ULTIMO)"
        echo ""
        
        echo "Archivos generados:"
        [ -f "$ULTIMO/clasificacion/result.txt" ] && echo "  ✓ Clasificación" || echo "  ⏳ Clasificación"
        [ -f "$ULTIMO/concepto/result.txt" ] && echo "  ✓ Concepto" || echo "  ⏳ Concepto"
        [ -f "$ULTIMO/estructura/result.txt" ] && echo "  ✓ Estructura" || echo "  ⏳ Estructura"
        [ -f "$ULTIMO/escaleta/lista.txt" ] && echo "  ✓ Escaleta" || echo "  ⏳ Escaleta"
        
        ESC=$(ls "$ULTIMO"/escenas/*.txt 2>/dev/null | wc -l | tr -d ' ')
        echo "  → Escenas: $ESC archivos"
        
        PROM_SD=$(ls "$ULTIMO"/prompts_sd/*.txt 2>/dev/null | wc -l | tr -d ' ')
        echo "  → Prompts SD: $PROM_SD archivos"
        
        PROM_VEO=$(ls "$ULTIMO"/prompts_veo/*.json 2>/dev/null | wc -l | tr -d ' ')
        echo "  → Prompts Veo: $PROM_VEO archivos"
        
        echo ""
        echo "Última modificación:"
        ls -lt "$ULTIMO"/*/* 2>/dev/null | head -3 | awk '{print "  " $9}'
    else
        echo "No hay proyectos en ejecución"
    fi
    
    echo ""
    echo "Actualizado: $(date '+%H:%M:%S')"
    
    sleep 2
done
