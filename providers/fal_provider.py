"""
providers/fal_provider.py — Backend fal.ai (Kling, Runway, WAN, Veo, Hailuo).

Envuelve las llamadas actuales de webapp/integrations/fal.py (y el código
imperativo de master_orchestrator) en la interfaz `VideoProvider`.

Diseño:
    - No rompe nada existente: las integraciones viejas siguen funcionando.
    - Si FAL_API_KEY falta, is_healthy() retorna False y el factory
      puede caer al otro provider o abortar explícitamente.
    - generate_i2v / generate_t2v normalizan params a la shape esperada
      por cada modelo fal (kling, runway-gen3, wan-2.1, veo, hailuo).
"""
from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Optional

from .base import GenerationResult, ProviderError, VideoProvider


# ────────────────────────────────────────────────────────────────────────
# Mapa: modelo canónico → endpoint fal.ai (queue URL)
# ────────────────────────────────────────────────────────────────────────
# Cuando el director_flow elige "kling-2.5-pro" / "runway-gen3-alpha-turbo" /
# "wan-2.1-14b", el fal_provider lo traduce al endpoint oficial.

FAL_I2V_ENDPOINTS: dict[str, str] = {
    "kling-2.5-pro":           "fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
    "kling-2.1-pro":           "fal-ai/kling-video/v2.1-pro/image-to-video",
    "kling":                   "fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
    "runway-gen3-alpha-turbo": "fal-ai/runway-gen3/turbo/image-to-video",
    "runway-gen3":             "fal-ai/runway-gen3/turbo/image-to-video",
    "wan-2.1-14b":             "fal-ai/wan-i2v",
    "wan-2.1":                 "fal-ai/wan-i2v",
    "hailuo-02-pro":           "fal-ai/minimax/hailuo-02/pro/image-to-video",
    "minimax-hailuo":          "fal-ai/minimax/hailuo-02/pro/image-to-video",
    "veo-3.1":                 "fal-ai/veo/3.1/image-to-video",
    "veo":                     "fal-ai/veo/3.1/image-to-video",
}

FAL_T2V_ENDPOINTS: dict[str, str] = {
    # fal.ai tiene T2V para algunos modelos; lo usamos cuando el director
    # pide T2V explícito pero el backend es fal (ej. preferred=fal pero
    # modality_override=t2v).
    "kling-2.5-pro":           "fal-ai/kling-video/v2.5-turbo/pro/text-to-video",
    "runway-gen3-alpha-turbo": "fal-ai/runway-gen3/turbo/text-to-video",
    "wan-2.1-14b":             "fal-ai/wan-t2v",
    "hailuo-02-pro":           "fal-ai/minimax/hailuo-02/pro/text-to-video",
    "veo-3.1":                 "fal-ai/veo/3.1/text-to-video",
}


