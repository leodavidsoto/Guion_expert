"""
providers/base.py — Interface + tipos compartidos.

Define el contrato que todo backend de video debe implementar.
Diseñado para ser mínimo y estable: solo dos métodos (I2V y T2V)
más info de capacidad.

Los errores se normalizan a `ProviderError` para que el código
cliente pueda hacer fallback limpio sin conocer el backend origen.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional


Modality = Literal["i2v", "t2v"]
BackendName = Literal["fal", "trinity"]


class ProviderError(RuntimeError):
    """Error normalizado de cualquier provider.

    Attrs:
        backend: cuál backend disparó el error ('fal' | 'trinity').
        retriable: True si vale la pena reintentar / caer a otro backend.
        original: excepción original (para logs / debug).
    """

    def __init__(
        self,
        message: str,
        backend: BackendName,
        retriable: bool = True,
        original: Optional[BaseException] = None,
    ):
        super().__init__(message)
        self.backend = backend
        self.retriable = retriable
        self.original = original


@dataclass
class GenerationResult:
    """Resultado unificado de una generación de video."""

    # Ruta local al mp4 resultante (obligatoria — siempre descargamos).
    output_path: Path
    # Backend y modelo que efectivamente sirvieron el request.
    backend: BackendName = "fal"
    model: str = ""
    modality: Modality = "i2v"
    # Métricas útiles para observabilidad y billing.
    duration_seconds: float = 0.0
    latency_seconds: float = 0.0
    cost_usd_est: float = 0.0
    # Metadata libre — log structured consumer.
    meta: dict = field(default_factory=dict)


class VideoProvider(ABC):
    """Contrato para todo backend de generación de video."""

    name: BackendName = "fal"  # subclass override

    # ──────────────────────── Capability check ─────────────────────────

    @abstractmethod
    def is_healthy(self) -> bool:
        """Retorna True si el backend está listo para recibir requests.

        Para fal.ai: verifica que FAL_API_KEY esté presente.
        Para Trinity: pinguea el endpoint /health del Colab notebook.

        Debe ser RÁPIDO (<2s). Se llama antes de cada scene en modo auto.
        """

    def supports(self, modality: Modality, model: str) -> bool:
        """Sobreescribible: ¿este provider soporta esta combinación?
        Default: True (todos soportan todos los modelos). Útil para
        subclasses muy específicas.
        """
        return True

    # ──────────────────────── Generation API ──────────────────────────

    @abstractmethod
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
        """Image-to-Video: genera video animando la imagen ancla.

        El prompt describe el movimiento (no la composición — la composición
        ya está en la imagen). Los modelos I2V ignoran en gran medida las
        descripciones de sujeto/ambiente porque las leen del frame 0.
        """

    @abstractmethod
    def generate_t2v(
        self,
        prompt: str,
        model: str,
        duration_seconds: float = 5.0,
        aspect_ratio: str = "16:9",
        output_path: Optional[Path] = None,
        extra: Optional[dict] = None,
    ) -> GenerationResult:
        """Text-to-Video puro: genera video desde cero a partir del texto.

        El prompt debe ser DENSO: sujeto + acción + entorno + cámara +
        estilo + física. El modelo no tiene imagen para apoyarse.
        """

    # ──────────────────────── Helpers compartidos ─────────────────────

    def _default_output_path(self, scene_id: str = "") -> Path:
        """Path por defecto si el cliente no provee uno."""
        import tempfile
        prefix = f"{scene_id}-" if scene_id else "video-"
        return Path(tempfile.mkstemp(prefix=prefix, suffix=".mp4")[1])
