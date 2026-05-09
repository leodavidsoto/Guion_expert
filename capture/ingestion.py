"""
Ingesta — FastAPI + WebSocket server para captura multimodal.
==============================================================
Servidor asíncrono ASGI para ingesta de streams de video/audio
desde dispositivos de captura vía WebSocket bidireccional.

Cada paquete recibe un BTStamp (sello de bloque y tiempo) con
sincronización NTP antes de enrutar a los extractores.

Uso:
    from capture.ingestion import create_ingestion_app
    app = create_ingestion_app(config)
    # uvicorn capture.ingestion:app --host 0.0.0.0 --port 8100
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional, Callable, Any

from capture.schemas import BTStamp, BiometricFrame
from capture.config import CaptureConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


class IngestionServer:
    """Servidor de ingesta multimodal.

    Gestiona conexiones WebSocket, estampa BTStamps con
    corrección NTP, y despacha frames a los extractores.
    """

    def __init__(self, config: CaptureConfig = DEFAULT_CONFIG):
        self.config = config
        self._frame_counter: int = 0
        self._ntp_offset_ms: float = 0.0
        self._connections: dict[str, Any] = {}
        self._frame_callback: Optional[Callable] = None
        self._running = False

    def set_frame_callback(self, callback: Callable) -> None:
        """Registra callback para procesar frames entrantes.

        El callback recibe (device_id: str, btstamp: BTStamp, data: bytes).
        """
        self._frame_callback = callback

    def create_btstamp(self, device_id: str = "cam_0") -> BTStamp:
        """Genera un BTStamp sincronizado NTP."""
        self._frame_counter += 1
        return BTStamp(
            frame_counter=self._frame_counter,
            timestamp_unix=time.time(),
            device_id=device_id,
            ntp_offset_ms=self._ntp_offset_ms,
        )

    async def sync_ntp(self) -> float:
        """Sincroniza reloj local con servidor NTP (stub).

        En producción: usa ntplib para query al servidor NTP central.
        Returns offset en ms.
        """
        # Stub: offset simulado
        self._ntp_offset_ms = 0.5  # 0.5ms offset típico
        logger.info(f"NTP sync: offset={self._ntp_offset_ms}ms")
        return self._ntp_offset_ms

    async def handle_websocket_frame(
        self,
        device_id: str,
        data: bytes,
        modality: str = "video",
    ) -> Optional[BTStamp]:
        """Procesa un frame/chunk entrante por WebSocket.

        Args:
            device_id: ID del dispositivo de captura.
            data: Bytes del frame (video) o chunk (audio).
            modality: "video" o "audio".

        Returns:
            BTStamp asignado al paquete.
        """
        btstamp = self.create_btstamp(device_id)

        if self._frame_callback:
            await asyncio.coroutine(lambda: self._frame_callback(
                device_id, btstamp, data
            ))() if asyncio.iscoroutinefunction(self._frame_callback) else (
                self._frame_callback(device_id, btstamp, data)
            )

        return btstamp

    def get_status(self) -> dict:
        """Estado del servidor de ingesta."""
        return {
            "running": self._running,
            "connections": len(self._connections),
            "frames_processed": self._frame_counter,
            "ntp_offset_ms": self._ntp_offset_ms,
            "host": self.config.ingestion_host,
            "port": self.config.ingestion_port,
        }


def create_ingestion_app(config: CaptureConfig = DEFAULT_CONFIG):
    """Crea la aplicación FastAPI con endpoints WebSocket.

    Returns:
        FastAPI app lista para uvicorn.
    """
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.responses import JSONResponse
    except ImportError:
        logger.error("FastAPI not installed — pip install fastapi uvicorn")
        return None

    app = FastAPI(
        title="Guion_expert Multimodal Capture",
        description="Ingesta multimodal WebSocket para el pipeline generativo",
        version="1.0.0",
    )
    server = IngestionServer(config)

    @app.on_event("startup")
    async def startup():
        await server.sync_ntp()
        server._running = True
        logger.info(f"Ingestion server started on {config.ingestion_host}:{config.ingestion_port}")

    @app.get("/health")
    async def health():
        return JSONResponse(server.get_status())

    @app.websocket(config.websocket_path)
    async def websocket_capture(websocket: WebSocket):
        device_id = websocket.query_params.get("device_id", "cam_0")
        await websocket.accept()
        server._connections[device_id] = websocket
        logger.info(f"Device connected: {device_id}")

        try:
            while True:
                data = await websocket.receive_bytes()
                btstamp = await server.handle_websocket_frame(device_id, data)
                # Confirmar recepción
                await websocket.send_json({
                    "status": "ok",
                    "frame": btstamp.frame_counter,
                    "timestamp": btstamp.corrected_time,
                })
        except WebSocketDisconnect:
            server._connections.pop(device_id, None)
            logger.info(f"Device disconnected: {device_id}")

    return app


# App para uvicorn directo
app = create_ingestion_app()
