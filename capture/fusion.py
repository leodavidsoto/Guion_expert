"""
Fusión Multimodal — Tensor Fusion Network (TFN) + Cross-Attention.
===================================================================
Integra vectores cinemáticos, faciales y acústicos en el
Actor Identity Tensor unificado.

Arquitectura:
    z_a (acústico) ⊗ z_v (visual) ⊗ z_l (lingüístico) → Tensor 3D
    → Proyección → Cross-Attention (lips↔fonemas) → ActorIdentityTensor

El tensor resultante contiene:
    - Características unimodales aisladas
    - Todas las combinaciones bimodales
    - El espectro trimodal completo

Requiere: numpy
"""
from __future__ import annotations

import time
import logging
from typing import Optional

import numpy as np

from capture.schemas import (
    ActorIdentityTensor,
    ModalityVector,
    BiometricFrame,
    BTStamp,
)
from capture.config import CaptureConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


class TensorFusionNetwork:
    """Red de Fusión Tensorial (TFN) para dinámicas inter/intra-modales.

    Calcula el producto exterior de los tres vectores de modalidad,
    expandidos con una unidad constante antes del producto tensorial.
    """

    def __init__(self, config: CaptureConfig = DEFAULT_CONFIG):
        self.config = config
        self._projection_weights: Optional[np.ndarray] = None
        self._initialized = False

    def initialize(self) -> bool:
        """Inicializa pesos de proyección post-fusión."""
        # En producción: cargar pesos entrenados
        # Aquí: proyección aleatoria como placeholder
        # La dimensión del tensor exterior es (d_k+1)*(d_f+1)*(d_a+1)
        d_k = self.config.kinematic_dim + 1
        d_f = self.config.facial_dim + 1
        d_a = self.config.acoustic_dim + 1
        total_dim = d_k * d_f * d_a  # Puede ser enorme — se proyecta
        output_dim = self.config.fusion_output_dim

        # Proyección mediante random + normalización (Xavier-like)
        rng = np.random.RandomState(42)
        self._projection_weights = rng.randn(
            min(total_dim, 4096), output_dim  # Cap para eficiencia
        ).astype(np.float32)
        scale = np.sqrt(2.0 / (min(total_dim, 4096) + output_dim))
        self._projection_weights *= scale

        self._initialized = True
        logger.info(
            f"TFN initialized: tensor_dim≈{total_dim}, "
            f"projected→{output_dim}"
        )
        return True

    def fuse(
        self,
        z_kinematic: ModalityVector,
        z_facial: ModalityVector,
        z_acoustic: ModalityVector,
        z_linguistic: Optional[ModalityVector] = None,
        actor_id: str = "actor_0",
        btstamp: Optional[BTStamp] = None,
    ) -> ActorIdentityTensor:
        """Fusiona tres modalidades en un ActorIdentityTensor.

        Args:
            z_kinematic: Vector cinemático (MotionBERT).
            z_facial: Vector facial (FACS/MediaPipe).
            z_acoustic: Vector acústico (ECAPA-TDNN).
            z_linguistic: Opcional — vector semántico (Whisper ASR).
            actor_id: ID del actor.
            btstamp: Sello temporal del frame.

        Returns:
            ActorIdentityTensor con el tensor fusionado.
        """
        t0 = time.time()

        # Paso 1: Expandir vectores con unidad constante (TFN requirement)
        v_k = np.array([1.0] + z_kinematic.vector, dtype=np.float32)
        v_f = np.array([1.0] + z_facial.vector, dtype=np.float32)
        v_a = np.array([1.0] + z_acoustic.vector, dtype=np.float32)

        # Paso 2: Producto exterior simplificado
        # Full outer product sería v_k ⊗ v_f ⊗ v_a → demasiado grande
        # Usamos aproximación: concatenar productos bimodales + trimodal
        bimodal_kf = np.outer(v_k[:32], v_f[:32]).flatten()
        bimodal_ka = np.outer(v_k[:32], v_a[:32]).flatten()
        bimodal_fa = np.outer(v_f[:32], v_a[:32]).flatten()

        # Trimodal: hadamard product de los tres
        tri_len = min(len(v_k), len(v_f), len(v_a), 64)
        trimodal = v_k[:tri_len] * v_f[:tri_len] * v_a[:tri_len]

        # Concatenar todas las interacciones
        full_tensor = np.concatenate([
            v_k[:64],       # Unimodal kinematic
            v_f[:64],       # Unimodal facial
            v_a[:64],       # Unimodal acoustic
            bimodal_kf,     # Bimodal kinematic×facial
            bimodal_ka,     # Bimodal kinematic×acoustic
            bimodal_fa,     # Bimodal facial×acoustic
            trimodal,       # Trimodal
        ])

        # Paso 3: Proyectar a dimensión final
        fused = self._project(full_tensor)

        # Paso 4: Derivar métricas narrativas
        emotional_valence = self._compute_valence(z_facial, z_acoustic)
        emotional_arousal = self._compute_arousal(z_kinematic, z_acoustic)
        sarcasm_score = self._compute_sarcasm(z_acoustic, z_facial)
        deception_score = self._compute_deception(z_kinematic, z_facial, z_acoustic)

        elapsed_ms = (time.time() - t0) * 1000
        logger.debug(f"TFN fusion: {elapsed_ms:.1f}ms, dim={len(fused)}")

        return ActorIdentityTensor(
            actor_id=actor_id,
            kinematic_vector=z_kinematic.vector,
            facial_vector=z_facial.vector,
            acoustic_vector=z_acoustic.vector,
            linguistic_vector=z_linguistic.vector if z_linguistic else [],
            fused_tensor=fused.tolist(),
            fusion_dimension=len(fused),
            emotional_valence=emotional_valence,
            emotional_arousal=emotional_arousal,
            sarcasm_score=sarcasm_score,
            deception_score=deception_score,
            btstamp=btstamp,
        )

    def cross_attention(
        self,
        queries: np.ndarray,
        keys: np.ndarray,
        values: np.ndarray,
    ) -> np.ndarray:
        """Cross-Attention intermodal.

        Ejemplo: queries=lip_landmarks, keys/values=phonetic_features.
        Enseña a la red cuánto peso asignar cada píxel facial
        a cada sílaba específica del audio.
        """
        d_k = keys.shape[-1]
        scores = np.dot(queries, keys.T) / np.sqrt(d_k)
        # Softmax por fila
        exp_scores = np.exp(scores - scores.max(axis=-1, keepdims=True))
        attention_weights = exp_scores / (exp_scores.sum(axis=-1, keepdims=True) + 1e-8)
        return np.dot(attention_weights, values)

    # ── Proyección y métricas narrativas ─────────────

    def _project(self, tensor: np.ndarray) -> np.ndarray:
        """Proyecta tensor a dimensión fusion_output_dim."""
        if self._projection_weights is None:
            return tensor[:self.config.fusion_output_dim]

        # Truncar/pad tensor al tamaño esperado por la matriz de proyección
        proj_input_dim = self._projection_weights.shape[0]
        if len(tensor) < proj_input_dim:
            tensor = np.pad(tensor, (0, proj_input_dim - len(tensor)))
        elif len(tensor) > proj_input_dim:
            tensor = tensor[:proj_input_dim]

        projected = tensor @ self._projection_weights
        # Normalizar L2
        norm = np.linalg.norm(projected)
        if norm > 0:
            projected = projected / norm
        return projected

    def _compute_valence(self, z_f: ModalityVector, z_a: ModalityVector) -> float:
        """Valencia emocional: derivada de AU facial + pitch vocal."""
        f_vals = z_f.vector[:10] if len(z_f.vector) >= 10 else z_f.vector
        return float(np.clip(np.mean(f_vals) * 2 - 0.5, -1.0, 1.0))

    def _compute_arousal(self, z_k: ModalityVector, z_a: ModalityVector) -> float:
        """Arousal: activación basada en velocidad + volumen."""
        k_energy = np.mean(np.abs(z_k.vector[:20])) if z_k.vector else 0.0
        a_energy = np.mean(np.abs(z_a.vector[:20])) if z_a.vector else 0.0
        return float(np.clip((k_energy + a_energy) / 2, 0.0, 1.0))

    def _compute_sarcasm(self, z_a: ModalityVector, z_f: ModalityVector) -> float:
        """Sarcasmo: fricción entre z_a positivo y z_v negativo."""
        a_val = np.mean(z_a.vector[:10]) if z_a.vector else 0.0
        f_val = np.mean(z_f.vector[:10]) if z_f.vector else 0.0
        friction = abs(a_val - f_val)
        return float(np.clip(friction * 2, 0.0, 1.0))

    def _compute_deception(
        self, z_k: ModalityVector, z_f: ModalityVector, z_a: ModalityVector
    ) -> float:
        """Engaño: inconsistencia inter-modal (varianza entre modalidades)."""
        means = [
            np.mean(z_k.vector[:20]) if z_k.vector else 0.0,
            np.mean(z_f.vector[:20]) if z_f.vector else 0.0,
            np.mean(z_a.vector[:20]) if z_a.vector else 0.0,
        ]
        return float(np.clip(np.std(means) * 3, 0.0, 1.0))
