"""
fal.ai integration — FLUX, Kling, Runway, WAN, Real-ESRGAN, mmaudio, TTS.
===========================================================================

Un solo cliente (`FalClient`) que consume la **queue API** de fal.ai. Todos los
modelos generativos (imagen, video, audio) se exponen por el mismo endpoint
pattern:

    1. POST https://queue.fal.run/{model_id}         → submit (returns request_id)
    2. GET  https://queue.fal.run/{model_id}/requests/{request_id}/status
    3. GET  https://queue.fal.run/{model_id}/requests/{request_id}            → result

El `FalClient` encapsula el poll-loop: vos llamás `flux_generate(prompt=...)`
y te devolvés el URL de la imagen, sin ver el request_id nunca.

Autenticación
-------------
Header: `Authorization: Key <key_id>:<key_secret>`. La key sale de
`settings.fal_api_key` (pydantic SecretStr — no se loggea).

Routing I2V
-----------
`VIDEO_MODEL_ROUTING` (de `webapp.schemas.cinematic`) mapea `subject_type` →
modelo. Usá `dispatch_i2v(subject_type=...)` para el routing automático, o
los helpers específicos (`kling_i2v`, `runway_i2v`, `wan_i2v`) si ya sabés
cuál querés.

Uso típico desde asset_generator (Commit 11):

    async with FalClient() as fal:
        # Una sola vez — entrená el LoRA de 3SM.
        lora = await fal.aflux_lora_train(
            image_urls=[...],
            trigger_word=settings.flux_lora_trigger,
            steps=1000,
        )

        # Por escena: FLUX con LoRA → I2V elegido por routing.
        image = await fal.aflux_generate(
            prompt=f"{settings.flux_lora_trigger}. {master_stack.flux_prompt}",
            lora_url=lora["safetensors_url"],
        )
        video = await fal.adispatch_i2v(
            subject_type=master_stack.subject_type,
            image_url=image["url"],
            prompt=master_stack.motion_intent.action,
            duration_s=master_stack.camera.duration_seconds,
        )

Todos los métodos levantan `HTTPClientError` / `RetryableError` si algo sale
mal (ver `base.py`). No hay fallbacks silenciosos.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import structlog

from webapp.config import settings
from webapp.integrations.base import (
    BaseHTTPClient,
    HTTPClientError,
    RetryableError,
)

# Importamos el routing canónico del schema. Esto deja al bridge y al
# integration alineados — una sola tabla de verdad.
from webapp.schemas.cinematic import VIDEO_MODEL_ROUTING, choose_video_model

log = structlog.get_logger(__name__)


# ============================================================
# Model registry — IDs de fal.ai por función
# ============================================================

# IDs oficiales de fal.ai. Cuando fal saca versiones nuevas, actualizar acá.
# NO inventar IDs — verificar en https://fal.ai/models.

FAL_MODEL_IDS: dict[str, str] = {
    # ── Imagen ───────────────────────────────────────────────────────
    "flux-1.1-pro":          "fal-ai/flux-pro/v1.1",
    "flux-1.1-pro-ultra":    "fal-ai/flux-pro/v1.1-ultra",
    "flux-lora":             "fal-ai/flux-lora",
    "flux-lora-train":       "fal-ai/flux-lora-fast-training",
    # ── Imagen → Video ──────────────────────────────────────────────
    "kling-2.5-pro":         "fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
    "runway-gen3-alpha-turbo": "fal-ai/runway-gen3/turbo/image-to-video",
    "wan-2.1-14b":           "fal-ai/wan-pro/v2.1-14b/image-to-video",
    # ── Audio ───────────────────────────────────────────────────────
    "mmaudio-v2":            "fal-ai/mmaudio-v2",
    "tts-playai":            "fal-ai/playai/tts/v3",
    # ── Upscale / interpolation ─────────────────────────────────────
    "real-esrgan":           "fal-ai/real-esrgan",
    "rife-interp":           "fal-ai/rife-interpolation",
}


# ============================================================
# Excepciones específicas
# ============================================================


class FalJobFailed(HTTPClientError):
    """Un job de fal terminó con status=FAILED o similar."""


class FalJobTimeout(RetryableError):
    """Un job de fal no completó dentro del tope de espera."""


# ============================================================
# Status / result dataclasses
# ============================================================


@dataclass
class FalJobResult:
    """Resultado exitoso de un job. Los distintos modelos tienen schemas
    distintos, así que exponemos el payload completo más un helper para
    extraer la URL principal."""

    request_id: str
    model_id: str
    payload: dict
    elapsed_s: float

    def first_url(self) -> str:
        """Intenta extraer la URL principal del output. Cubre los patterns
        más comunes de fal (flux, kling, runway, mmaudio, esrgan)."""
        p = self.payload
        # FLUX: {"images": [{"url": "..."}]}
        if "images" in p and p["images"]:
            first = p["images"][0]
            if isinstance(first, dict) and "url" in first:
                return first["url"]
        # Kling/Runway/WAN: {"video": {"url": "..."}} o {"url": "..."}
        if "video" in p and isinstance(p["video"], dict) and "url" in p["video"]:
            return p["video"]["url"]
        # mmaudio: {"video": {"url": "..."}}
        if "audio" in p and isinstance(p["audio"], dict) and "url" in p["audio"]:
            return p["audio"]["url"]
        # Real-ESRGAN / TTS: {"image": {"url": "..."}} o {"audio": {...}}
        if "image" in p and isinstance(p["image"], dict) and "url" in p["image"]:
            return p["image"]["url"]
        # LoRA training: {"diffusers_lora_file": {"url": "..."}}
        if "diffusers_lora_file" in p and "url" in p["diffusers_lora_file"]:
            return p["diffusers_lora_file"]["url"]
        # Último fallback: top-level url
        if "url" in p:
            return p["url"]
        raise FalJobFailed(
            f"fal {self.model_id}: output sin URL reconocible. "
            f"Keys: {list(p.keys())}"
        )


# ============================================================
# Cliente
# ============================================================


class FalClient(BaseHTTPClient):
    """Cliente único para todos los modelos de fal.ai (queue-based)."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        poll_interval_s: float | None = None,
        poll_max_wait_s: float | None = None,
    ) -> None:
        key = api_key or settings.fal_api_key.get_secret_value()
        if not key or "REEMPLAZAR" in key.upper():
            raise ValueError(
                "FAL_API_KEY no configurada. Setealá en .env o pasala "
                "explícita al constructor."
            )
        self._api_key = key
        self.poll_interval_s = poll_interval_s or settings.fal_poll_interval_s
        self.poll_max_wait_s = poll_max_wait_s or settings.fal_poll_max_wait_s
        # request_id -> (status_path, result_path). Algunos modelos (Kling)
        # responden con rutas de queue distintas al model_id submitteado.
        self._request_paths: dict[str, tuple[str, str]] = {}

        super().__init__(
            base_url=base_url or settings.fal_base_url,
            # fal puede tardar mucho para responder status 200 de result,
            # pero el submit es rápido. El poll-loop maneja el long-running.
            timeout_read=60.0,
        )

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Key {self._api_key}"}

    def _service_name(self) -> str:
        return "fal"

    # ----------------------------------------------------------
    # Queue primitives: submit + poll + fetch result
    # ----------------------------------------------------------

    def _resolve_model_id(self, model: str) -> str:
        """Resuelve alias interno (ej. 'kling-2.5-pro') al ID oficial de fal.
        Si ya es un ID completo (contiene '/'), se devuelve tal cual."""
        if "/" in model:
            return model
        fid = FAL_MODEL_IDS.get(model)
        if fid is None:
            raise ValueError(
                f"Modelo fal desconocido: {model!r}. "
                f"Alternativas: {sorted(FAL_MODEL_IDS.keys())}"
            )
        return fid

    def submit(self, model: str, payload: dict) -> str:
        """Submit a queue. Devuelve el request_id."""
        model_id = self._resolve_model_id(model)
        log.info("fal_submit", model=model_id, payload_keys=list(payload.keys()))
        resp = self.post(f"/{model_id}", json=payload)
        request_id = resp.get("request_id")
        if not request_id:
            raise HTTPClientError(
                f"fal {model_id}: submit no devolvió request_id. Body: {resp}"
            )
        self._register_request_paths(model_id, request_id, resp)
        return request_id

    async def asubmit(self, model: str, payload: dict) -> str:
        model_id = self._resolve_model_id(model)
        log.info("fal_submit", model=model_id, payload_keys=list(payload.keys()))
        resp = await self.apost(f"/{model_id}", json=payload)
        request_id = resp.get("request_id")
        if not request_id:
            raise HTTPClientError(
                f"fal {model_id}: submit no devolvió request_id. Body: {resp}"
            )
        self._register_request_paths(model_id, request_id, resp)
        return request_id

    def _status_path(self, model_id: str, request_id: str) -> str:
        return f"/{model_id}/requests/{request_id}/status"

    def _result_path(self, model_id: str, request_id: str) -> str:
        return f"/{model_id}/requests/{request_id}"

    def _path_from_url(self, value: str | None, *, fallback: str) -> str:
        """Normaliza una URL absoluta de queue a path relativo."""
        if not value:
            return fallback
        try:
            parsed = urlsplit(value)
            path = parsed.path or ""
            if not path.startswith("/"):
                return fallback
            if parsed.query:
                path = f"{path}?{parsed.query}"
            return path
        except Exception:  # noqa: BLE001
            return fallback

    def _register_request_paths(self, model_id: str, request_id: str, resp: dict) -> None:
        status_default = self._status_path(model_id, request_id)
        result_default = self._result_path(model_id, request_id)
        status_path = self._path_from_url(resp.get("status_url"), fallback=status_default)
        result_path = self._path_from_url(resp.get("response_url"), fallback=result_default)
        self._request_paths[request_id] = (status_path, result_path)

    def poll_until_complete(
        self,
        model: str,
        request_id: str,
        *,
        poll_interval_s: float | None = None,
        max_wait_s: float | None = None,
    ) -> FalJobResult:
        """Poll bloqueante hasta que el job termine (o timeout). Devuelve el result."""
        model_id = self._resolve_model_id(model)
        interval = poll_interval_s or self.poll_interval_s
        cap = max_wait_s or self.poll_max_wait_s

        t0 = time.monotonic()
        status_path, result_path = self._request_paths.get(
            request_id,
            (self._status_path(model_id, request_id), self._result_path(model_id, request_id)),
        )
        use_logs = True
        last_status = None

        while True:
            poll_path = (
                f"{status_path}{'&' if '?' in status_path else '?'}logs=1"
                if use_logs
                else status_path
            )
            try:
                status_resp = self.get(poll_path)
            except HTTPClientError as e:
                # Algunos modelos de fal (ej. ciertas rutas I2V) no soportan
                # `?logs=1` y responden 405/404. Reintentamos sin logs.
                if use_logs and e.status_code in {404, 405}:
                    use_logs = False
                    log.warning(
                        "fal_status_logs_unsupported",
                        model=model_id,
                        request_id=request_id,
                        status_code=e.status_code,
                    )
                    continue
                raise
            status = status_resp.get("status", "UNKNOWN")
            if status != last_status:
                log.info(
                    "fal_status",
                    model=model_id,
                    request_id=request_id,
                    status=status,
                )
                last_status = status

            if status == "COMPLETED":
                break
            if status in ("FAILED", "ERROR", "CANCELLED"):
                raise FalJobFailed(
                    f"fal {model_id} job {request_id} {status}. "
                    f"Logs: {status_resp.get('logs', [])}"
                )

            elapsed = time.monotonic() - t0
            if elapsed > cap:
                raise FalJobTimeout(
                    f"fal {model_id} job {request_id} timeout después "
                    f"de {elapsed:.0f}s (cap={cap}s, último status={status})"
                )
            time.sleep(interval)

        # Fetch result
        payload = self.get(result_path)
        elapsed = time.monotonic() - t0
        self._request_paths.pop(request_id, None)
        return FalJobResult(
            request_id=request_id,
            model_id=model_id,
            payload=payload,
            elapsed_s=elapsed,
        )

    async def apoll_until_complete(
        self,
        model: str,
        request_id: str,
        *,
        poll_interval_s: float | None = None,
        max_wait_s: float | None = None,
    ) -> FalJobResult:
        """Variante async del poll-loop — usada por asset_generator para
        paralelizar N escenas con `asyncio.gather`."""
        model_id = self._resolve_model_id(model)
        interval = poll_interval_s or self.poll_interval_s
        cap = max_wait_s or self.poll_max_wait_s

        t0 = time.monotonic()
        status_path, result_path = self._request_paths.get(
            request_id,
            (self._status_path(model_id, request_id), self._result_path(model_id, request_id)),
        )
        use_logs = True
        last_status = None

        while True:
            poll_path = (
                f"{status_path}{'&' if '?' in status_path else '?'}logs=1"
                if use_logs
                else status_path
            )
            try:
                status_resp = await self.aget(poll_path)
            except HTTPClientError as e:
                # Algunos modelos de fal (ej. ciertas rutas I2V) no soportan
                # `?logs=1` y responden 405/404. Reintentamos sin logs.
                if use_logs and e.status_code in {404, 405}:
                    use_logs = False
                    log.warning(
                        "fal_status_logs_unsupported",
                        model=model_id,
                        request_id=request_id,
                        status_code=e.status_code,
                    )
                    continue
                raise
            status = status_resp.get("status", "UNKNOWN")
            if status != last_status:
                log.info(
                    "fal_status",
                    model=model_id,
                    request_id=request_id,
                    status=status,
                )
                last_status = status

            if status == "COMPLETED":
                break
            if status in ("FAILED", "ERROR", "CANCELLED"):
                raise FalJobFailed(
                    f"fal {model_id} job {request_id} {status}. "
                    f"Logs: {status_resp.get('logs', [])}"
                )

            elapsed = time.monotonic() - t0
            if elapsed > cap:
                raise FalJobTimeout(
                    f"fal {model_id} job {request_id} timeout después "
                    f"de {elapsed:.0f}s (cap={cap}s, último status={status})"
                )
            await asyncio.sleep(interval)

        payload = await self.aget(result_path)
        elapsed = time.monotonic() - t0
        self._request_paths.pop(request_id, None)
        return FalJobResult(
            request_id=request_id,
            model_id=model_id,
            payload=payload,
            elapsed_s=elapsed,
        )

    def run(self, model: str, payload: dict, **poll_kwargs: Any) -> FalJobResult:
        """Submit + poll en un solo call. La API conveniente de alto nivel."""
        request_id = self.submit(model, payload)
        return self.poll_until_complete(model, request_id, **poll_kwargs)

    async def arun(self, model: str, payload: dict, **poll_kwargs: Any) -> FalJobResult:
        request_id = await self.asubmit(model, payload)
        return await self.apoll_until_complete(model, request_id, **poll_kwargs)

    # ==========================================================
    # FLUX — text-to-image
    # ==========================================================

    def _flux_payload(
        self,
        prompt: str,
        *,
        image_size: str | None = None,
        num_inference_steps: int | None = None,
        guidance_scale: float | None = None,
        seed: int | None = None,
        lora_url: str | None = None,
    ) -> dict:
        payload: dict = {
            "prompt": prompt,
            "image_size": image_size or settings.flux_image_size,
            "num_inference_steps": num_inference_steps or settings.flux_steps,
            "guidance_scale": guidance_scale if guidance_scale is not None else settings.flux_guidance,
            "num_images": 1,
            "enable_safety_checker": True,
            "output_format": "png",
        }
        if seed is not None:
            payload["seed"] = seed
        # LoRA path: URL del .safetensors + scale=1.0 default.
        lora_target = lora_url or settings.flux_lora_url
        if lora_target:
            payload["loras"] = [{"path": lora_target, "scale": 1.0}]
        return payload

    def flux_generate(self, prompt: str, **kwargs: Any) -> FalJobResult:
        """FLUX text-to-image (con LoRA opcional si `settings.flux_lora_url`
        o `lora_url=` vienen seteados). Usa el alias `flux-lora` para
        aceptar LoRAs; pasá `model='flux-1.1-pro'` si querés base-only."""
        model = kwargs.pop("model", settings.flux_model)
        payload = self._flux_payload(prompt, **kwargs)
        return self.run(model, payload)

    async def aflux_generate(self, prompt: str, **kwargs: Any) -> FalJobResult:
        model = kwargs.pop("model", settings.flux_model)
        payload = self._flux_payload(prompt, **kwargs)
        return await self.arun(model, payload)

    # ==========================================================
    # FLUX LoRA training — entrenar LoRA de identidad
    # ==========================================================

    def _flux_lora_train_payload(
        self,
        images_data_url: str,
        *,
        trigger_word: str,
        steps: int = 1000,
        learning_rate: float | None = None,
    ) -> dict:
        payload: dict = {
            "images_data_url": images_data_url,
            "trigger_word": trigger_word,
            "steps": steps,
            "is_style": False,    # es identidad (subject), no estilo.
            "create_masks": True,
        }
        if learning_rate is not None:
            payload["learning_rate"] = learning_rate
        return payload

    def flux_lora_train(
        self,
        images_data_url: str,
        *,
        trigger_word: str,
        steps: int = 1000,
        **kwargs: Any,
    ) -> FalJobResult:
        """Entrena un LoRA subject. `images_data_url` es un ZIP público con
        las imágenes (5-10 fotos es suficiente). Devuelve URL del
        safetensors en `result.payload["diffusers_lora_file"]["url"]`.

        Costo aprox: ~$1-2 en fal.ai. Duración: 4-8 minutos."""
        payload = self._flux_lora_train_payload(
            images_data_url, trigger_word=trigger_word, steps=steps, **kwargs
        )
        # Training puede tardar — subimos el cap del poll a 20min.
        return self.run(
            "flux-lora-train",
            payload,
            max_wait_s=max(1200.0, self.poll_max_wait_s),
        )

    async def aflux_lora_train(
        self,
        images_data_url: str,
        *,
        trigger_word: str,
        steps: int = 1000,
        **kwargs: Any,
    ) -> FalJobResult:
        payload = self._flux_lora_train_payload(
            images_data_url, trigger_word=trigger_word, steps=steps, **kwargs
        )
        return await self.arun(
            "flux-lora-train",
            payload,
            max_wait_s=max(1200.0, self.poll_max_wait_s),
        )

    # ==========================================================
    # I2V — Image to Video (Kling / Runway / WAN)
    # ==========================================================

    def _kling_payload(
        self,
        image_url: str,
        prompt: str,
        *,
        duration_s: int = 5,
        negative_prompt: str | None = None,
        cfg_scale: float = 0.5,
    ) -> dict:
        # Kling admite duration = 5 o 10 (segundos). Snap al más cercano.
        dur = 10 if duration_s > 7 else 5
        p: dict = {
            "prompt": prompt,
            "image_url": image_url,
            "duration": str(dur),
            "aspect_ratio": "9:16",      # vertical para reels
            "cfg_scale": cfg_scale,
        }
        if negative_prompt:
            p["negative_prompt"] = negative_prompt
        return p

    def _runway_payload(
        self,
        image_url: str,
        prompt: str,
        *,
        duration_s: int = 5,
    ) -> dict:
        # Runway Gen-3: duration solo 5s o 10s. Aspect ratio "9:16".
        dur = 10 if duration_s > 7 else 5
        return {
            "prompt": prompt,
            "image_url": image_url,
            "duration": str(dur),
            "ratio": "9:16",
        }

    def _wan_payload(
        self,
        image_url: str,
        prompt: str,
        *,
        duration_s: int = 5,
    ) -> dict:
        # WAN 2.1 14B: duration continuous (1-8s), aspect por resolución input.
        return {
            "prompt": prompt,
            "image_url": image_url,
            "num_frames": max(16, min(int(duration_s * 16), 128)),  # ~16fps
        }

    def kling_i2v(
        self,
        image_url: str,
        prompt: str,
        *,
        duration_s: int = 5,
        **kwargs: Any,
    ) -> FalJobResult:
        payload = self._kling_payload(image_url, prompt, duration_s=duration_s, **kwargs)
        return self.run("kling-2.5-pro", payload)

    async def akling_i2v(self, image_url: str, prompt: str, **kwargs: Any) -> FalJobResult:
        duration_s = kwargs.pop("duration_s", 5)
        payload = self._kling_payload(image_url, prompt, duration_s=duration_s, **kwargs)
        return await self.arun("kling-2.5-pro", payload)

    def runway_i2v(
        self,
        image_url: str,
        prompt: str,
        *,
        duration_s: int = 5,
        **kwargs: Any,
    ) -> FalJobResult:
        payload = self._runway_payload(image_url, prompt, duration_s=duration_s, **kwargs)
        return self.run("runway-gen3-alpha-turbo", payload)

    async def arunway_i2v(self, image_url: str, prompt: str, **kwargs: Any) -> FalJobResult:
        duration_s = kwargs.pop("duration_s", 5)
        payload = self._runway_payload(image_url, prompt, duration_s=duration_s, **kwargs)
        return await self.arun("runway-gen3-alpha-turbo", payload)

    def wan_i2v(
        self,
        image_url: str,
        prompt: str,
        *,
        duration_s: int = 5,
        **kwargs: Any,
    ) -> FalJobResult:
        payload = self._wan_payload(image_url, prompt, duration_s=duration_s, **kwargs)
        return self.run("wan-2.1-14b", payload)

    async def awan_i2v(self, image_url: str, prompt: str, **kwargs: Any) -> FalJobResult:
        duration_s = kwargs.pop("duration_s", 5)
        payload = self._wan_payload(image_url, prompt, duration_s=duration_s, **kwargs)
        return await self.arun("wan-2.1-14b", payload)

    # ---------------- routing determinístico ---------------------

    def dispatch_i2v(
        self,
        *,
        subject_type: str | None,
        image_url: str,
        prompt: str,
        duration_s: int = 5,
        model_override: str | None = None,
        **kwargs: Any,
    ) -> FalJobResult:
        """Elige el modelo I2V según `subject_type` (VIDEO_MODEL_ROUTING) y
        lo ejecuta. Permite override explícito con `model_override=`.

        Devuelve `FalJobResult` con `.first_url()` disponible.
        """
        chosen = model_override or choose_video_model(subject_type)
        log.info(
            "fal_dispatch_i2v",
            subject_type=subject_type,
            chosen_model=chosen,
            duration_s=duration_s,
        )
        if chosen == "kling-2.5-pro":
            return self.kling_i2v(image_url, prompt, duration_s=duration_s, **kwargs)
        if chosen == "runway-gen3-alpha-turbo":
            return self.runway_i2v(image_url, prompt, duration_s=duration_s, **kwargs)
        if chosen == "wan-2.1-14b":
            return self.wan_i2v(image_url, prompt, duration_s=duration_s, **kwargs)
        raise ValueError(
            f"Modelo I2V desconocido: {chosen!r}. "
            f"Routing values: {sorted(set(VIDEO_MODEL_ROUTING.values()))}"
        )

    async def adispatch_i2v(
        self,
        *,
        subject_type: str | None,
        image_url: str,
        prompt: str,
        duration_s: int = 5,
        model_override: str | None = None,
        **kwargs: Any,
    ) -> FalJobResult:
        chosen = model_override or choose_video_model(subject_type)
        log.info(
            "fal_dispatch_i2v",
            subject_type=subject_type,
            chosen_model=chosen,
            duration_s=duration_s,
        )
        if chosen == "kling-2.5-pro":
            return await self.akling_i2v(image_url, prompt, duration_s=duration_s, **kwargs)
        if chosen == "runway-gen3-alpha-turbo":
            return await self.arunway_i2v(image_url, prompt, duration_s=duration_s, **kwargs)
        if chosen == "wan-2.1-14b":
            return await self.awan_i2v(image_url, prompt, duration_s=duration_s, **kwargs)
        raise ValueError(f"Modelo I2V desconocido: {chosen!r}")

    # ==========================================================
    # mmaudio — SFX para video (video_url + prompt → video con audio)
    # ==========================================================

    def _mmaudio_payload(
        self,
        video_url: str,
        prompt: str,
        *,
        num_steps: int = 25,
        duration_s: int | None = None,
        negative_prompt: str | None = None,
    ) -> dict:
        p: dict = {
            "video_url": video_url,
            "prompt": prompt,
            "num_steps": num_steps,
        }
        if duration_s is not None:
            p["duration"] = duration_s
        if negative_prompt:
            p["negative_prompt"] = negative_prompt
        return p

    def mmaudio(self, video_url: str, prompt: str, **kwargs: Any) -> FalJobResult:
        """Agrega SFX/ambient audio al video usando mmaudio-v2. Devuelve
        el URL del video con audio mezclado."""
        payload = self._mmaudio_payload(video_url, prompt, **kwargs)
        return self.run("mmaudio-v2", payload)

    async def ammaudio(self, video_url: str, prompt: str, **kwargs: Any) -> FalJobResult:
        payload = self._mmaudio_payload(video_url, prompt, **kwargs)
        return await self.arun("mmaudio-v2", payload)

    # ==========================================================
    # Real-ESRGAN — upscale de imagen o video
    # ==========================================================

    def real_esrgan(
        self,
        image_url: str,
        *,
        scale: int | None = None,
        face_enhance: bool = True,
    ) -> FalJobResult:
        """Upscale con Real-ESRGAN. scale=2 default (1080→2160)."""
        payload = {
            "image_url": image_url,
            "scale": scale or settings.real_esrgan_scale,
            "face_enhance": face_enhance,
        }
        return self.run("real-esrgan", payload)

    async def areal_esrgan(self, image_url: str, **kwargs: Any) -> FalJobResult:
        payload = {
            "image_url": image_url,
            "scale": kwargs.get("scale") or settings.real_esrgan_scale,
            "face_enhance": kwargs.get("face_enhance", True),
        }
        return await self.arun("real-esrgan", payload)

    # ==========================================================
    # RIFE — frame interpolation
    # ==========================================================

    def rife_interpolate(
        self,
        video_url: str,
        *,
        target_fps: int | None = None,
    ) -> FalJobResult:
        payload = {
            "video_url": video_url,
            "target_fps": target_fps or settings.rife_target_fps,
        }
        return self.run("rife-interp", payload)

    async def arife_interpolate(self, video_url: str, **kwargs: Any) -> FalJobResult:
        payload = {
            "video_url": video_url,
            "target_fps": kwargs.get("target_fps") or settings.rife_target_fps,
        }
        return await self.arun("rife-interp", payload)

    # ==========================================================
    # TTS (PlayAI)
    # ==========================================================

    def tts(self, text: str, *, voice: str = "Jennifer (English (US)/American)") -> FalJobResult:
        """Text-to-speech con PlayAI v3. Devuelve URL del WAV."""
        payload = {"input": text, "voice": voice}
        return self.run("tts-playai", payload)

    async def atts(self, text: str, *, voice: str = "Jennifer (English (US)/American)") -> FalJobResult:
        payload = {"input": text, "voice": voice}
        return await self.arun("tts-playai", payload)


__all__ = [
    "FalClient",
    "FalJobResult",
    "FalJobFailed",
    "FalJobTimeout",
    "FAL_MODEL_IDS",
]
