#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $1"; }
log_success() { echo -e "${GREEN}✓${NC} $1"; }
log_error() { echo -e "${RED}✗${NC} $1"; }
log_info() { echo -e "${YELLOW}→${NC} $1"; }
log_section() { echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n$1\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"; }

clean_ansi() {
    cat "$1" | tr -cd '\11\12\15\40-\176' | sed '/^$/d' > "${1}.clean"
    mv "${1}.clean" "$1"
}

ollama_run_robust() {
    local modelo=$1
    local prompt=$2
    local input=$3
    local output=$4
    local timeout_secs=${5:-300} # Default 5 minutes
    local max_intentos=3
    
    for intento in $(seq 1 $max_intentos); do
        log_info "Intento $intento/$max_intentos ($modelo)..."
        
        # Construct full input
        FULL_INPUT="$prompt

INPUT:
$input"
        
        # Run with timeout if available (gtimeout on mac if installed, else timeout, else python fallback)
        if command -v gtimeout &> /dev/null; then
            echo "$FULL_INPUT" | gtimeout "$timeout_secs" ollama run "$modelo" 2>&1 > "$output.tmp"
        elif command -v timeout &> /dev/null; then
            echo "$FULL_INPUT" | timeout "$timeout_secs" ollama run "$modelo" 2>&1 > "$output.tmp"
        else
            # Fallback using perl for timeout on macOS
            echo "$FULL_INPUT" | perl -e 'alarm shift; exec @ARGV' "$timeout_secs" ollama run "$modelo" 2>&1 > "$output.tmp"
        fi
        
        EXIT_CODE=$?
        
        if [ $EXIT_CODE -eq 0 ]; then
            clean_ansi "$output.tmp"
            if [ -s "$output.tmp" ] && [ $(wc -l < "$output.tmp") -gt 1 ]; then
                mv "$output.tmp" "$output"
                return 0
            else
                log_error "Salida vacía o inválida"
            fi
        elif [ $EXIT_CODE -eq 124 ]; then
            log_error "Timeout ($timeout_secs s) excedido"
        else
            log_error "Error en ejecución (Exit code: $EXIT_CODE)"
        fi
        
        rm -f "$output.tmp"
        sleep 2
    done
    return 1
}

num_escenas() {
    case $1 in
        VIDEOCLIP) echo "8" ;;
        CORTO) echo "20" ;;
        MEDIO) echo "35" ;;
        LARGO) echo "60" ;;
        *) echo "20" ;;
    esac
}

detectar_sd() {
    for puerto in 7860 8188 7861; do
        if curl -s -m 3 -f "http://127.0.0.1:$puerto/sdapi/v1/sd-models" > /dev/null 2>&1; then
            echo "http://127.0.0.1:$puerto"
            return 0
        fi
    done
    return 1
}

# Progress indicator
show_progress() {
    local current=$1
    local total=$2
    local step_name=$3
    
    local percent=$((current * 100 / total))
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 PROGRESO: $current/$total ($percent%) - $step_name"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
}

# Heartbeat - enviar señal de vida cada 30 segundos
send_heartbeat() {
    local message=$1
    echo "💓 [$(date +%H:%M:%S)] $message"
}
