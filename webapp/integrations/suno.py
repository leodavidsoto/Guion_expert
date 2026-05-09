"""
Suno integration — música original via `gcui-art/suno-api` (self-hosted).
==========================================================================

Por qué self-hosted
-------------------
Suno NO tiene API pública oficial. `gcui-art/suno-api` es un reverse-proxy
que habla con suno.com usando la cookie de sesión del usuario (Leo paga
Premium). Lo corremos como servicio Docker al lado de `guion-web`, en la
misma red compose.

La cookie se refresca cada ~24h según la vida de la sesión de suno.com —
si empieza a fallar con 401/403, regenerar desde DevTools y actualizar
`SUNO_COOKIE` en `.env`.

Flujo
-----
1. `POST /api/custom_generate` con `{prompt, tags, title, make_instrumental,
   wait_audio: false, model}` → devuelve N clips con `id` pero `audio_url`
   vacío y `status="submitted"`.
2. `GET /api/get?ids=<clip_id,...>` cada ~5s hasta que cada clip termine
   en `status="streaming"` (parcial, 20-30s de audio) o `status="complete"`
   (el mp3 final con `audio_url` completo).
3. Descargar el mp3 de `audio_url` → guardar local → referenciar desde el
   `resolved_assets` del scene_plan.

**Por defecto esperamos a "complete"** para evitar audio streaming corrupto.
Setear `wait_for_streaming=True` si querés el parcial para preview rápido.

API endpoints de gcui-art/suno-api que usamos
---------------------------------------------
- `POST /api/custom_generate` — modo custom (tu propio lyrics + style).
  Payload: `{prompt, tags, title, make_instrumental, wait_audio, model}`.
- `POST /api/generate` — modo simple (solo description, Suno inventa todo).
- `GET /api/get?ids=<csv>` — status + URLs de clips específicos.
- `GET /api/get` — últimos 10 clips (útil para debug).
- `GET /api/get_limit` — créditos restantes de la cuenta.

Uso típico desde asset_generator (Commit 11):

    async with SunoClient() as suno:
        clip = await suno.agenerate_song(
            prompt=master_stack.sonic.music_brief,
            tags=", ".join(master_stack.sonic.music_reference_artists),
            title=f"3SM — {master_stack.narrative_beat}",
            instrumental=True,  # reels sin letra
        )
        print(clip.audio_url)   # mp3 listo para descargar
        print(clip.duration_s)  # duración real (usalo para cortar)

Fail-fast
---------
- Si `SUNO_COOKIE` no está seteada, el constructor raises.
- Si el primer submit vuelve 401/403, bubble up `HTTPClientError` —
  probablemente la cookie expiró.
- Si ningún clip termina dentro de `suno_poll_max_wait_s`, raises
  `SunoTimeout`.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from webapp.config import settings
from webapp.integrations.base import (
    BaseHTTPClient,
    HTTPClientError,
    RetryableError,
)

log = structlog.get_logger(__name__)


# ============================================================
# Excepciones
# ============================================================


class SunoClipFailed(HTTPClientError):
    """Un clip terminó con status='error' o similar."""


class SunoTimeout(RetryableError):
    """Ningún clip completó dentro del cap de espera."""


# ============================================================
# Clip
# ============================================================


@dataclass
class SunoClip:
    """Un clip de Suno. Suno siempre genera 2 clips por submit (variantes),
    aunque nosotros típicamente usamos solo el mejor (`select_best()`)."""

    id: str
    status: str
    title: str = ""
    audio_url: str = ""
    video_url: str = ""
    image_url: str = ""
    lyrics: str = ""
    prompt: str = ""
    tags: str = ""
    model_name: str = ""
    duration_s: float = 0.0
    is_instrumental: bool = False
    created_at: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        return self.status == "complete" and bool(self.audio_url)

    @property
    def is_streaming(self) -> bool:
        """'streaming' = audio_url ya apunta al stream parcial pero
        todavía se está renderizando el mp3 final."""
        return self.status == "streaming" and bool(self.audio_url)

    @property
    def is_failed(self) -> bool:
        return self.status in ("error", "failed")

    @classmethod
    def from_api(cls, data: dict) -> "SunoClip":
        """Parsea un clip del formato que devuelve gcui-art/suno-api."""
        metadata = data.get("metadata") or {}
        return cls(
            id=data.get("id") or data.get("clip_id") or "",
            status=data.get("status", "unknown"),
            title=data.get("title", ""),
            audio_url=data.get("audio_url", "") or data.get("audio", {}).get("url", "") if isinstance(data.get("audio"), dict) else data.get("audio_url", ""),
            video_url=data.get("video_url", ""),
            image_url=data.get("image_url", ""),
            lyrics=metadata.get("prompt", "") or data.get("lyric", ""),
            prompt=metadata.get("prompt", "") or data.get("prompt", ""),
            tags=metadata.get("tags", "") or data.get("tags", ""),
            model_name=data.get("model_name", "") or metadata.get("model_name", ""),
            duration_s=float(metadata.get("duration", 0.0) or data.get("duration", 0.0) or 0.0),
            is_instrumental=bool(metadata.get("is_instrumental", False)),
            created_at=data.get("created_at", ""),
            raw=data,
        )


# ============================================================
# Cliente
# ============================================================


class SunoClient(BaseHTTPClient):
    """Cliente para `gcui-art/suno-api` (self-hosted reverse-proxy a suno.com)."""

    def __init__(
        self,
        *,
        cookie: str | None = None,
        base_url: str | None = None,
        poll_interval_s: float | None = None,
        poll_max_wait_s: float | None = None,
        model: str | None = None,
    ) -> None:
        ck = cookie if cookie is not None else settings.suno_cookie.get_secret_value()
        if not ck or "REEMPLAZAR" in ck.upper():
            raise ValueError(
                "SUNO_COOKIE no configurada. Sacala de suno.com (DevTools → "
                "Cookies) y pegala en .env. Leo paga Premium; la cookie se "
                "refresca cada ~24h."
            )
        self._cookie = ck
        self.poll_interval_s = poll_interval_s or settings.suno_poll_interval_s
        self.poll_max_wait_s = poll_max_wait_s or settings.suno_poll_max_wait_s
        self.model = model or settings.suno_model

        super().__init__(
            base_url=base_url or settings.suno_api_url,
            # Suno api responde rápido a cada request individual; el long-running
            # vive en el poll-loop.
            timeout_read=30.0,
        )

    def _auth_headers(self) -> dict[str, str]:
        # gcui-art/suno-api NO usa Bearer — mete la cookie como header
        # `Cookie` que relaya a suno.com. Se puede setear al submit level,
        # pero lo ponemos acá para que todos los requests la lleven.
        return {
            "Cookie": self._cookie,
            "Content-Type": "application/json",
        }

    def _service_name(self) -> str:
        return "suno"

    # ==========================================================
    # Endpoints base
    # ==========================================================

    def get_limit(self) -> dict:
        """GET /api/get_limit — créditos restantes."""
        return self.get("/api/get_limit")

    async def aget_limit(self) -> dict:
        return await self.aget("/api/get_limit")

    def get_clips(self, clip_ids: list[str] | None = None) -> list[SunoClip]:
        """GET /api/get[?ids=...] — status de clips específicos o últimos 10."""
        params = {"ids": ",".join(clip_ids)} if clip_ids else None
        resp = self.get("/api/get", params=params)
        if not isinstance(resp, list):
            raise HTTPClientError(
                f"suno /api/get esperaba lista, got {type(resp).__name__}: {str(resp)[:200]}"
            )
        return [SunoClip.from_api(c) for c in resp]

    async def aget_clips(self, clip_ids: list[str] | None = None) -> list[SunoClip]:
        params = {"ids": ",".join(clip_ids)} if clip_ids else None
        resp = await self.aget("/api/get", params=params)
        if not isinstance(resp, list):
            raise HTTPClientError(
                f"suno /api/get esperaba lista, got {type(resp).__name__}: {str(resp)[:200]}"
            )
        return [SunoClip.from_api(c) for c in resp]

    # ==========================================================
    # Generación
    # ==========================================================

    def _custom_payload(
        self,
        *,
        prompt: str,
        tags: str,
        title: str,
        instrumental: bool = False,
        model: str | None = None,
    ) -> dict:
        # "prompt" en modo custom = la letra/lyrics (o descripción larga
        # si instrumental=True; Suno lo ignora igual).
        # "tags" = géneros/estilos separados por coma (ej.
        # "dark indie rock, minimalist, 120bpm, bass-driven").
        return {
            "prompt": prompt,
            "tags": tags,
            "title": title,
            "make_instrumental": instrumental,
            "wait_audio": False,   # no bloquear submit; poll nosotros
            "model": model or self.model,
        }

    def _simple_payload(
        self,
        *,
        description: str,
        instrumental: bool = False,
        model: str | None = None,
    ) -> dict:
        return {
            "prompt": description,
            "make_instrumental": instrumental,
            "wait_audio": False,
            "model": model or self.model,
        }

    def submit_custom(
        self,
        *,
        prompt: str,
        tags: str,
        title: str,
        instrumental: bool | None = None,
        model: str | None = None,
    ) -> list[SunoClip]:
        """POST /api/custom_generate — devuelve 2 clips (variants) con
        `id` seteado pero `audio_url` vacío. Usar `wait_for_clips()` o
        `generate_song()` para esperar al mp3 final."""
        instr = settings.suno_default_instrumental if instrumental is None else instrumental
        payload = self._custom_payload(
            prompt=prompt, tags=tags, title=title, instrumental=instr, model=model
        )
        log.info("suno_submit_custom", title=title, instrumental=instr, tag_count=len(tags.split(",")))
        resp = self.post("/api/custom_generate", json=payload)
        clips = self._parse_submit_response(resp)
        log.info("suno_submitted", clip_ids=[c.id for c in clips])
        return clips

    async def asubmit_custom(
        self,
        *,
        prompt: str,
        tags: str,
        title: str,
        instrumental: bool | None = None,
        model: str | None = None,
    ) -> list[SunoClip]:
        instr = settings.suno_default_instrumental if instrumental is None else instrumental
        payload = self._custom_payload(
            prompt=prompt, tags=tags, title=title, instrumental=instr, model=model
        )
        log.info("suno_submit_custom", title=title, instrumental=instr)
        resp = await self.apost("/api/custom_generate", json=payload)
        clips = self._parse_submit_response(resp)
        log.info("suno_submitted", clip_ids=[c.id for c in clips])
        return clips

    def submit_simple(
        self,
        description: str,
        *,
        instrumental: bool | None = None,
        model: str | None = None,
    ) -> list[SunoClip]:
        """POST /api/generate — modo simple, Suno inventa título/estilo."""
        instr = settings.suno_default_instrumental if instrumental is None else instrumental
        payload = self._simple_payload(description=description, instrumental=instr, model=model)
        log.info("suno_submit_simple", desc_len=len(description), instrumental=instr)
        resp = self.post("/api/generate", json=payload)
        clips = self._parse_submit_response(resp)
        log.info("suno_submitted", clip_ids=[c.id for c in clips])
        return clips

    async def asubmit_simple(
        self,
        description: str,
        *,
        instrumental: bool | None = None,
        model: str | None = None,
    ) -> list[SunoClip]:
        instr = settings.suno_default_instrumental if instrumental is None else instrumental
        payload = self._simple_payload(description=description, instrumental=instr, model=model)
        log.info("suno_submit_simple", desc_len=len(description), instrumental=instr)
        resp = await self.apost("/api/generate", json=payload)
        clips = self._parse_submit_response(resp)
        log.info("suno_submitted", clip_ids=[c.id for c in clips])
        return clips

    def _parse_submit_response(self, resp: Any) -> list[SunoClip]:
        """`gcui-art/suno-api` devuelve a veces `[{...}, {...}]` directo,
        a veces `{"data": [...]}`, a veces `{"clips": [...]}`. Cubrimos
        los 3."""
        if isinstance(resp, list):
            items = resp
        elif isinstance(resp, dict):
            items = resp.get("data") or resp.get("clips") or []
            if not items and "id" in resp:
                items = [resp]
        else:
            items = []
        if not items:
            raise HTTPClientError(
                f"suno submit devolvió respuesta vacía o malformada: {str(resp)[:300]}"
            )
        return [SunoClip.from_api(c) for c in items]

    # ==========================================================
    # Polling
    # ==========================================================

    def wait_for_clips(
        self,
        clip_ids: list[str],
        *,
        wait_for_streaming: bool = False,
        poll_interval_s: float | None = None,
        max_wait_s: float | None = None,
    ) -> list[SunoClip]:
        """Poll bloqueante hasta que todos los clip_ids estén complete
        (o streaming, si `wait_for_streaming=True`). Devuelve los clips
        finales con `audio_url` poblado."""
        interval = poll_interval_s or self.poll_interval_s
        cap = max_wait_s or self.poll_max_wait_s

        t0 = time.monotonic()
        last_states: dict[str, str] = {}

        while True:
            clips = self.get_clips(clip_ids)

            # Log cambios de estado
            for c in clips:
                if last_states.get(c.id) != c.status:
                    log.info(
                        "suno_clip_status",
                        clip_id=c.id,
                        status=c.status,
                        title=c.title,
                    )
                    last_states[c.id] = c.status

            # Fail-fast si alguno erroró
            failed = [c for c in clips if c.is_failed]
            if failed:
                raise SunoClipFailed(
                    f"suno clips fallaron: {[c.id for c in failed]} "
                    f"(statuses: {[c.status for c in failed]})"
                )

            # Done condition
            done_fn = (
                (lambda c: c.is_complete or c.is_streaming)
                if wait_for_streaming
                else (lambda c: c.is_complete)
            )
            if all(done_fn(c) for c in clips):
                elapsed = time.monotonic() - t0
                log.info(
                    "suno_clips_ready",
                    clip_ids=[c.id for c in clips],
                    elapsed_s=round(elapsed, 1),
                )
                return clips

            elapsed = time.monotonic() - t0
            if elapsed > cap:
                raise SunoTimeout(
                    f"suno clips {clip_ids} no completaron en {cap}s. "
                    f"Last statuses: {last_states}"
                )
            time.sleep(interval)

    async def await_for_clips(
        self,
        clip_ids: list[str],
        *,
        wait_for_streaming: bool = False,
        poll_interval_s: float | None = None,
        max_wait_s: float | None = None,
    ) -> list[SunoClip]:
        """Variante async del poll-loop."""
        interval = poll_interval_s or self.poll_interval_s
        cap = max_wait_s or self.poll_max_wait_s

        t0 = time.monotonic()
        last_states: dict[str, str] = {}

        while True:
            clips = await self.aget_clips(clip_ids)

            for c in clips:
                if last_states.get(c.id) != c.status:
                    log.info(
                        "suno_clip_status",
                        clip_id=c.id,
                        status=c.status,
                        title=c.title,
                    )
                    last_states[c.id] = c.status

            failed = [c for c in clips if c.is_failed]
            if failed:
                raise SunoClipFailed(
                    f"suno clips fallaron: {[c.id for c in failed]} "
                    f"(statuses: {[c.status for c in failed]})"
                )

            done_fn = (
                (lambda c: c.is_complete or c.is_streaming)
                if wait_for_streaming
                else (lambda c: c.is_complete)
            )
            if all(done_fn(c) for c in clips):
                elapsed = time.monotonic() - t0
                log.info(
                    "suno_clips_ready",
                    clip_ids=[c.id for c in clips],
                    elapsed_s=round(elapsed, 1),
                )
                return clips

            elapsed = time.monotonic() - t0
            if elapsed > cap:
                raise SunoTimeout(
                    f"suno clips {clip_ids} no completaron en {cap}s. "
                    f"Last statuses: {last_states}"
                )
            await asyncio.sleep(interval)

    # ==========================================================
    # High-level convenience
    # ==========================================================

    def generate_song(
        self,
        *,
        prompt: str,
        tags: str,
        title: str,
        instrumental: bool | None = None,
        model: str | None = None,
        wait_for_streaming: bool = False,
    ) -> SunoClip:
        """Submit + wait. Devuelve el MEJOR de los 2 clips (el que tiene
        mayor `duration_s`; si ambos son iguales, el primero)."""
        clips = self.submit_custom(
            prompt=prompt,
            tags=tags,
            title=title,
            instrumental=instrumental,
            model=model,
        )
        clip_ids = [c.id for c in clips]
        completed = self.wait_for_clips(clip_ids, wait_for_streaming=wait_for_streaming)
        return self.select_best(completed)

    async def agenerate_song(
        self,
        *,
        prompt: str,
        tags: str,
        title: str,
        instrumental: bool | None = None,
        model: str | None = None,
        wait_for_streaming: bool = False,
    ) -> SunoClip:
        clips = await self.asubmit_custom(
            prompt=prompt,
            tags=tags,
            title=title,
            instrumental=instrumental,
            model=model,
        )
        clip_ids = [c.id for c in clips]
        completed = await self.await_for_clips(clip_ids, wait_for_streaming=wait_for_streaming)
        return self.select_best(completed)

    @staticmethod
    def select_best(clips: list[SunoClip]) -> SunoClip:
        """Heurística simple: la clip más larga. Si son iguales, la primera.

        Criterio: Suno a veces genera una variante más corta (truncada)
        y una más completa; queremos la completa.
        """
        if not clips:
            raise SunoClipFailed("no clips para seleccionar")
        return max(clips, key=lambda c: c.duration_s)


__all__ = [
    "SunoClient",
    "SunoClip",
    "SunoClipFailed",
    "SunoTimeout",
]
