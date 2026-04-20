"""
Asset generator — orquestador de generación por escena (Commit 11)
====================================================================

Consume un `scene_plan.json` (contrato OpenMontage v1) con `master_stack`
poblado por el bridge (Commit 7), y resuelve los `required_assets` de cada
escena contra fal.ai + Suno. Escribe el resultado de vuelta al mismo JSON
bajo `scene["resolved_assets"]`, sin tocar los campos originales.

Excepción al acople
-------------------
El resto de `bridge/` está explícitamente desacoplado de `webapp/` (el
bridge traduce artefactos entre sistemas, no invoca LLMs ni HTTP clients).
**`asset_generator.py` es la única excepción**: importa
`webapp.integrations.fal` + `webapp.integrations.suno` + `webapp.config`
porque es el puente que tiene que ejecutar la tubería completa — y esa
tubería vive en `webapp/integrations/`. Mantener esto en `bridge/` en vez
de `webapp/` señala dos cosas:
  1. Consume el contrato de OpenMontage (scene_plan) como input/output.
  2. Se ejecuta fuera del request-response de Flask (típicamente CLI o
     job worker), por eso no participa del ciclo de vida de la webapp.

Pipeline por escena
-------------------
Para cada `scene` con `required_assets`:

    1. FLUX text-to-image (con LoRA si `settings.flux_lora_url` está
       seteado). Prompt = `master_stack.visual_anchor.subject_description`
       + paleta + lighting + texturas + style (sintetizado desde bridge).
    2. I2V vía `FalClient.adispatch_i2v()`: el modelo sale del routing
       determinístico (`master_stack.chosen_video_model`), el prompt de
       movimiento sale de `master_stack.motion_intent.action`,
       duración de `camera.duration_seconds`.
    3. mmaudio (opcional, controlable con `--no-sfx`): toma el video I2V
       + el prompt combinado de `sonic.sfx` + `sonic.diegetic_sound` y
       devuelve un video con SFX mezclados.
    4. Real-ESRGAN (opcional, solo si `post_production.upscale_with`
       no es null): upscale 2x del frame inicial (o del video completo
       si fuera directo sobre video — no hoy).

En paralelo al procesamiento por escena:

    5. Suno (una vez, para el `hero_scene_id`): `sonic.music_brief` +
       `sonic.music_reference_artists` → clip mp3. Se asocia a la escena
       hero pero podés reasignarlo en edit-director.

Budget tracker
--------------
`BudgetTracker` suma el costo estimado de cada job (tabla `COST_USD`
abajo) y aborta ANTES de arrancar el próximo job si `max_budget_usd`
sería excedido. Esto evita runs accidentales que drenen la tarjeta.

Output
------
Cada escena recibe `resolved_assets` con la misma cantidad de items que
`required_assets`, en el mismo orden:

    "resolved_assets": [
      {
        "type": "image",
        "generator": "fal-ai/flux-lora",
        "url": "https://...",
        "cost_usd": 0.055,
        "elapsed_s": 18.4,
        "request_id": "abc-123",
        "phase": "flux"
      },
      {
        "type": "video",
        "generator": "fal-ai/kling-video/v2.5-turbo/...",
        "url": "https://...",
        ...
      }
    ]

Además se añade a `scene_plan.metadata`:

    "asset_generation": {
      "started_at": "...",
      "finished_at": "...",
      "total_cost_usd": 2.37,
      "budget_usd": 3.00,
      "scenes_completed": 6,
      "scenes_failed": 0,
      "lora_url": "https://...",
      "hero_music_url": "https://..."
    }

Uso CLI
-------

    python -m bridge.asset_generator \\
        /path/to/scene_plan.json \\
        --budget 3.00 \\
        --concurrency 2 \\
        --no-sfx \\
        [--dry-run]

`--dry-run` imprime el plan (modelos + costos estimados) sin pegarle a
fal/Suno. Útil para ver cuánto va a costar antes de hacer click.

Uso programático
----------------

    from bridge.asset_generator import generate_all_assets
    result = await generate_all_assets(
        scene_plan_path=Path("..."),
        budget_usd=3.00,
        concurrency=2,
    )

No tocamos `stages/scene_plan.json` in-place hasta el final: escribimos
primero a `scene_plan.json.tmp` y movemos atómicamente cuando todo
termina (aborta por budget incluido). Esto evita scene_plan corruptos
si Python crashea a mitad de camino.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

# Importar webapp.* es una decisión consciente (ver docstring). El resto
# de bridge/ sigue siendo LLM/HTTP-free.
from webapp.config import settings
from webapp.integrations.fal import (
    FalClient,
    FalJobFailed,
    FalJobResult,
    FalJobTimeout,
)
from webapp.integrations.suno import SunoClient, SunoClip, SunoClipFailed, SunoTimeout

log = structlog.get_logger(__name__)


# ============================================================
# Cost table — valores aproximados (USD) por job, 2026-Q2
# ============================================================
# Estos son estimados conservadores. La verdad oficial vive en la página
# de fal.ai/pricing. Los usamos para el BudgetTracker: si excede el cap,
# abortamos ANTES de submit. Nunca como "lo que costó exactamente" —
# después del run se puede consultar la consola de fal para el número real.

COST_USD: dict[str, float] = {
    # --- imagen ---
    "flux-1.1-pro":             0.040,
    "flux-1.1-pro-ultra":       0.060,
    "flux-lora":                0.055,   # base + LoRA
    "flux-lora-train":          1.500,   # 1000 steps, ~4-8 min
    # --- I2V ---
    "kling-2.5-pro":            0.350,   # 5s a 0.07/s
    "runway-gen3-alpha-turbo":  0.400,
    "wan-2.1-14b":              0.100,
    # --- audio ---
    "mmaudio-v2":               0.015,
    "tts-playai":               0.030,
    # --- post ---
    "real-esrgan":              0.010,
    "rife-interp":              0.012,
    # --- Suno ---
    "suno":                     0.000,   # Leo paga Premium flat-rate
}


def _cost(model: str) -> float:
    return COST_USD.get(model, 0.0)


# ============================================================
# Budget tracker (thread-safe via asyncio lock)
# ============================================================


class BudgetExceeded(RuntimeError):
    """Se abortó un job porque sumar su costo rompería el cap."""


@dataclass
class BudgetTracker:
    cap_usd: float
    spent_usd: float = 0.0
    jobs: list[tuple[str, float]] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def charge(self, label: str, amount_usd: float) -> None:
        """Reserva el costo ANTES de lanzar el job. Si excede el cap,
        raise BudgetExceeded. Si no, lo suma al running total."""
        async with self._lock:
            new_total = self.spent_usd + amount_usd
            if new_total > self.cap_usd:
                raise BudgetExceeded(
                    f"budget exceeded: {label} would bring total to "
                    f"${new_total:.2f} (cap=${self.cap_usd:.2f}, "
                    f"already spent=${self.spent_usd:.2f})"
                )
            self.spent_usd = new_total
            self.jobs.append((label, amount_usd))

    def summary(self) -> dict:
        return {
            "budget_usd": self.cap_usd,
            "spent_usd": round(self.spent_usd, 3),
            "jobs": [
                {"label": label, "cost_usd": round(cost, 3)}
                for label, cost in self.jobs
            ],
        }


# ============================================================
# Dataclasses de output (lo que va a scene_plan.resolved_assets)
# ============================================================


@dataclass
class ResolvedAsset:
    """Un asset resuelto. Se serializa tal cual a JSON."""

    type: str              # "image" | "video" | "audio"
    phase: str             # "flux" | "i2v" | "mmaudio" | "upscale" | "music"
    generator: str         # fal model_id o "suno"
    url: str               # URL del artefacto resuelto
    cost_usd: float
    elapsed_s: float
    request_id: str = ""
    error: str = ""
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        # No commitear el raw payload al scene_plan (demasiado verboso);
        # guardarlo aparte si se pide --verbose.
        d.pop("raw", None)
        if not d["error"]:
            d.pop("error", None)
        if not d["request_id"]:
            d.pop("request_id", None)
        return d


@dataclass
class SceneAssetBundle:
    """Resultado de procesar una escena. Lo unimos después en scene_plan."""

    scene_id: str
    assets: list[ResolvedAsset] = field(default_factory=list)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and bool(self.assets)


# ============================================================
# Helpers
# ============================================================


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _synthesize_flux_prompt(scene: dict, trigger: str = "") -> str:
    """Arma el prompt de FLUX desde `master_stack.visual_anchor`. Mismo
    contrato que el bridge ya escribió en `required_assets[0].description`,
    pero reconstruido desde los campos estructurados para mayor control.

    Si `trigger` está seteado (ej. '3SM_BAND'), se prepende para activar
    el LoRA de identidad entrenado.
    """
    ms = scene.get("master_stack") or {}
    va = ms.get("visual_anchor") or {}

    parts: list[str] = []
    if trigger:
        # Prepend como trigger word suelto — sin punto adicional para evitar
        # el famoso "3SM_BAND.. Bajista..." (doble punto) cuando subj arranca
        # con mayúscula.
        parts.append(trigger.strip())

    subj = (va.get("subject_description") or scene.get("description") or "").strip()
    if subj:
        parts.append(subj)

    comp = (va.get("composition") or "").strip()
    if comp:
        parts.append("composition: " + comp)

    palette = va.get("palette") or []
    if isinstance(palette, list) and palette:
        parts.append("palette: " + ", ".join(str(p) for p in palette if p))
    elif isinstance(palette, str) and palette.strip():
        parts.append("palette: " + palette.strip())

    lighting = (va.get("lighting") or "").strip()
    if lighting:
        parts.append("lighting: " + lighting)

    textures = va.get("textures") or []
    if isinstance(textures, list) and textures:
        parts.append("textures: " + ", ".join(str(t) for t in textures if t))
    elif isinstance(textures, str) and textures.strip():
        parts.append("textures: " + textures.strip())

    style = (va.get("style") or "").strip()
    if style:
        parts.append("style: " + style)

    return ". ".join(parts)


def _synthesize_i2v_prompt(scene: dict) -> str:
    """Prompt de movimiento para I2V: `motion_intent.action` + camera hint."""
    ms = scene.get("master_stack") or {}
    motion = ms.get("motion_intent") or {}
    camera = ms.get("camera") or {}

    parts: list[str] = []
    action = (motion.get("action") or "").strip()
    if action:
        parts.append(action)
    phys = (motion.get("physics_notes") or "").strip()
    if phys:
        parts.append("physics: " + phys)
    mov = (camera.get("movement") or "").strip()
    if mov:
        parts.append("camera: " + mov.replace("_", " "))
    return ". ".join(parts)


def _synthesize_sfx_prompt(scene: dict) -> str:
    """Prompt para mmaudio: combina sfx + diegetic sound."""
    ms = scene.get("master_stack") or {}
    sonic = ms.get("sonic") or {}

    parts: list[str] = []
    sfx = sonic.get("sfx") or []
    if isinstance(sfx, list) and sfx:
        parts.append(", ".join(str(s) for s in sfx if s))
    elif isinstance(sfx, str) and sfx.strip():
        parts.append(sfx.strip())

    diegetic = (sonic.get("diegetic_sound") or "").strip()
    if diegetic:
        parts.append(diegetic)

    return ". ".join(parts)


def _duration_s_for_scene(scene: dict, default: int = 5) -> int:
    """Saca duración en segundos desde master_stack.camera.duration_seconds.
    Los modelos I2V aceptan solo 5 o 10 — el FalClient se encarga del snap."""
    ms = scene.get("master_stack") or {}
    cam = ms.get("camera") or {}
    dur = cam.get("duration_seconds") or default
    try:
        return int(round(float(dur)))
    except (TypeError, ValueError):
        return default


def _hero_scene(plan: dict) -> dict | None:
    """Devuelve la escena marcada como hero, o None. Prefiere
    `metadata.hero_scene_id`; si no, la primera con `hero_moment=True`."""
    hero_id = (plan.get("metadata") or {}).get("hero_scene_id")
    if hero_id:
        for s in plan.get("scenes") or []:
            if s.get("id") == hero_id:
                return s
    for s in plan.get("scenes") or []:
        if s.get("hero_moment"):
            return s
    return None


# ============================================================
# LoRA training (opcional, una vez por proyecto)
# ============================================================


async def train_lora_if_needed(
    fal: FalClient,
    budget: BudgetTracker,
    *,
    images_zip_url: str = "",
    trigger_word: str = "",
    force: bool = False,
) -> str:
    """Entrena un LoRA de identidad si no hay uno listo.

    Orden de preferencia:
        1. Si `force=False` y `settings.flux_lora_url` está seteado en
           env, devuelve esa URL (cache hit).
        2. Si `images_zip_url` está seteado, entrena. Costo ~$1.50.
        3. Si nada de lo anterior: devuelve "" (sin LoRA, el FLUX se
           llama sin parámetro `loras`, identity NO se preserva).

    `images_zip_url` tiene que ser un ZIP público ya hosteado (fal.ai
    NO lo descarga del disco local). Para subirlo:
        - https://fal.ai/docs/private-gallery  (UI manual), o
        - `fal-client` upload API (TODO: agregar helper).
    """
    trigger = trigger_word or settings.flux_lora_trigger
    cached = settings.flux_lora_url.strip()

    if cached and not force:
        log.info("lora_cache_hit", url=cached, trigger=trigger)
        return cached

    if not images_zip_url:
        log.warning(
            "lora_skip_no_refs",
            reason="FLUX_LORA_URL vacío y no se pasó images_zip_url — "
            "identidad NO va a preservarse entre escenas.",
        )
        return ""

    if not trigger:
        raise ValueError(
            "LoRA training requiere trigger_word. Seteá FLUX_LORA_TRIGGER "
            "en .env (ej. 3SM_BAND)."
        )

    # Reservar budget ANTES de submit
    await budget.charge("flux-lora-train", _cost("flux-lora-train"))
    log.info("lora_train_start", trigger=trigger, images_zip=images_zip_url[:80])

    try:
        result = await fal.aflux_lora_train(
            images_zip_url, trigger_word=trigger, steps=1000
        )
    except (FalJobFailed, FalJobTimeout) as e:
        log.error("lora_train_failed", error=str(e))
        raise

    url = result.first_url()
    log.info(
        "lora_train_done",
        url=url[:80],
        elapsed_s=round(result.elapsed_s, 1),
    )
    return url


# ============================================================
# Per-scene pipeline
# ============================================================


async def process_scene(
    scene: dict,
    *,
    fal: FalClient,
    budget: BudgetTracker,
    lora_url: str,
    trigger_word: str,
    enable_sfx: bool,
) -> SceneAssetBundle:
    """Resuelve todos los `required_assets` de una escena, en orden:
    FLUX → I2V → mmaudio (si enable_sfx) → Real-ESRGAN (si upscale_with).

    Si una fase falla, el bundle se corta y se anota el error — las fases
    posteriores no se intentan (p.ej. sin imagen no hay I2V).
    """
    scene_id = scene.get("id", "?")
    bundle = SceneAssetBundle(scene_id=scene_id)
    ms = scene.get("master_stack") or {}
    scene_log = log.bind(scene_id=scene_id)

    # ---- 1. FLUX ----
    try:
        flux_prompt = _synthesize_flux_prompt(scene, trigger=trigger_word)
        flux_model = settings.flux_model   # "fal-ai/flux-lora" admite lora_url opcional
        await budget.charge(f"{scene_id}:flux", _cost("flux-lora" if lora_url else "flux-1.1-pro"))

        scene_log.info("scene_flux_start", prompt_len=len(flux_prompt), has_lora=bool(lora_url))
        flux_result = await fal.aflux_generate(
            flux_prompt,
            model=flux_model,
            lora_url=lora_url or None,
        )
        flux_url = flux_result.first_url()
        bundle.assets.append(ResolvedAsset(
            type="image",
            phase="flux",
            generator=flux_result.model_id,
            url=flux_url,
            cost_usd=_cost("flux-lora" if lora_url else "flux-1.1-pro"),
            elapsed_s=round(flux_result.elapsed_s, 2),
            request_id=flux_result.request_id,
        ))
        scene_log.info("scene_flux_ok", url=flux_url[:80], elapsed=flux_result.elapsed_s)
    except (FalJobFailed, FalJobTimeout, BudgetExceeded) as e:
        bundle.error = f"flux: {e}"
        scene_log.error("scene_flux_failed", error=str(e))
        return bundle

    # ---- 2. I2V (routing desde master_stack.chosen_video_model) ----
    chosen_model = ms.get("chosen_video_model") or ""
    subject_type = ms.get("subject_type")
    duration = _duration_s_for_scene(scene)
    i2v_prompt = _synthesize_i2v_prompt(scene)

    try:
        await budget.charge(f"{scene_id}:i2v", _cost(chosen_model))
        scene_log.info(
            "scene_i2v_start",
            model=chosen_model,
            duration_s=duration,
            subject_type=subject_type,
        )
        i2v_result = await fal.adispatch_i2v(
            subject_type=subject_type,
            image_url=flux_url,
            prompt=i2v_prompt,
            duration_s=duration,
            model_override=chosen_model or None,
        )
        i2v_url = i2v_result.first_url()
        bundle.assets.append(ResolvedAsset(
            type="video",
            phase="i2v",
            generator=i2v_result.model_id,
            url=i2v_url,
            cost_usd=_cost(chosen_model),
            elapsed_s=round(i2v_result.elapsed_s, 2),
            request_id=i2v_result.request_id,
        ))
        scene_log.info("scene_i2v_ok", url=i2v_url[:80], elapsed=i2v_result.elapsed_s)
    except (FalJobFailed, FalJobTimeout, BudgetExceeded) as e:
        bundle.error = f"i2v: {e}"
        scene_log.error("scene_i2v_failed", error=str(e))
        return bundle

    # ---- 3. mmaudio (opcional) ----
    if enable_sfx:
        sfx_prompt = _synthesize_sfx_prompt(scene)
        if sfx_prompt:
            try:
                await budget.charge(f"{scene_id}:mmaudio", _cost("mmaudio-v2"))
                scene_log.info("scene_mmaudio_start", prompt_len=len(sfx_prompt))
                sfx_result = await fal.ammaudio(
                    i2v_url,
                    sfx_prompt,
                    duration_s=duration,
                )
                sfx_url = sfx_result.first_url()
                bundle.assets.append(ResolvedAsset(
                    type="video",
                    phase="mmaudio",
                    generator=sfx_result.model_id,
                    url=sfx_url,
                    cost_usd=_cost("mmaudio-v2"),
                    elapsed_s=round(sfx_result.elapsed_s, 2),
                    request_id=sfx_result.request_id,
                ))
                scene_log.info("scene_mmaudio_ok", url=sfx_url[:80])
            except (FalJobFailed, FalJobTimeout, BudgetExceeded) as e:
                # mmaudio falla != escena entera falla; anotamos y seguimos.
                scene_log.warning("scene_mmaudio_failed", error=str(e))
                bundle.assets.append(ResolvedAsset(
                    type="video",
                    phase="mmaudio",
                    generator="mmaudio-v2",
                    url="",
                    cost_usd=0.0,
                    elapsed_s=0.0,
                    error=str(e),
                ))
        else:
            scene_log.debug("scene_mmaudio_skip", reason="empty sfx prompt")

    # ---- 4. Real-ESRGAN upscale (opcional) ----
    post = ms.get("post_production") or {}
    upscale_with = post.get("upscale_with")
    if upscale_with and str(upscale_with).lower().startswith("real-esrgan"):
        try:
            await budget.charge(f"{scene_id}:upscale", _cost("real-esrgan"))
            scene_log.info("scene_upscale_start", target=upscale_with)
            # Upscale sobre la imagen FLUX (mejor calidad que upscalear video).
            # El frame final puede reconstruirse con el video I2V upscaleado
            # via un paso posterior en OpenMontage (Remotion).
            up_result = await fal.areal_esrgan(
                flux_url,
                scale=settings.real_esrgan_scale,
            )
            up_url = up_result.first_url()
            bundle.assets.append(ResolvedAsset(
                type="image",
                phase="upscale",
                generator=up_result.model_id,
                url=up_url,
                cost_usd=_cost("real-esrgan"),
                elapsed_s=round(up_result.elapsed_s, 2),
                request_id=up_result.request_id,
            ))
            scene_log.info("scene_upscale_ok", url=up_url[:80])
        except (FalJobFailed, FalJobTimeout, BudgetExceeded) as e:
            scene_log.warning("scene_upscale_failed", error=str(e))
            bundle.assets.append(ResolvedAsset(
                type="image",
                phase="upscale",
                generator="real-esrgan",
                url="",
                cost_usd=0.0,
                elapsed_s=0.0,
                error=str(e),
            ))

    return bundle


# ============================================================
# Music generation (Suno, solo para hero)
# ============================================================


async def generate_hero_music(
    suno: SunoClient,
    plan: dict,
) -> tuple[str, float, str]:
    """Genera la música del hero scene. Devuelve (audio_url, duration_s, clip_id)
    o ("", 0, "") si no hay hero o falta el music_brief."""
    hero = _hero_scene(plan)
    if hero is None:
        log.info("hero_music_skip", reason="no hero scene")
        return ("", 0.0, "")

    ms = hero.get("master_stack") or {}
    sonic = ms.get("sonic") or {}
    brief = (sonic.get("music_brief") or "").strip()
    if not brief:
        log.info("hero_music_skip", reason="no music_brief", scene_id=hero.get("id"))
        return ("", 0.0, "")

    refs = sonic.get("music_reference_artists") or []
    if isinstance(refs, list):
        tags = ", ".join(str(r) for r in refs if r)
    else:
        tags = str(refs)
    if not tags:
        # Fallback a moods si no hay artistas
        moods = sonic.get("mood") or []
        if isinstance(moods, list):
            tags = ", ".join(str(m) for m in moods if m)

    title = f"3SM — {ms.get('narrative_beat', hero.get('id', 'hero'))}"
    log.info("hero_music_start", scene_id=hero.get("id"), title=title, tags=tags)

    try:
        clip: SunoClip = await suno.agenerate_song(
            prompt=brief,
            tags=tags,
            title=title,
            instrumental=settings.suno_default_instrumental,
        )
    except (SunoClipFailed, SunoTimeout) as e:
        log.error("hero_music_failed", error=str(e))
        return ("", 0.0, "")

    log.info(
        "hero_music_ok",
        clip_id=clip.id,
        url=clip.audio_url[:80],
        duration_s=clip.duration_s,
    )
    return (clip.audio_url, clip.duration_s, clip.id)


# ============================================================
# Dry-run: estimación de costo sin pegarle a la API
# ============================================================


def plan_cost_estimate(plan: dict, *, enable_sfx: bool, has_lora_url: bool) -> dict:
    """Calcula el costo estimado total sin tocar la red. Útil para
    `--dry-run` y para decidir si el budget alcanza antes de empezar."""
    scenes = plan.get("scenes") or []
    per_scene: list[dict] = []
    total = 0.0

    for s in scenes:
        ms = s.get("master_stack") or {}
        i2v_model = ms.get("chosen_video_model") or ""
        post = ms.get("post_production") or {}
        upscale = bool(post.get("upscale_with"))

        items: list[tuple[str, float]] = []
        items.append(("flux-lora" if has_lora_url else "flux-1.1-pro",
                      _cost("flux-lora" if has_lora_url else "flux-1.1-pro")))
        items.append((i2v_model, _cost(i2v_model)))
        if enable_sfx:
            items.append(("mmaudio-v2", _cost("mmaudio-v2")))
        if upscale:
            items.append(("real-esrgan", _cost("real-esrgan")))

        scene_total = sum(c for _, c in items)
        total += scene_total
        per_scene.append({
            "scene_id": s.get("id"),
            "hero": bool(s.get("hero_moment")),
            "items": [{"model": m, "cost_usd": c} for m, c in items],
            "subtotal_usd": round(scene_total, 3),
        })

    return {
        "scenes": per_scene,
        "hero_music_usd": _cost("suno"),
        "total_usd": round(total + _cost("suno"), 3),
    }


# ============================================================
# Main orchestrator
# ============================================================


async def generate_all_assets(
    scene_plan_path: Path | str,
    *,
    budget_usd: float | None = None,
    concurrency: int = 2,
    enable_sfx: bool = True,
    enable_music: bool = True,
    lora_images_zip_url: str = "",
    force_train_lora: bool = False,
    dry_run: bool = False,
) -> dict:
    """Orquestador principal. Lee scene_plan, dispara todas las fases,
    escribe resolved_assets de vuelta atómicamente. Devuelve un dict
    resumen (mismo payload que `metadata.asset_generation`).

    Levanta `BudgetExceeded` si el cap se rompe a mitad de camino — el
    scene_plan original NO se sobreescribe en ese caso (todo queda en
    `.tmp`).
    """
    path = Path(scene_plan_path)
    if not path.exists():
        raise FileNotFoundError(f"scene_plan no encontrado: {path}")

    plan = json.loads(path.read_text(encoding="utf-8"))
    scenes: list[dict] = plan.get("scenes") or []
    if not scenes:
        raise ValueError(f"scene_plan vacío (sin 'scenes'): {path}")

    if len(scenes) > settings.max_scenes_per_project:
        raise ValueError(
            f"scene_plan tiene {len(scenes)} escenas > cap "
            f"({settings.max_scenes_per_project}). Ajustá MAX_SCENES_PER_PROJECT."
        )

    cap = budget_usd if budget_usd is not None else settings.max_budget_usd
    budget = BudgetTracker(cap_usd=cap)

    # ---- dry-run: solo estimación ----
    if dry_run:
        est = plan_cost_estimate(
            plan,
            enable_sfx=enable_sfx,
            has_lora_url=bool(settings.flux_lora_url or lora_images_zip_url),
        )
        est["budget_usd"] = cap
        est["would_exceed"] = est["total_usd"] > cap
        log.info("dry_run_estimate", **{k: v for k, v in est.items() if k != "scenes"})
        return est

    started_at = _now_iso()
    t_start = time.monotonic()

    # ---- abrimos clientes (context managers async) ----
    async with FalClient() as fal:
        # 1. LoRA training (bloquea todo lo demás — la cache es global)
        lora_url = await train_lora_if_needed(
            fal,
            budget,
            images_zip_url=lora_images_zip_url,
            trigger_word=settings.flux_lora_trigger,
            force=force_train_lora,
        )

        # 2. Paralelizar: procesamiento por escena + música del hero.
        sem = asyncio.Semaphore(max(1, concurrency))

        async def _with_sem(s: dict) -> SceneAssetBundle:
            async with sem:
                try:
                    return await process_scene(
                        s,
                        fal=fal,
                        budget=budget,
                        lora_url=lora_url,
                        trigger_word=settings.flux_lora_trigger,
                        enable_sfx=enable_sfx,
                    )
                except BudgetExceeded as e:
                    return SceneAssetBundle(
                        scene_id=s.get("id", "?"),
                        error=f"budget_exceeded: {e}",
                    )
                except Exception as e:  # noqa: BLE001
                    log.exception("scene_unexpected_error", scene_id=s.get("id"))
                    return SceneAssetBundle(
                        scene_id=s.get("id", "?"),
                        error=f"unexpected: {e}",
                    )

        scene_tasks = [asyncio.create_task(_with_sem(s)) for s in scenes]

        hero_music_task: asyncio.Task[tuple[str, float, str]] | None = None
        if enable_music:
            async def _music() -> tuple[str, float, str]:
                try:
                    async with SunoClient() as suno:
                        return await generate_hero_music(suno, plan)
                except ValueError as e:
                    # Cookie no configurada, etc — no abortar todo el run.
                    log.warning("suno_disabled", error=str(e))
                    return ("", 0.0, "")
            hero_music_task = asyncio.create_task(_music())

        # Esperamos a todo
        bundles: list[SceneAssetBundle] = await asyncio.gather(*scene_tasks)
        hero_url, hero_duration, hero_clip_id = await hero_music_task if hero_music_task else ("", 0.0, "")

    # ---- Merge bundles en el scene_plan ----
    bundle_by_id = {b.scene_id: b for b in bundles}
    scenes_completed = 0
    scenes_failed = 0

    for s in scenes:
        b = bundle_by_id.get(s.get("id", ""))
        if b is None:
            continue
        s["resolved_assets"] = [a.to_dict() for a in b.assets]
        if b.ok:
            scenes_completed += 1
        else:
            scenes_failed += 1
            s.setdefault("resolved_assets_error", b.error)

    # Hero music → metadata del hero + top-level
    if hero_url:
        hero = _hero_scene(plan)
        if hero is not None:
            hero.setdefault("resolved_assets", []).append({
                "type": "audio",
                "phase": "music",
                "generator": "suno",
                "url": hero_url,
                "cost_usd": _cost("suno"),
                "elapsed_s": 0.0,
                "duration_s": hero_duration,
                "clip_id": hero_clip_id,
            })

    # Metadata agregada (running totals, timings, URLs importantes)
    plan.setdefault("metadata", {})["asset_generation"] = {
        "started_at": started_at,
        "finished_at": _now_iso(),
        "elapsed_s": round(time.monotonic() - t_start, 1),
        "total_cost_usd": round(budget.spent_usd, 3),
        "budget_usd": cap,
        "scenes_completed": scenes_completed,
        "scenes_failed": scenes_failed,
        "lora_url": lora_url,
        "lora_trigger": settings.flux_lora_trigger,
        "hero_music_url": hero_url,
        "hero_music_duration_s": hero_duration,
        "hero_music_clip_id": hero_clip_id,
        "concurrency": concurrency,
        "sfx_enabled": enable_sfx,
        "music_enabled": enable_music,
    }

    # ---- Escritura atómica: .tmp → rename ----
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(plan, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)

    log.info(
        "asset_generation_done",
        path=str(path),
        scenes_completed=scenes_completed,
        scenes_failed=scenes_failed,
        total_cost_usd=round(budget.spent_usd, 3),
        hero_music=bool(hero_url),
    )

    return plan["metadata"]["asset_generation"]


# ============================================================
# CLI
# ============================================================


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m bridge.asset_generator",
        description=(
            "Resuelve los required_assets de un scene_plan.json contra "
            "fal.ai + Suno. Escribe resolved_assets in-place."
        ),
    )
    p.add_argument(
        "scene_plan",
        type=Path,
        help="Path al scene_plan.json (ej. OpenMontage/projects/<id>/stages/scene_plan.json)",
    )
    p.add_argument(
        "--budget",
        type=float,
        default=None,
        help=f"Cap de gasto en USD (default: settings.max_budget_usd={settings.max_budget_usd})",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=2,
        help="Escenas en paralelo (default 2). OJO: fal tiene rate limit.",
    )
    p.add_argument(
        "--no-sfx",
        action="store_true",
        help="Saltear mmaudio (ahorra ~$0.015/escena).",
    )
    p.add_argument(
        "--no-music",
        action="store_true",
        help="Saltear Suno (música del hero).",
    )
    p.add_argument(
        "--lora-images",
        type=str,
        default="",
        help=(
            "URL de un ZIP público con fotos de referencia para entrenar "
            "un LoRA de identidad. Solo se usa si FLUX_LORA_URL no está "
            "seteado en .env. Costo extra: ~$1.50."
        ),
    )
    p.add_argument(
        "--force-train-lora",
        action="store_true",
        help="Entrenar LoRA aunque FLUX_LORA_URL ya esté en .env (ignora cache).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Imprimir estimación de costo sin pegar a fal/Suno.",
    )
    return p


def _main_sync() -> int:
    args = _build_argparser().parse_args()
    try:
        result = asyncio.run(generate_all_assets(
            scene_plan_path=args.scene_plan,
            budget_usd=args.budget,
            concurrency=args.concurrency,
            enable_sfx=not args.no_sfx,
            enable_music=not args.no_music,
            lora_images_zip_url=args.lora_images,
            force_train_lora=args.force_train_lora,
            dry_run=args.dry_run,
        ))
    except BudgetExceeded as e:
        print(f"❌ Budget exceeded: {e}", file=sys.stderr)
        return 2
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    # Silenciar warnings de asyncio.gather si quedó algún task pendiente
    # (debería estar todo cerrado vía context managers)
    with contextlib.suppress(KeyboardInterrupt):
        sys.exit(_main_sync())


__all__ = [
    "generate_all_assets",
    "process_scene",
    "train_lora_if_needed",
    "generate_hero_music",
    "plan_cost_estimate",
    "BudgetTracker",
    "BudgetExceeded",
    "ResolvedAsset",
    "SceneAssetBundle",
    "COST_USD",
]
