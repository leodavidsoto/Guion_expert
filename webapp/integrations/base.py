"""
BaseHTTPClient — cliente HTTP compartido para todos los integrations.
======================================================================

Por qué existe
--------------
Todos los servicios externos que consumimos (fal.ai, Suno, mmaudio
cuando lo exponemos) hablan HTTP(S) con JSON. En vez de que cada
integration escriba su propio httpx client con su propio retry loop
y su propio logging, centralizamos acá:

- **Retries** en 5xx/429/connect errors con backoff exponencial.
- **Timeouts** configurables (connect vs read) — I2V puede tardar
  minutos; connect debería fallar rápido.
- **Auth headers** inyectados por subclase (Bearer, Basic, custom).
- **Structlog context** — cada request loguea con `pipeline_id` +
  `trace_id` si están en el contexto (ver Commit 3).
- **Rate limit** — respeta `Retry-After` header de respuestas 429.
- **Sync + async** — ambas variantes disponibles; el asset_generator
  (Commit 11) usa async para paralelizar FLUX/I2V/Suno.

Uso
---
Subclasear, implementar `_auth_headers()`, y usar:

    class FalClient(BaseHTTPClient):
        def __init__(self):
            super().__init__(base_url=settings.fal_base_url)

        def _auth_headers(self) -> dict[str, str]:
            return {"Authorization": f"Key {settings.fal_api_key.get_secret_value()}"}

        def submit_flux(self, prompt: str) -> dict:
            return self.post("/fal-ai/flux-lora", json={"prompt": prompt})

Fail-fast
---------
- Si el subclase no implementa `_auth_headers()`, raises NotImplementedError.
- Si la response es 4xx (que no sea 429), raises `HTTPClientError` inmediato.
- Solo 5xx + 429 + connect/read errors disparan retry.
"""
from __future__ import annotations

import asyncio
import random
import time
from typing import Any

import httpx
import structlog

from webapp.config import settings

log = structlog.get_logger(__name__)


# ============================================================
# Excepciones
# ============================================================