class FalProvider(VideoProvider):
    """Backend fal.ai — llamadas HTTP a queue.fal.run con polling."""

    name = "fal"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://queue.fal.run",
        timeout_connect: float = 10.0,
        timeout_read: float = 300.0,
        max_retries: int = 3,
    ):
        self.api_key = api_key or os.getenv("FAL_API_KEY", "")
        self.base_url = base_url or os.getenv("FAL_BASE_URL", "https://queue.fal.run")
        self.timeout_connect = timeout_connect
        self.timeout_read = timeout_read
        self.max_retries = max_retries

    # ─────────────────────────── Health ───────────────────────────────

    def is_healthy(self) -> bool:
        """FalProvider está sano si la API key está presente.

        No hacemos ping HTTP acá porque fal.ai no expone /health público y
        un ping real costaría créditos. La validación verdadera pasa en
        el primer generate().
        """
        return bool(self.api_key) and self.api_key != "REEMPLAZAR_CON_TU_KEY_FAL"

    # ─────────────────────────── I2V ──────────────────────────────────

    def generate_i2v(
        self,
        image_path: Path,
        prompt: str,
        model: str,
        duration_seconds: float = 5.0,
        aspect_ratio: str = "16:9",
        output_path: Optional[Path] = None,
        extra: Optional[dict] = None,
    ) -> GenerationResult:
        endpoint = FAL_I2V_ENDPOINTS.get(model)
        if not endpoint:
            raise ProviderError(
                f"Modelo I2V '{model}' no tiene endpoint fal.ai registrado. "
                f"Keys disponibles: {sorted(FAL_I2V_ENDPOINTS.keys())}",
                backend="fal",
                retriable=False,
            )
        if not self.is_healthy():
            raise ProviderError(
                "FAL_API_KEY ausente o placeholder. Seteala en .env.",
                backend="fal",
                retriable=False,
            )

        output_path = output_path or self._default_output_path()
        image_data_uri = _encode_image_data_uri(image_path)
        payload = {
            "prompt": prompt,
            "image_url": image_data_uri,
            "duration": str(int(round(duration_seconds))),
            "aspect_ratio": aspect_ratio,
        }
        if extra:
            payload.update(extra)

        started = time.monotonic()
        video_url = self._submit_and_poll(endpoint, payload)
        _download(video_url, output_path, timeout=self.timeout_read)
        latency = time.monotonic() - started

        return GenerationResult(
            output_path=output_path,
            backend="fal",
            model=model,
            modality="i2v",
            duration_seconds=duration_seconds,
            latency_seconds=latency,
            meta={"endpoint": endpoint, "video_url": video_url},
        )

    # ─────────────────────────── T2V ──────────────────────────────────

    def generate_t2v(
        self,
        prompt: str,
        model: str,
        duration_seconds: float = 5.0,
        aspect_ratio: str = "16:9",
        output_path: Optional[Path] = None,
        extra: Optional[dict] = None,
    ) -> GenerationResult:
        endpoint = FAL_T2V_ENDPOINTS.get(model)
        if not endpoint:
            raise ProviderError(
                f"Modelo T2V '{model}' no tiene endpoint fal.ai registrado. "
                f"Considerá preferred_backend=trinity o cambiá modality a i2v. "
                f"Keys T2V disponibles: {sorted(FAL_T2V_ENDPOINTS.keys())}",
                backend="fal",
                retriable=False,
            )
        if not self.is_healthy():
            raise ProviderError(
                "FAL_API_KEY ausente o placeholder. Seteala en .env.",
                backend="fal",
                retriable=False,
            )

        output_path = output_path or self._default_output_path()
        payload = {
            "prompt": prompt,
            "duration": str(int(round(duration_seconds))),
            "aspect_ratio": aspect_ratio,
        }
        if extra:
            payload.update(extra)

        started = time.monotonic()
        video_url = self._submit_and_poll(endpoint, payload)
        _download(video_url, output_path, timeout=self.timeout_read)
        latency = time.monotonic() - started

        return GenerationResult(
            output_path=output_path,
            backend="fal",
            model=model,
            modality="t2v",
            duration_seconds=duration_seconds,
            latency_seconds=latency,
            meta={"endpoint": endpoint, "video_url": video_url},
        )

    # ─────────────────────── HTTP internals ───────────────────────────

    def _submit_and_poll(self, endpoint: str, payload: dict) -> str:
        """Submit a queue.fal.run y hace polling hasta COMPLETED. Retorna video URL."""
        try:
            import requests  # type: ignore
        except ImportError as e:
            raise ProviderError(
                "El paquete 'requests' no está instalado. pip install requests.",
                backend="fal",
                retriable=False,
                original=e,
            )

        headers = {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json",
        }
        submit_url = f"{self.base_url}/{endpoint}"

        # Submit
        try:
            r = requests.post(submit_url, json=payload, headers=headers,
                              timeout=(self.timeout_connect, self.timeout_read))
            r.raise_for_status()
        except Exception as e:
            raise ProviderError(
                f"fal submit falló: {e}",
                backend="fal",
                retriable=True,
                original=e,
            )
        data = r.json()
        status_url = data.get("status_url") or data.get("response_url")
        if not status_url:
            raise ProviderError(
                f"fal submit no devolvió status_url. Payload: {data}",
                backend="fal",
                retriable=False,
            )

        # Poll
        deadline = time.monotonic() + self.timeout_read
        while time.monotonic() < deadline:
            try:
                pr = requests.get(status_url, headers=headers,
                                  timeout=(self.timeout_connect, 30.0))
                pr.raise_for_status()
                st = pr.json()
            except Exception as e:
                # Error transitorio: esperar y seguir
                time.sleep(2.0)
                continue

            status = st.get("status") or st.get("state")
            if status in ("COMPLETED", "completed", "success"):
                # Fetch result
                result_url = st.get("response_url") or status_url
                rr = requests.get(result_url, headers=headers,
                                  timeout=(self.timeout_connect, 30.0))
                rr.raise_for_status()
                result = rr.json()
                video = (result.get("video") or result.get("videos", [{}])[0] or {})
                url = video.get("url") or result.get("video_url")
                if not url:
                    raise ProviderError(
                        f"fal completó pero sin url de video. Result: {result}",
                        backend="fal",
                        retriable=False,
                    )
                return url
            if status in ("FAILED", "failed", "error"):
                raise ProviderError(
                    f"fal generación falló: {st}",
                    backend="fal",
                    retriable=True,
                )
            # IN_QUEUE / IN_PROGRESS → esperar
            time.sleep(3.0)

        raise ProviderError(
            f"fal timeout tras {self.timeout_read}s polling {status_url}",
            backend="fal",
            retriable=True,
        )


# ──────────────────────────── Utilidades módulo ────────────────────────

def _encode_image_data_uri(image_path: Path) -> str:
    """Lee la imagen y la devuelve como data URI base64 (formato que fal acepta)."""
    image_path = Path(image_path)
    ext = image_path.suffix.lstrip(".").lower() or "jpg"
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext, "image/jpeg")
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def _download(url: str, dest: Path, timeout: float = 300.0) -> None:
    """Descarga el mp4 final a disco."""
    try:
        import requests  # type: ignore
    except ImportError as e:
        raise ProviderError("requests no instalado", backend="fal", retriable=False, original=e)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=(10.0, timeout)) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                if chunk:
                    f.write(chunk)
