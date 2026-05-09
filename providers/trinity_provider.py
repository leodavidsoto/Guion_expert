"""
providers/trinity_provider.py — Backend Trinity (Colab A100 self-hosted).

Habla HTTP con el notebook `openmontage_trinity_pro.ipynb` que expone un
mini servidor FastAPI detrás de un túnel (ngrok o Cloudflare Tunnel).

Contrato con el notebook:
    POST {TRINITY_URL}/i2v
        body: { image_b64, prompt, model, duration_seconds, aspect_ratio }
        resp: { video_url_or_b64, elapsed_s, model_used }
    POST {TRINITY_URL}/t2v
        body: { prompt, model, duration_seconds, aspect_ratio }
        resp: { video_url_or_b64, elapsed_s, model_used }
    GET  {TRINITY_URL}/health
        resp: { status: "ok", models_loaded: [...], vram_mb: ... }

Autenticación: header `X-Trinity-Token: {TRINITY_TOKEN}` (shared secret).

Política de errores:
    - Timeout HTTP → ProviderError(retriable=True)        → factory cae a fal
    - 5xx del Colab → ProviderError(retriable=True)       → factory cae a fal
    - 4xx (mal request, modelo no soportado) → retriable=False
    - Respuesta sin video → retriable=False
"""
from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Optional

from .base import GenerationResult, ProviderError, VideoProvider


TRINITY_SUPPORTED_MODELS = {
    "i2v": {"wan-2.1-14b", "wan-2.1"},
    "t2v": {"skyreels-v1", "skyreels", "hunyuan-13b", "hunyuan"},
}


