#!/bin/bash
set -e
cd "$(dirname "$(dirname "$0")")"
source scripts/lib.sh
source config/sd.conf

[ -z "$1" ] && echo "Uso: ./scripts/storyboard.sh [output_dir]" && exit 1

OUT="$1"

log_section "STORYBOARD CON SD"

SD_API=$(detectar_sd)
if [ $? -ne 0 ]; then
    log_error "SD no detectado"
    echo "Inicia: cd ~/stable-diffusion-webui && ./webui.sh --api --listen"
    exit 1
fi

log_success "SD: $SD_API"
mkdir -p "$OUT/storyboard"

NUM=$(ls "$OUT"/prompts_sd/prompt_*.txt 2>/dev/null | wc -l)
log_info "Generando $NUM imágenes..."
echo ""

c=0
for pfile in "$OUT"/prompts_sd/prompt_*.txt; do
    [ ! -f "$pfile" ] && continue
    c=$((c+1))
    num=$(basename "$pfile" .txt | sed 's/prompt_//')
    
    printf "\r  [%d/%d] Frame %s" $c $NUM $num
    
    prompt=$(cat "$pfile" | tr -d '\n\r')
    prompt_json=$(echo "$prompt" | sed 's/"/\\"/g')
    negative_json=$(echo "$SD_NEGATIVE" | sed 's/"/\\"/g')
    
    curl -s -X POST "$SD_API/sdapi/v1/txt2img" \
        -H "Content-Type: application/json" \
        -d "{\"prompt\":\"$prompt_json\",\"negative_prompt\":\"$negative_json\",\"width\":$SD_WIDTH,\"height\":$SD_HEIGHT,\"steps\":$SD_STEPS,\"cfg_scale\":$SD_CFG,\"sampler_name\":\"$SD_SAMPLER\"}" | \
    python3 -c "
import sys, json, base64
try:
    data = json.load(sys.stdin)
    if 'images' in data and len(data['images']) > 0:
        with open('$OUT/storyboard/frame_${num}.png', 'wb') as f:
            f.write(base64.b64decode(data['images'][0]))
except: pass
" 2>/dev/null
    
    sleep 0.3
done

echo ""
log_success "$c imágenes generadas"

# HTML
cat > "$OUT/storyboard.html" << 'HTML'
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Storyboard</title>
<style>
body{background:#0a0a0a;color:#e0e0e0;font-family:sans-serif;padding:40px}
h1{color:#00ff88;text-align:center;font-size:3em}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(450px,1fr));gap:30px;max-width:1800px;margin:40px auto}
.frame{background:#1a1a1a;border:2px solid #333;border-radius:12px;padding:20px;transition:0.3s}
.frame:hover{border-color:#00ff88;transform:translateY(-5px)}
img{width:100%;border-radius:8px;cursor:pointer}
.num{color:#00ff88;font-size:1.5em;margin-bottom:15px;font-weight:bold}
.prompt{margin-top:15px;padding:12px;background:#000;border-left:3px solid #00ff88;font-size:0.85em;color:#888}
</style></head><body>
<h1>🎬 STORYBOARD</h1>
<div class="grid">
HTML

for img in "$OUT"/storyboard/frame_*.png; do
    [ ! -f "$img" ] && continue
    num=$(basename "$img" .png | sed 's/frame_//')
    prompt=$(cat "$OUT/prompts_sd/prompt_${num}.txt" 2>/dev/null || echo "")
    
    cat >> "$OUT/storyboard.html" << FRAME
<div class="frame">
    <div class="num">Frame $num</div>
    <img src="storyboard/$(basename $img)">
    <div class="prompt">$prompt</div>
</div>
FRAME
done

echo "</div></body></html>" >> "$OUT/storyboard.html"

log_section "✓ STORYBOARD COMPLETADO"
log_success "HTML: $OUT/storyboard.html"
