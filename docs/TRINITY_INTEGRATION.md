# Trinity Integration — Backend híbrido fal.ai + Colab self-hosted

**Estado:** feature branch `feature/trinity-hybrid`. Default OFF (100% fal.ai).

## Por qué existe

El pipeline actual depende 100% de fal.ai para todos los pasos de generación
de video (Kling, Runway, WAN). Esto funciona pero:

1. Cuesta dinero por cada clip generado (~$0.10–0.50 según modelo).
2. No tenemos acceso a modelos open-source T2V puros como SkyReels V1
   (entrenado con 10M de clips de cine/TV → mejor en humanos) o
   HunyuanVideo 13B (física end-to-end → mejor en fuego/agua/colisiones).

Trinity agrega un segundo backend que corre en Colab Pro (A100 40/80GB),
gratis mientras haya cómputo disponible, con los 3 modelos open source
top del mercado. El pipeline elige automáticamente fal o Trinity según
la escena y la disponibilidad del notebook.

## Arquitectura

```
                    VideoProvider (interface)
                           │
         ┌─────────────────┴─────────────────┐
         │                                   │
   FalProvider                         TrinityProvider
   (fal.ai API)                        (Colab A100)
   • kling-2.5-pro                     • wan-2.1-14b   (I2V)
   • runway-gen3                       • skyreels-v1   (T2V)
   • wan-2.1                           • hunyuan-13b   (T2V)
   • veo, hailuo                       HTTP + ngrok

                 ChainedProvider
                 (cuando TRINITY_ENABLED=true)
                 intenta Trinity → cae a fal si falla
```

## I2V vs T2V — conceptos

### I2V (Image-to-Video)

Primer paso: generar la imagen ancla con FLUX.1 Pro. Segundo paso: el
modelo I2V anima esa imagen. Ventaja: control visual total porque
el frame 0 ya fijó composición, paleta, iluminación. Ideal para:
paisajes, drone shots, planos cinemáticos lentos, reveals.

**Modelos I2V:** Kling, Runway Gen-3, Wan 2.1 (todos vía fal o trinity).

### T2V (Text-to-Video)

Un solo paso: el modelo genera frames + movimiento juntos a partir
del prompt denso. No requiere imagen ancla. Ventajas: más rápido,
mejor comprensión de matices emocionales y física compleja.

**Modelos T2V:** SkyReels V1, Hunyuan 13B (solo trinity por ahora
en nuestro pipeline; fal también soporta T2V pero no lo usamos
primario porque preferimos consistencia visual vía FLUX).

### Qué modelo recibe cada escena

El director flow emite un `subject_type` por escena y el resolver
hace el routing:

| subject_type | fal (I2V) | trinity | modalidad trinity |
|---|---|---|---|
| human_gesture / human_performance / creature_animal | kling-2.5-pro | skyreels-v1 | **T2V** |
| landscape_static / landscape_dynamic / drone_sweep | runway-gen3-alpha-turbo | wan-2.1-14b | **I2V** |
| subtle_slow_camera / object_reveal | wan-2.1-14b | wan-2.1-14b | **I2V** |
| vfx_heavy | kling-2.5-pro | hunyuan-13b | **T2V** |

El director puede forzar con `preferred_backend: fal|trinity|auto` y
`modality_override: i2v|t2v` cuando una escena lo requiere.

## Puesta en marcha

### 0. Prerrequisitos
- Colab Pro con A100 (40GB o 80GB)
- Cuenta ngrok gratis (o Cloudflare Tunnel si preferís)
- Python 3.10+ local con el venv de Guion_expert

### 1. Subir el notebook a Colab
```bash
# Desde el repo
cp Guion_expert/notebooks/openmontage_trinity_pro.ipynb ~/Downloads/
# Abrí Colab → File → Upload notebook → selecciona ese .ipynb
# Runtime → Change runtime type → GPU → A100
```

### 2. Correr celdas 1 → 5
La celda 5 imprime dos líneas al final:
```
TRINITY_URL=https://abc123.ngrok-free.app
TRINITY_TOKEN=<64 chars hex>
```

### 3. Copiar al `.env` de Guion_expert
```bash
# Editá Guion_expert/.env
TRINITY_ENABLED=true
TRINITY_URL=https://abc123.ngrok-free.app
TRINITY_TOKEN=<tu token>
```

### 4. Correr el pipeline normalmente
```bash
python master_orchestrator.py -i "Una chica descubre una carta vieja"
```

