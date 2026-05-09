"""
Sistema de Captura Multimodal — Motor perceptual del pipeline Guion_expert.
===========================================================================
Puente determinista entre la fenomenología del actor físico (o fuente AV de
referencia) y la Story Bible del proyecto.

Subsistemas:
    capture.schemas         → Pydantic: ActorIdentityTensor, BiometricFrame, etc.
    capture.config          → CaptureConfig (ports, thresholds, model paths)
    capture.ingestion       → FastAPI + WebSocket ingestion server (BTStamp, NTP)
    capture.extractors      → MotionBERT, MediaPipe/FACS, ECAPA-TDNN
    capture.fusion          → Tensor Fusion Network (TFN) + Cross-Attention
    capture.vector_store    → FAISS HNSW-backed Story Bible vector index
    capture.continuity      → Continuity Critic (vectorial OOC detection)
    capture.serialization   → JSON-LD Schema.org ontological output
    capture.orchestrator    → Main orchestrator tying all subsystems

Uso rápido:
    from capture import CaptureOrchestrator
    orch = CaptureOrchestrator()
    orch.initialize()
    orch.load_story_bible("output/.../story_bible.json")
    tensor = orch.process_frame(video_frame, audio_chunk)
"""

from capture.schemas import (
    ActorIdentityTensor,
    BiometricFrame,
    FACSReading,
    KinematicSkeleton,
    VocalEmbedding,
    BTStamp,
    ModalityVector,
    ContinuityAlert,
    CharacterArchetype,
    ScoresDatabaseEntry,
)
from capture.config import CaptureConfig
from capture.orchestrator import CaptureOrchestrator

__all__ = [
    "ActorIdentityTensor",
    "BiometricFrame",
    "FACSReading",
    "KinematicSkeleton",
    "VocalEmbedding",
    "BTStamp",
    "CaptureConfig",
    "ModalityVector",
    "ContinuityAlert",
    "CharacterArchetype",
    "ScoresDatabaseEntry",
    "CaptureOrchestrator",
]
