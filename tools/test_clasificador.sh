#!/bin/bash
source scripts/lib.sh

log_section "TEST DEL CLASIFICADOR"

# Test cases
declare -a TESTS=(
    "un short para youtube sobre cocina:YOUTUBE_SHORT"
    "reel de instagram aesthetic:REEL_INSTAGRAM"
    "video de tiktok viral:TIKTOK"
    "tutorial rápido de 30 segundos:YOUTUBE_SHORT"
    "historia de una banda en un bar:CORTO"
    "película sobre robots:LARGO"
    "videoclip musical de rock:VIDEOCLIP"
    "algo vertical sobre maquillaje:YOUTUBE_SHORT"
    "contenido móvil de 60 segundos:YOUTUBE_SHORT"
)

PASSED=0
FAILED=0

for test in "${TESTS[@]}"; do
    IFS=':' read -r INPUT EXPECTED <<< "$test"
    
    echo ""
    log_info "Test: $INPUT"
    echo "Esperado: $EXPECTED"
    
    RESULT=$(./scripts/pre_clasificar.sh "$INPUT")
    
    if [ "$RESULT" == "UNKNOWN" ]; then
        echo "→ Pre-clasificador no detectó, probando con IA..."
        # Aquí normalmente llamaríamos a Ollama
        echo "→ SKIP (requiere Ollama)"
        continue
    fi
    
    if [ "$RESULT" == "$EXPECTED" ]; then
        log_success "✓ PASS: $RESULT"
        PASSED=$((PASSED + 1))
    else
        log_error "✗ FAIL: obtuvo $RESULT, esperaba $EXPECTED"
        FAILED=$((FAILED + 1))
    fi
done

echo ""
log_section "RESULTADOS"
echo "Pasados: $PASSED"
echo "Fallados: $FAILED"
echo "Total: $((PASSED + FAILED))"
