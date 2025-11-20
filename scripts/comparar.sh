#!/bin/bash
source scripts/lib.sh

echo "Proyectos disponibles:"
echo ""

ls -td output/*/ | head -10 | nl

echo ""
echo "Selecciona dos proyectos para comparar (números):"
read -p "Proyecto 1: " p1
read -p "Proyecto 2: " p2

PROJ1=$(ls -td output/*/ | sed -n "${p1}p")
PROJ2=$(ls -td output/*/ | sed -n "${p2}p")

log_section "COMPARACIÓN"

echo "Proyecto 1: $(basename $PROJ1)"
echo "Proyecto 2: $(basename $PROJ2)"
echo ""

# Comparar estadísticas
echo "ESTADÍSTICAS:"
printf "%-20s %15s %15s\n" "Métrica" "Proyecto 1" "Proyecto 2"
echo "────────────────────────────────────────────────"

esc1=$(ls "$PROJ1"/escenas/*.txt 2>/dev/null | wc -l)
esc2=$(ls "$PROJ2"/escenas/*.txt 2>/dev/null | wc -l)
printf "%-20s %15d %15d\n" "Escenas" $esc1 $esc2

lineas1=$(cat "$PROJ1"/concepto/result.txt 2>/dev/null | wc -l)
lineas2=$(cat "$PROJ2"/concepto/result.txt 2>/dev/null | wc -l)
printf "%-20s %15d %15d\n" "Líneas concepto" $lineas1 $lineas2

size1=$(du -sh "$PROJ1" | cut -f1)
size2=$(du -sh "$PROJ2" | cut -f1)
printf "%-20s %15s %15s\n" "Tamaño total" $size1 $size2

echo ""

# Comparar conceptos
echo "DIFERENCIAS EN CONCEPTO:"
echo ""
diff -u "$PROJ1/concepto/result.txt" "$PROJ2/concepto/result.txt" | head -20
