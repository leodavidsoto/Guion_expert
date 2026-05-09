"""
Configuración del Sistema de Captura Multimodal.
=================================================
Centraliza paths de modelos, puertos, umbrales y parámetros
de todos los subsistemas. Cargable desde variables de entorno.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field


class CaptureConfig(BaseModel):
    """Configuración global del sistema de captura."""

    # ── Servidor de ingesta ──────────────────────────
    ingestion_host: str = Field(default="0.0.0.0")
    ingestion_port: int = Field(default=8100)
    websocket_path: str = Field(default="/ws/capture")
    ntp_server: str = Field(default="pool.ntp.org")
    ntp_sync_interval_s: int = Field(default=300)

    # ── Extractores ──────────────────────────────────
    # MotionBERT
    motionbert_checkpoint: str = Field(
        default="checkpoint/motionbert/best_epoch.bin",
        description="Path al checkpoint pre-entrenado de MotionBERT.",
    )
    motionbert_batch_size: int = Field(default=16)
    alphapose_model: str = Field(
        default="halpe136",
        description="Modelo AlphaPose para keypoints 2D iniciales.",
    )

    # MediaPipe
    mediapipe_model_path: str = Field(
        default="",
        description="Path al modelo MediaPipe Face Landmarker (vacío = default).",
    )
    mediapipe_min_detection_confidence: float = Field(default=0.5)
    mediapipe_min_tracking_confidence: float = Field(default=0.5)
    opengraphau_model: str = Field(
        default="resnet50",
        description="Backbone para clasificación FACS (ResNet50).",
    )

    # ECAPA-TDNN
    ecapa_model_source: str = Field(
        default="speechbrain/spkrec-ecapa-voxceleb",
        description="Fuente HuggingFace del modelo ECAPA-TDNN.",
    )
    ecapa_embedding_dim: int = Field(default=192)
    whisper_model_size: str = Field(
        default="base",
        description="Tamaño del modelo Whisper ASR (tiny/base/small/medium/large).",
    )

    # ── Fusión TFN ───────────────────────────────────
    kinematic_dim: int = Field(default=256, description="Dimensión del vector cinemático.")
    facial_dim: int = Field(default=256, description="Dimensión del vector facial.")
    acoustic_dim: int = Field(default=192, description="Dimensión del vector acústico.")
    fusion_hidden_dim: int = Field(default=512, description="Capa oculta post-fusión.")
    fusion_output_dim: int = Field(default=256, description="Dimensión del tensor fusionado final.")

    # ── FAISS Vector Store ───────────────────────────
    faiss_index_type: str = Field(
        default="HNSW32",
        description="Tipo de índice FAISS: HNSW32, IVF256, Flat.",
    )
    faiss_metric: str = Field(
        default="cosine",
        description="Métrica de distancia: cosine, l2, ip.",
    )
    faiss_ef_search: int = Field(default=64, description="HNSW ef_search parameter.")
    faiss_ef_construction: int = Field(default=200, description="HNSW ef_construction.")

    # ── Continuity Critic ────────────────────────────
    ooc_threshold: float = Field(
        default=0.35,
        ge=0.0, le=1.0,
        description="Umbral de distancia cosenoidal para alertas OOC.",
    )
    drift_threshold: float = Field(
        default=0.25,
        ge=0.0, le=1.0,
        description="Umbral para alertas de drift gradual.",
    )

    # ── Presupuesto de latencia ──────────────────────
    max_frame_latency_ms: float = Field(
        default=100.0,
        description="Latencia máxima por frame completo (ms).",
    )
    max_extraction_latency_ms: float = Field(
        default=50.0,
        description="Latencia máxima por extractor individual (ms).",
    )

    # ── Paths de persistencia ────────────────────────
    vector_store_path: Optional[str] = Field(
        default=None,
        description="Path para persistir el índice FAISS. None = in-memory.",
    )
    capture_log_dir: str = Field(
        default="output/capture_logs",
        description="Directorio para logs de captura.",
    )


# Configuración default singleton
DEFAULT_CONFIG = CaptureConfig()
