"""
Extractor Cinemático — MotionBERT + AlphaPose.
===============================================
Captura la dinámica postural y relación espacial del actor.

Pipeline:
    Frame RGB → AlphaPose (Halpe keypoints 2D) → MotionBERT DSTformer
    → Esqueleto 3D (coordenadas + profundidad Z inferida)
    → KinematicSkeleton (proxémica, apertura postural, velocidad)

Requiere:
    pip install torch numpy
    (MotionBERT y AlphaPose se cargan como módulos PyTorch)
"""
from __future__ import annotations

import time
import logging
from typing import Optional

import numpy as np

from capture.schemas import KinematicSkeleton, Joint3D, ModalityVector
from capture.config import CaptureConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


# ============================================================
# Nombres de articulaciones HALPE-136 (subset 26 principales)
# ============================================================
HALPE_JOINT_NAMES = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
    "head_top", "neck", "pelvis", "thorax",
    "spine", "left_toe", "right_toe", "left_heel", "right_heel",
]


class KinematicExtractor:
    """Wrapper para MotionBERT: extracción de cinemática corporal 3D.

    Interfaz agnóstica al backend: usa MotionBERT si torch disponible,
    fallback a estimación heurística 2D si no.
    """

    def __init__(self, config: CaptureConfig = DEFAULT_CONFIG):
        self.config = config
        self._model = None
        self._alphapose = None
        self._device = "cpu"
        self._prev_skeleton: Optional[KinematicSkeleton] = None
        self._prev_time: float = 0.0
        self._initialized = False

    def initialize(self) -> bool:
        """Carga los modelos MotionBERT y AlphaPose. Returns True si OK."""
        try:
            import torch
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"KinematicExtractor: device={self._device}")
            # NOTE: En producción, aquí se cargaría:
            #   1. AlphaPose con backbone HRNet + dataset Halpe
            #   2. MotionBERT DSTformer checkpoint
            # Por ahora se usa el pipeline en modo stub para validar la interfaz.
            self._initialized = True
            logger.info("KinematicExtractor initialized (stub mode)")
            return True
        except ImportError:
            logger.warning("torch not available — KinematicExtractor in heuristic mode")
            self._initialized = True
            return True

    def extract(
        self,
        frame: np.ndarray,
        keypoints_2d: Optional[np.ndarray] = None,
    ) -> KinematicSkeleton:
        """Extrae el esqueleto 3D de un frame.

        Args:
            frame: Frame RGB (H, W, 3) como numpy array.
            keypoints_2d: Opcional — keypoints 2D pre-computados (N, 3).
                Si None, se ejecuta AlphaPose internamente.

        Returns:
            KinematicSkeleton con joints 3D, proxémica y postura.
        """
        t0 = time.time()

        if keypoints_2d is None:
            keypoints_2d = self._run_alphapose(frame)

        joints_3d = self._run_motionbert(keypoints_2d)
        skeleton = self._build_skeleton(joints_3d)

        # Calcular velocidad espacial si hay frame previo
        if self._prev_skeleton and self._prev_time > 0:
            dt = time.time() - self._prev_time
            if dt > 0:
                skeleton.spatial_velocity = self._compute_velocity(
                    self._prev_skeleton, skeleton, dt
                )

        self._prev_skeleton = skeleton
        self._prev_time = time.time()

        elapsed_ms = (time.time() - t0) * 1000
        if elapsed_ms > self.config.max_extraction_latency_ms:
            logger.warning(f"Kinematic extraction slow: {elapsed_ms:.1f}ms")

        return skeleton

    def to_modality_vector(self, skeleton: KinematicSkeleton) -> ModalityVector:
        """Convierte KinematicSkeleton en vector normalizado para fusión TFN."""
        # Serializar joints como vector plano [x,y,z,conf, x,y,z,conf, ...]
        vec = []
        for j in skeleton.joints:
            vec.extend([j.x, j.y, j.z, j.confidence])
        # Agregar métricas de postura
        vec.extend([
            skeleton.proxemic_radius,
            skeleton.posture_openness,
            skeleton.spatial_velocity,
        ])
        # Pad/truncar a kinematic_dim
        target_dim = self.config.kinematic_dim
        if len(vec) < target_dim:
            vec.extend([0.0] * (target_dim - len(vec)))
        elif len(vec) > target_dim:
            vec = vec[:target_dim]
        # Normalizar L2
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = (np.array(vec) / norm).tolist()

        return ModalityVector(modality="kinematic", vector=vec)

    # ── Métodos internos ─────────────────────────────

    def _run_alphapose(self, frame: np.ndarray) -> np.ndarray:
        """Ejecuta AlphaPose para obtener keypoints 2D (stub).

        En producción: AlphaPose con Halpe-136 dataset, backbone HRNet-W48.
        Retorna array (N_joints, 3) con [x, y, confidence].
        """
        h, w = frame.shape[:2]
        n_joints = len(HALPE_JOINT_NAMES)
        # Stub: keypoints distribuidos uniformemente
        keypoints = np.zeros((n_joints, 3), dtype=np.float32)
        for i in range(n_joints):
            keypoints[i] = [w * (i + 1) / (n_joints + 1), h * 0.5, 0.8]
        return keypoints

    def _run_motionbert(self, keypoints_2d: np.ndarray) -> np.ndarray:
        """Ejecuta MotionBERT DSTformer para inferir profundidad Z (stub).

        En producción: DSTformer con lotes de 16 secuencias,
        optimizador AdamW, atención dual espacial-temporal.
        Retorna array (N_joints, 3) con coordenadas 3D [x, y, z].
        """
        n_joints = keypoints_2d.shape[0]
        joints_3d = np.zeros((n_joints, 3), dtype=np.float32)
        joints_3d[:, :2] = keypoints_2d[:, :2]
        # Stub: profundidad Z estimada heurísticamente
        joints_3d[:, 2] = np.random.uniform(-0.5, 0.5, n_joints)
        return joints_3d

    def _build_skeleton(self, joints_3d: np.ndarray) -> KinematicSkeleton:
        """Construye KinematicSkeleton a partir de coordenadas 3D."""
        joints = []
        for i, name in enumerate(HALPE_JOINT_NAMES[:joints_3d.shape[0]]):
            joints.append(Joint3D(
                name=name,
                x=float(joints_3d[i, 0]),
                y=float(joints_3d[i, 1]),
                z=float(joints_3d[i, 2]),
                confidence=0.8,
            ))

        # Calcular apertura postural (distancia entre manos relativa a hombros)
        openness = self._compute_openness(joints_3d)
        # Estimar radio proxémico
        proxemic = self._compute_proxemic_radius(joints_3d)

        return KinematicSkeleton(
            joints=joints,
            proxemic_radius=proxemic,
            posture_openness=openness,
        )

    def _compute_openness(self, joints_3d: np.ndarray) -> float:
        """Calcula apertura postural: ratio manos/hombros."""
        if joints_3d.shape[0] < 11:
            return 0.5
        # Índices: left_wrist=9, right_wrist=10, left_shoulder=5, right_shoulder=6
        hand_dist = np.linalg.norm(joints_3d[9, :2] - joints_3d[10, :2])
        shoulder_dist = np.linalg.norm(joints_3d[5, :2] - joints_3d[6, :2])
        if shoulder_dist < 1e-6:
            return 0.5
        ratio = float(hand_dist / (shoulder_dist * 2.5))
        return float(np.clip(ratio, 0.0, 1.0))

    def _compute_proxemic_radius(self, joints_3d: np.ndarray) -> float:
        """Estima el radio proxémico basado en la extensión del esqueleto."""
        if joints_3d.shape[0] < 2:
            return 0.5
        center = joints_3d.mean(axis=0)
        distances = np.linalg.norm(joints_3d - center, axis=1)
        return float(distances.max()) * 0.001  # Normalizar a metros aprox.

    def _compute_velocity(
        self, prev: KinematicSkeleton, curr: KinematicSkeleton, dt: float
    ) -> float:
        """Calcula velocidad del centro de masa entre frames."""
        if not prev.joints or not curr.joints:
            return 0.0
        prev_center = np.mean([[j.x, j.y, j.z] for j in prev.joints], axis=0)
        curr_center = np.mean([[j.x, j.y, j.z] for j in curr.joints], axis=0)
        dist = float(np.linalg.norm(curr_center - prev_center))
        return dist / dt if dt > 0 else 0.0
