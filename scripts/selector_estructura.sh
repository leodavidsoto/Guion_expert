#!/bin/bash
source scripts/lib.sh

log_section "SELECTOR DE ESTRUCTURA NARRATIVA"

echo "Estructuras disponibles:"
echo ""
echo "1. SAVE THE CAT (15 Beats) - Comercial, fórmula probada"
echo "2. HERO'S JOURNEY (12 Etapas) - Épica, mitológica"
echo "3. STORY CIRCLE (8 Pasos) - TV, episódica, Dan Harmon"
echo "4. THREE ACT (Syd Field) - Clásica Hollywood, universal"
echo "5. FIVE ACT (Shakespeare) - Teatral, tragedia/comedia"
echo "6. IN MEDIA RES - No-lineal, misterio"
echo ""
read -p "Selecciona estructura [1-6]: " num

case $num in
    1) ESTRUCTURA="estructuras/save_the_cat.txt" ;;
    2) ESTRUCTURA="estructuras/heros_journey.txt" ;;
    3) ESTRUCTURA="estructuras/story_circle.txt" ;;
    4) ESTRUCTURA="estructuras/three_act_field.txt" ;;
    5) ESTRUCTURA="estructuras/five_act.txt" ;;
    6) ESTRUCTURA="estructuras/in_media_res.txt" ;;
    *) log_error "Opción inválida" && exit 1 ;;
esac

log_success "Estructura seleccionada: $(basename $ESTRUCTURA .txt)"
echo ""

cat "$ESTRUCTURA" | head -50
echo ""
echo "───────────────────────────────────────────────────"
echo ""
read -p "Ver estructura completa? [s/N]: " ver

if [[ "$ver" =~ ^[sS]$ ]]; then
    cat "$ESTRUCTURA" | less
fi

echo ""
read -p "Usar esta estructura para tu proyecto? [s/N]: " usar

if [[ "$usar" =~ ^[sS]$ ]]; then
    read -p "Ingresa tu idea: " IDEA
    
    # Modificar prompt del arquitecto temporalmente
    cat "$ESTRUCTURA" > /tmp/estructura_temp.txt
    
    # Ejecutar pipeline con estructura seleccionada
    export ESTRUCTURA_CUSTOM="/tmp/estructura_temp.txt"
    ./ejecutar.sh "$IDEA"
fi
