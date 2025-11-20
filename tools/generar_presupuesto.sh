#!/bin/bash
source scripts/lib.sh

[ -z "$1" ] && echo "Uso: ./tools/generar_presupuesto.sh [analysis_dir]" && exit 1

ANALYSIS="$1"

log_section "GENERADOR DE PRESUPUESTO"

python3 << 'PYEOF'
import sys, json

analysis_dir = sys.argv[1]

with open(f'{analysis_dir}/stats.json', 'r') as f:
    stats = json.load(f)

pages = stats['estimated_pages']
scenes = stats['total_scenes']
characters = stats['total_characters']

COST_PER_PAGE = 1000
total = pages * COST_PER_PAGE

budget = f"""# 💰 PRESUPUESTO ESTIMADO

**Presupuesto Total:** ${total:,}

## DESGLOSE

- **Páginas:** {pages}
- **Costo por página:** ${COST_PER_PAGE:,}
- **Pre-producción:** ${int(total * 0.10):,} (10%)
- **Producción:** ${int(total * 0.70):,} (70%)
- **Post-producción:** ${int(total * 0.15):,} (15%)
- **Contingencia:** ${int(total * 0.05):,} (5%)

---

**NOTA:** Este es un cálculo aproximado basado en promedios de la industria.
Los costos reales varían según ubicación, talento, y escala de producción.
"""

with open(f'{analysis_dir}/BUDGET_ESTIMATE.md', 'w') as f:
    f.write(budget)

print(f"✓ Presupuesto estimado: ${total:,}")
PYEOF "$ANALYSIS"

log_success "Presupuesto generado"