class HTTPClientError(Exception):
    """Error HTTP no-retryable (4xx que no sea 429)."""

    def __init__(self, message: str, *, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class RetryableError(HTTPClientError):
    """Error retryable (5xx, connect/read, JSON malformado)."""


class RateLimitError(RetryableError):
    """429 Too Many Requests — respeta `Retry-After` si viene."""

    def __init__(self, message: str, *, retry_after: float | None = None, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


# ============================================================
# Cliente base
# ============================================================


class BaseHTTPClient:
    """
    Cliente HTTP compartido con retries + timeouts + auth + logs.

    Parameters
    ----------
    base_url
        Base URL del servicio. Todas las rutas relativas se resuelven
        contra esta URL.
    timeout_connect, timeout_read
        Timeouts en segundos. Si es None, usa los globales de `settings`.
    max_retries
        Reintentos en errores retryables. None = usa `settings.http_max_retries`.
    backoff_base
        Base del backoff exponencial: `base ** attempt + jitter`.
    extra_headers
        Headers custom que se mergean con `_auth_headers()`.
    verify_ssl
        True en prod. False solo para desarrollo contra self-hosted.
    """

    def __init__(
        self,
        *,
        base_url: str,
        timeout_connect: float | None = None,
        timeout_read: float | None = None,
        max_retries: int | None = None,
        backoff_base: float | None = None,
        extra_headers: dict[str, str] | None = None,
        verify_ssl: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_connect = timeout_connect or settings.http_timeout_connect
        self.timeout_read = timeout_read or settings.http_timeout_read
        self.max_retries = settings.http_max_retries if max_retries is None else max_retries
        self.backoff_base = backoff_base or settings.http_backoff_base
        self.extra_headers = extra_headers or {}
        self.verify_ssl = verify_ssl

        # Lazy — el client se crea al primer uso y se reutiliza.
        self._sync_client: httpx.Client | None = None
        self._async_client: httpx.AsyncClient | None = None

    # ---------------- subclass hooks -----------------------------------

    def _auth_headers(self) -> dict[str, str]:
        """
        Headers de autenticación. Subclase DEBE implementar.

        Returns
        -------
        dict[str, str]
            Ej: `{"Authorization": f"Bearer {token}"}`.
        """
        raise NotImplementedError(
            f"{type(self).__name__} debe implementar _auth_headers()"
        )

    def _service_name(self) -> str:
        """Nombre corto del servicio, para logs. Override opcional."""
        return type(self).__name__.replace("Client", "").lower()

    # ---------------- lifecycle ----------------------------------------

    def _headers(self) -> dict[str, str]:
        hdrs = {
            "Accept": "application/json",
            "User-Agent": "guion-expert/2.1.0 (+https://github.com/leodavidsoto/Guion_expert)",
        }
        hdrs.update(self._auth_headers())
        hdrs.update(self.extra_headers)
        return hdrs

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.timeout_connect,
            read=self.timeout_read,
            write=self.timeout_read,
            pool=self.timeout_connect,
        )

    def _get_sync_client(self) -> httpx.Client:
        if self._sync_client is None:
            self._sync_client = httpx.Client(
                base_url=self.base_url,
                headers=self._headers(),
                timeout=self._timeout(),
                verify=self.verify_ssl,
                follow_redirects=True,
            )
        return self._sync_client

    def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers(),
                timeout=self._timeout(),
                verify=self.verify_ssl,
                follow_redirects=True,
            )
        return self._async_client

    def close(self) -> None:
        """Cierra los clients httpx. Llamar al shutdown del servidor."""
        if self._sync_client is not None:
            self._sync_client.close()
            self._sync_client = None

    async def aclose(self) -> None:
        if self._async_client is not None:
            await self._async_client.aclose()
            self._async_client = None

    # Context manager support
    def __enter__(self) -> "BaseHTTPClient":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    async def __aenter__(self) -> "BaseHTTPClient":
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.aclose()

    # ---------------- response handling --------------------------------

    def _raise_for_status(self, response: httpx.Response) -> None:
        """
        Clasifica la response:
        - 2xx → ok, no-op.
        - 429 → RateLimitError (retryable con Retry-After).
        - 5xx → RetryableError.
        - 4xx (otros) → HTTPClientError (no-retryable, bug del cliente).
        """
        if response.is_success:
            return

        body = response.text[:2000]  # cap para logs
        status = response.status_code

        if status == 429:
            retry_after_hdr = response.headers.get("Retry-After")
            retry_after = None
            if retry_after_hdr:
                try:
                    retry_after = float(retry_after_hdr)
                except ValueError:
                    retry_after = None
            raise RateLimitError(
                f"{self._service_name()} rate-limited (429)",
                retry_after=retry_after,
                status_code=status,
                body=body,
            )

        if 500 <= status < 600:
            raise RetryableError(
                f"{self._service_name()} {status} server error",
                status_code=status,
                body=body,
            )

        # 4xx no-retryable (401/403/404/422/etc) — es bug del caller.
        raise HTTPClientError(
            f"{self._service_name()} {status} client error: {body[:200]}",
            status_code=status,
            body=body,
        )

    def _parse_json(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as e:
            raise RetryableError(
                f"{self._service_name()} returned non-JSON: {response.text[:200]}"
            ) from e

    # ---------------- retry loop ---------------------------------------

    def _compute_backoff(self, attempt: int, retry_after: float | None = None) -> float:
        """
        Backoff exponencial con jitter. Si viene Retry-After de 429, usalo.
        attempt: 0, 1, 2, ... → 1.5s, 2.25s, 3.38s, ...
        """
        if retry_after is not None and retry_after > 0:
            return min(retry_after, 120.0)  # cap a 2min
        base = self.backoff_base ** (attempt + 1)
        jitter = random.uniform(0, 0.3 * base)
        return min(base + jitter, 60.0)

    # ---------------- sync requests ------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict | None = None,
        data: Any = None,
        files: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """
        Request sync con retries. Devuelve JSON parseado si content-type
        es json; si no, devuelve el httpx.Response crudo.
        """
        client = self._get_sync_client()
        merged_headers = headers or {}

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            t0 = time.monotonic()
            try:
                response = client.request(
                    method=method,
                    url=path,
                    json=json,
                    params=params,
                    data=data,
                    files=files,
                    headers=merged_headers,
                )
                elapsed = time.monotonic() - t0
                log.debug(
                    "http_request",
                    service=self._service_name(),
                    method=method,
                    path=path,
                    status=response.status_code,
                    elapsed_s=round(elapsed, 3),
                    attempt=attempt,
                )
                self._raise_for_status(response)

                # Success
                ct = response.headers.get("content-type", "")
                if "application/json" in ct:
                    return self._parse_json(response)
                return response

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as e:
                last_exc = RetryableError(
                    f"{self._service_name()} transport error: {e}"
                )
                log.warning(
                    "http_transport_error",
                    service=self._service_name(),
                    method=method,
                    path=path,
                    attempt=attempt,
                    error=str(e),
                )

            except RateLimitError as e:
                last_exc = e
                if attempt >= self.max_retries:
                    break
                wait = self._compute_backoff(attempt, e.retry_after)
                log.warning(
                    "http_rate_limited",
                    service=self._service_name(),
                    attempt=attempt,
                    retry_after_s=e.retry_after,
                    sleep_s=round(wait, 2),
                )
                time.sleep(wait)
                continue

            except RetryableError as e:
                last_exc = e
                log.warning(
                    "http_retryable_error",
                    service=self._service_name(),
                    attempt=attempt,
                    status=e.status_code,
                    error=str(e)[:200],
                )

            except HTTPClientError:
                # No-retryable — bubble up inmediato.
                raise

            # Si llegamos acá: hubo RetryableError (transport o 5xx).
            if attempt >= self.max_retries:
                break
            wait = self._compute_backoff(attempt)
            log.debug("http_retry_sleep", service=self._service_name(), sleep_s=round(wait, 2))
            time.sleep(wait)

        # Agotamos retries.
        assert last_exc is not None
        raise last_exc

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self.request("DELETE", path, **kwargs)

    # ---------------- async requests -----------------------------------

    async def arequest(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict | None = None,
        data: Any = None,
        files: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """
        Request async con retries. Mismo contrato que `request()` pero
        await-able. Usado por asset_generator (Commit 11) para
        paralelizar FLUX/I2V/Suno.
        """
        client = self._get_async_client()
        merged_headers = headers or {}

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            t0 = time.monotonic()
            try:
                response = await client.request(
                    method=method,
                    url=path,
                    json=json,
                    params=params,
                    data=data,
                    files=files,
                    headers=merged_headers,
                )
                elapsed = time.monotonic() - t0
                log.debug(
                    "http_request",
                    service=self._service_name(),
                    method=method,
                    path=path,
                    status=response.status_code,
                    elapsed_s=round(elapsed, 3),
                    attempt=attempt,
                )
                self._raise_for_status(response)
                ct = response.headers.get("content-type", "")
                if "application/json" in ct:
                    return self._parse_json(response)
                return response

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as e:
                last_exc = RetryableError(
                    f"{self._service_name()} transport error: {e}"
                )
                log.warning(
                    "http_transport_error",
                    service=self._service_name(),
                    method=method,
                    path=path,
                    attempt=attempt,
                    error=str(e),
                )

            except RateLimitError as e:
                last_exc = e
                if attempt >= self.max_retries:
                    break
                wait = self._compute_backoff(attempt, e.retry_after)
                log.warning(
                    "http_rate_limited",
                    service=self._service_name(),
                    attempt=attempt,
                    retry_after_s=e.retry_after,
                    sleep_s=round(wait, 2),
                )
                await asyncio.sleep(wait)
                continue

            except RetryableError as e:
                last_exc = e
                log.warning(
                    "http_retryable_error",
                    service=self._service_name(),
                    attempt=attempt,
                    status=e.status_code,
                    error=str(e)[:200],
                )

            except HTTPClientError:
                raise

            if attempt >= self.max_retries:
                break
            wait = self._compute_backoff(attempt)
            await asyncio.sleep(wait)

        assert last_exc is not None
        raise last_exc

    async def aget(self, path: str, **kwargs: Any) -> Any:
        return await self.arequest("GET", path, **kwargs)

    async def apost(self, path: str, **kwargs: Any) -> Any:
        return await self.arequest("POST", path, **kwargs)

    async def aput(self, path: str, **kwargs: Any) -> Any:
        return await self.arequest("PUT", path, **kwargs)

    async def adelete(self, path: str, **kwargs: Any) -> Any:
        return await self.arequest("DELETE", path, **kwargs)