Vas a ver en los logs:
```
provider_booted name=chained:trinity+fal healthy=True
scene_start scene_id=scene-001 backend=trinity model=skyreels-v1 modality=t2v
scene_done  scene_id=scene-001 backend_used=trinity latency_s=183.2
```

### 5. Apagar Trinity (vuelta a 100% fal)
```bash
# En .env:
TRINITY_ENABLED=false
```
Zero cambios de código. El pipeline ignora las vars de Trinity.

## Comportamiento ante fallas

| Escenario | Resultado |
|---|---|
| TRINITY_ENABLED=false | Solo fal.ai. Trinity nunca se toca. |
| TRINITY_ENABLED=true pero Colab apagado | Primer call detecta /health fail → cae a fal. |
| Colab se cae mid-run | La escena en curso falla con `retriable=True` → el próximo intento cae a fal. |
| Modelo T2V pedido pero fal no lo soporta | ProviderError retriable=False → la escena se registra como fallida. Se recomienda dejar `preferred_backend=auto`. |
| Escena crítica marcada `preferred_backend=fal` | Ignora Trinity aunque esté ON. Va directo a fal. |
| `TRINITY_STRICT=true` y Trinity falla | No cae a fal — aborta. Útil para tests. |

## Auditoría de decisiones

Cada escena del `scene_plan.json` tiene en `master_stack`:
- `backend` → efectivo (fal | trinity)
- `modality` → efectivo (i2v | t2v)
- `needs_flux_anchor` → True si se generó imagen ancla con FLUX
- `preferred_backend` → lo que emitió el director (auto | fal | trinity)
- `modality_override` → override explícito del director, si hubo
- `routing_reason` → frase legible explicando la decisión

Ejemplo real:
```json
"master_stack": {
  "chosen_video_model": "skyreels-v1",
  "backend": "trinity",
  "modality": "t2v",
  "needs_flux_anchor": false,
  "preferred_backend": "auto",
  "modality_override": null,
  "routing_reason": "subject_type=human_performance · backend=trinity · model=skyreels-v1 · modality=t2v"
}
```

## Costo estimado por run

| Escenario | Costo aprox por escena | Tiempo |
|---|---|---|
| Solo fal (Kling I2V) | $0.40 | 30–90 s |
| Solo fal (Runway Gen-3 I2V) | $0.60 | 60–120 s |
| Trinity (SkyReels T2V) | $0.00* | 2–5 min (Colab Pro) |
| Trinity (Hunyuan T2V) | $0.00* | 3–7 min (Colab Pro A100) |
| Trinity (Wan 2.1 I2V) | $0.00* | 2–4 min + $0.03 FLUX |

\* costo real = créditos Colab Pro consumidos (~$10/mes).

Para un corto de 10 escenas:
- Solo fal: ~$4–6 USD + 10–20 min wall-clock.
- Trinity primary + fal fallback: ~$0.30 USD (solo FLUX anclas para I2V) + 30–60 min.

## Troubleshooting

**"Trinity no alcanzable" en los logs**
→ El túnel ngrok caducó (ngrok free dura ~2h). Re-corré la celda 5 del
notebook; copiá la nueva `TRINITY_URL` al `.env`.

**"TRINITY_URL no configurada"**
→ No seteaste la var. El pipeline intenta Trinity porque TRINITY_ENABLED=true
pero la URL es empty. Solución: o la seteás, o poné TRINITY_ENABLED=false.

**"Modelo I2V 'skyreels-v1' no tiene endpoint fal.ai registrado"**
→ El director emitió modality_override=i2v para una escena humano, y
Trinity no está disponible, así que cae a fal, que no tiene SkyReels.
Solución: quitá el modality_override o activá Trinity.

**VRAM OOM en el notebook**
→ El modelo no cabe a pesar de `enable_model_cpu_offload()`. Probá
bajar la resolución en `_ratio_to_size` o usá A100 80GB en lugar de 40GB.

## Referencias

- `webapp/schemas/cinematic.py` — schema con `Backend`, `VideoModality`, `VIDEO_MODEL_ROUTING_V2`
- `bridge/openmontage_export.py` — `_resolve_backend()` + `_synthesize_t2v_prompt()`
- `providers/base.py` — interface `VideoProvider`
- `providers/fal_provider.py` — implementación fal.ai
- `providers/trinity_provider.py` — cliente HTTP del Colab
- `providers/factory.py` — `get_provider()` + `ChainedProvider`
- `notebooks/openmontage_trinity_pro.ipynb` — servidor Colab
- `prompts/05_veo_flow.txt` — prompt del director flow con routing guide