class TrinityProvider(VideoProvider):
    """Backend Trinity (Colab A100 self-hosted, open source)."""

    name = "trinity"

    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
        timeout_connect: float = 5.0,
        timeout_read: float = 900.0,  # Colab puede ser lento la primera vez
        health_timeout: float = 3.0,
    ):
        self.url = (url or os.getenv("TRINITY_URL", "")).rstrip("/")
        self.token = token or os.getenv("TRINITY_TOKEN", "")
        self.timeout_connect = timeout_connect
        self.timeout_read = timeout_read
        self.health_timeout = health_timeout

    # ─────────────────────────── Health ───────────────────────────────

    def is_healthy(self) -> bool:
        """Pinguea /health del notebook. Retorna False si:
        - TRINITY_URL vacío
        - No responde en health_timeout
        - Responde algo distinto a status=ok
        """
        if not self.url:
            return False
        try:
            import requests  # type: ignore
        except ImportError:
            return False
        try:
            headers = {"X-Trinity-Token": self.token} if self.token else {}
            r = requests.get(f"{self.url}/health", headers=headers,
                             timeout=(self.timeout_connect, self.health_timeout))
            if r.status_code != 200:
                return False
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            return body.get("status") == "ok"
        except Exception:
            return False

    def supports(self, modality: str, model: str) -> bool:
        return model in TRINITY_SUPPORTED_MODELS.get(modality, set())

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
        if not self.supports("i2v", model):
            raise ProviderError(
                f"Trinity no soporta el modelo I2V '{model}'. "
                f"Soportados: {sorted(TRINITY_SUPPORTED_MODELS['i2v'])}",
                backend="trinity",
                retriable=False,
            )
        if not self.url:
            raise ProviderError(
                "TRINITY_URL no configurada. Setealo en .env cuando levantes el Colab.",
                backend="trinity",
                retriable=False,
            )

        output_path = output_path or self._default_output_path()
        image_b64 = _read_b64(image_path)
        payload = {
            "image_b64": image_b64,
            "prompt": prompt,
            "model": model,
            "duration_seconds": duration_seconds,
            "aspect_ratio": aspect_ratio,
        }
        if extra:
            payload.update(extra)

        return self._post_and_download(
            path="/i2v", payload=payload, output_path=output_path,
            model=model, modality="i2v", duration_seconds=duration_seconds,
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
        if not self.supports("t2v", model):
            raise ProviderError(
                f"Trinity no soporta el modelo T2V '{model}'. "
                f"Soportados: {sorted(TRINITY_SUPPORTED_MODELS['t2v'])}",
                backend="trinity",
                retriable=False,
            )
        if not self.url:
            raise ProviderError(
                "TRINITY_URL no configurada. Setealo en .env cuando levantes el Colab.",
                backend="trinity",
                retriable=False,
            )

        output_path = output_path or self._default_output_path()
        payload = {
            "prompt": prompt,
            "model": model,
            "duration_seconds": duration_seconds,
            "aspect_ratio": aspect_ratio,
        }
        if extra:
            payload.update(extra)

        return self._post_and_download(
            path="/t2v", payload=payload, output_path=output_path,
            model=model, modality="t2v", duration_seconds=duration_seconds,
        )

    # ─────────────────────── HTTP internals ───────────────────────────

    def _post_and_download(
        self,
        path: str,
        payload: dict,
        output_path: Path,
        model: str,
        modality: str,
        duration_seconds: float,
    ) -> GenerationResult:
        try:
            import requests  # type: ignore
        except ImportError as e:
            raise ProviderError(
                "requests no instalado. pip install requests.",
                backend="trinity", retriable=False, original=e,
            )

        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["X-Trinity-Token"] = self.token

        started = time.monotonic()
        try:
            r = requests.post(
                f"{self.url}{path}",
                json=payload, headers=headers,
                timeout=(self.timeout_connect, self.timeout_read),
            )
        except requests.exceptions.ConnectionError as e:
            raise ProviderError(
                f"Trinity no alcanzable ({self.url}): {e}. "
                "El notebook Colab puede haberse dormido o el túnel caído.",
                backend="trinity", retriable=True, original=e,
            )
        except requests.exceptions.Timeout as e:
            raise ProviderError(
                f"Trinity timeout tras {self.timeout_read}s — GPU saturada.",
                backend="trinity", retriable=True, original=e,
            )

        if r.status_code >= 500:
            raise ProviderError(
                f"Trinity 5xx: {r.status_code} {r.text[:200]}",
                backend="trinity", retriable=True,
            )
        if r.status_code >= 400:
            raise ProviderError(
                f"Trinity 4xx: {r.status_code} {r.text[:200]}",
                backend="trinity", retriable=False,
            )

        data = r.json()
        # La respuesta puede venir como URL (tunnel/S3) o como b64 inline.
        video_url = data.get("video_url")
        video_b64 = data.get("video_b64")
        if video_url:
            _download_http(video_url, output_path, timeout=self.timeout_read)
        elif video_b64:
            _write_b64(video_b64, output_path)
        else:
            raise ProviderError(
                f"Trinity respondió sin video (url ni b64): keys={list(data.keys())}",
                backend="trinity", retriable=False,
            )

        latency = time.monotonic() - started
        return GenerationResult(
            output_path=output_path,
            backend="trinity",
            model=data.get("model_used", model),
            modality=modality,
            duration_seconds=duration_seconds,
            latency_seconds=latency,
            cost_usd_est=0.0,  # self-hosted, costo = GPU cloud del usuario
            meta={
                "elapsed_s_server": data.get("elapsed_s"),
                "vram_peak_mb": data.get("vram_peak_mb"),
            },
        )


# ──────────────────────────── Utilidades módulo ────────────────────────

def _read_b64(image_path: Path) -> str:
    """Lee imagen a base64 plain (sin data URI — el notebook lo prefiere así)."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _write_b64(b64: str, dest: Path) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        f.write(base64.b64decode(b64))


def _download_http(url: str, dest: Path, timeout: float) -> None:
    import requests  # type: ignore
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=(10.0, timeout)) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                if chunk:
                    f.write(chunk)
