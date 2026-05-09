"""
Extractor Acústico — ECAPA-TDNN + Whisper.
==========================================
Destila la huella biométrica de la voz y métricas de
"Dialogue as Music" (Sorkin).

Pipeline:
    Audio chunk → ECAPA-TDNN (speaker embedding 192-d)
    Audio chunk → Whisper ASR (transcripción + fonemas)
    → Métricas: syllabic rate, pitch, overlapping, non-sequitur

Requiere:
    pip install numpy
    (speechbrain y whisper como dependencias opcionales)
"""
from __future__ import annotations

import time
import logging
from typing import Optional

import numpy as np

from capture.schemas import VocalEmbedding, ModalityVector
from capture.config import CaptureConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


class AcousticExtractor:
    """Wrapper ECAPA-TDNN + Whisper para identidad acústica y métricas Sorkin.

    Extrae:
    - Speaker embedding (192-d, EER ~1.71%)
    - Syllabic rate, pitch, volume, overlap ratio
    - Pause anomaly score (non-sequitur detection)
    """

    def __init__(self, config: CaptureConfig = DEFAULT_CONFIG):
        self.config = config
        self._ecapa_model = None
        self._whisper_model = None
        self._initialized = False
        self._speaker_registry: dict[str, np.ndarray] = {}

    def initialize(self) -> bool:
        """Carga ECAPA-TDNN y Whisper. Returns True si OK."""
        try:
            logger.info(
                f"AcousticExtractor: loading ECAPA-TDNN "
                f"({self.config.ecapa_model_source})..."
            )
            # NOTE: En producción:
            #   from speechbrain.pretrained import EncoderClassifier
            #   self._ecapa_model = EncoderClassifier.from_hparams(
            #       source=self.config.ecapa_model_source
            #   )
            #   import whisper
            #   self._whisper_model = whisper.load_model(self.config.whisper_model_size)
            self._initialized = True
            logger.info("AcousticExtractor initialized (stub mode)")
            return True
        except Exception as e:
            logger.error(f"AcousticExtractor init failed: {e}")
            return False

    def extract(
        self,
        audio_chunk: np.ndarray,
        sample_rate: int = 16000,
    ) -> VocalEmbedding:
        """Extrae embedding vocal y métricas acústicas.

        Args:
            audio_chunk: Audio mono float32 numpy array.
            sample_rate: Tasa de muestreo (default 16kHz para ECAPA).

        Returns:
            VocalEmbedding con embedding, métricas Sorkin y speaker ID.
        """
        t0 = time.time()

        embedding = self._extract_ecapa_embedding(audio_chunk, sample_rate)
        metrics = self._compute_sorkin_metrics(audio_chunk, sample_rate)
        speaker_id = self._identify_speaker(embedding)

        vocal = VocalEmbedding(
            speaker_id=speaker_id,
            embedding_dim=self.config.ecapa_embedding_dim,
            embedding_vector=embedding.tolist(),
            syllabic_rate=metrics["syllabic_rate"],
            pitch_mean_hz=metrics["pitch_mean_hz"],
            pitch_variance=metrics["pitch_variance"],
            volume_db=metrics["volume_db"],
            overlap_ratio=metrics["overlap_ratio"],
            pause_anomaly_score=metrics["pause_anomaly_score"],
        )

        elapsed_ms = (time.time() - t0) * 1000
        if elapsed_ms > self.config.max_extraction_latency_ms:
            logger.warning(f"Acoustic extraction slow: {elapsed_ms:.1f}ms")

        return vocal

    def register_speaker(self, speaker_id: str, embedding: np.ndarray) -> None:
        """Registra un hablante conocido para identificación futura."""
        self._speaker_registry[speaker_id] = embedding / (
            np.linalg.norm(embedding) + 1e-8
        )

    def to_modality_vector(self, vocal: VocalEmbedding) -> ModalityVector:
        """Convierte VocalEmbedding en vector normalizado para fusión TFN."""
        vec = list(vocal.embedding_vector)
        # Agregar métricas prosódicas normalizadas
        vec.extend([
            vocal.syllabic_rate / 10.0,     # normalizar ~0-10 syl/s
            vocal.pitch_mean_hz / 500.0,     # normalizar ~0-500 Hz
            vocal.pitch_variance / 100.0,
            (vocal.volume_db + 80) / 80.0,   # normalizar -80 a 0 dB
            vocal.overlap_ratio,
            vocal.pause_anomaly_score,
        ])

        # Pad/truncar a acoustic_dim
        target_dim = self.config.acoustic_dim
        if len(vec) < target_dim:
            vec.extend([0.0] * (target_dim - len(vec)))
        elif len(vec) > target_dim:
            vec = vec[:target_dim]

        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = (np.array(vec) / norm).tolist()

        return ModalityVector(modality="acoustic", vector=vec)

    # ── Métodos internos ─────────────────────────────

    def _extract_ecapa_embedding(
        self, audio: np.ndarray, sr: int
    ) -> np.ndarray:
        """ECAPA-TDNN speaker embedding (stub).

        En producción: 22.3M parámetros, bloques SE + convoluciones
        agrupadas, entrenado con VoxCeleb1+2.
        """
        dim = self.config.ecapa_embedding_dim
        # Stub: embedding pseudo-aleatorio seeded por audio stats
        seed = int(abs(audio.sum()) * 1000) % (2**31)
        rng = np.random.RandomState(seed)
        emb = rng.randn(dim).astype(np.float32)
        emb = emb / (np.linalg.norm(emb) + 1e-8)
        return emb

    def _compute_sorkin_metrics(
        self, audio: np.ndarray, sr: int
    ) -> dict[str, float]:
        """Calcula métricas de Dialogue-as-Music (stub).

        En producción: Whisper ASR + minería de tripletes + nt-xent loss.
        """
        duration_s = len(audio) / sr if sr > 0 else 1.0

        # Volume RMS
        rms = float(np.sqrt(np.mean(audio**2)))
        volume_db = float(20 * np.log10(rms + 1e-8))

        # Pitch estimation (stub — en prod: CREPE o pYIN)
        pitch_mean = 150.0 + np.random.uniform(-30, 30)
        pitch_var = 15.0 + np.random.uniform(0, 10)

        # Syllabic rate (stub — en prod: Whisper timestamps)
        syllabic_rate = 4.0 + np.random.uniform(-1, 1)

        return {
            "syllabic_rate": float(syllabic_rate),
            "pitch_mean_hz": float(pitch_mean),
            "pitch_variance": float(pitch_var),
            "volume_db": float(volume_db),
            "overlap_ratio": 0.0,
            "pause_anomaly_score": float(np.random.uniform(0, 0.3)),
        }

    def _identify_speaker(self, embedding: np.ndarray) -> str:
        """Identifica hablante por similitud coseno con registro."""
        if not self._speaker_registry:
            return "unknown"

        emb_norm = embedding / (np.linalg.norm(embedding) + 1e-8)
        best_id = "unknown"
        best_sim = -1.0

        for sid, ref_emb in self._speaker_registry.items():
            sim = float(np.dot(emb_norm, ref_emb))
            if sim > best_sim:
                best_sim = sim
                best_id = sid

        # Umbral de aceptación
        if best_sim > 0.7:
            return best_id
        return "unknown"
