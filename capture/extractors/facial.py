"""
Extractor Facial — MediaPipe + FACS (OpenGraphAU).
===================================================
Decodifica microexpresiones faciales en Unidades de Acción FACS
con significado narrativo.

Pipeline:
    Frame RGB → MediaPipe Face Landmarker (BlazeFace)
    → Malla 3D + blendshapes + pose de cabeza
    → OpenGraphAU (ResNet50) → AU scores
    → FACSReading con decodificadores narrativos

Requiere:
    pip install mediapipe numpy
    (OpenGraphAU como módulo PyTorch opcional)
"""
from __future__ import annotations

import time
import logging
from typing import Optional

import numpy as np

from capture.schemas import FACSReading, ModalityVector
from capture.config import CaptureConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


# ============================================================
# Mapeo AU → nombre descriptivo para logs
# ============================================================
AU_DESCRIPTIONS = {
    "AU1": "Inner Brow Raise (Frontalis medialis)",
    "AU2": "Outer Brow Raise (Frontalis lateralis)",
    "AU4": "Brow Lowerer (Corrugator)",
    "AU5": "Upper Lid Raise (Levator palpebrae)",
    "AU6": "Cheek Raise (Orbicularis oculi)",
    "AU7": "Lid Tightener",
    "AU9": "Nose Wrinkler (Levator labii)",
    "AU10": "Upper Lip Raiser",
    "AU12": "Lip Corner Puller (Zygomaticus major)",
    "AU14": "Dimpler (Buccinator)",
    "AU15": "Lip Corner Depressor (Depressor anguli oris)",
    "AU17": "Chin Raiser (Mentalis)",
    "AU20": "Lip Stretcher (Risorius)",
    "AU23": "Lip Tightener (Orbicularis oris)",
    "AU25": "Lips Part",
    "AU26": "Jaw Drop (Masseter/pterygoid)",
    "AU28": "Lip Suck",
    "AU45": "Blink",
}

# Combinaciones narrativas FACS
NARRATIVE_FACS_PATTERNS = {
    "inner_conflict": {"required": ["AU1", "AU4"], "label": "Conflicto Interno / Dolor"},
    "social_mask": {"required": ["AU12"], "absent": ["AU6"], "label": "Máscara Social (Pan Am)"},
    "panic_shock": {"required": ["AU5", "AU26"], "label": "Pánico y Shock"},
    "contempt": {"required": ["AU14"], "label": "Desprecio"},
    "suppressed_anger": {"required": ["AU4", "AU23", "AU7"], "label": "Ira Contenida"},
    "genuine_joy": {"required": ["AU6", "AU12"], "label": "Alegría Genuina (Duchenne)"},
    "sadness": {"required": ["AU1", "AU15"], "label": "Tristeza"},
    "fear": {"required": ["AU1", "AU2", "AU4", "AU5"], "label": "Miedo"},
}


class FacialExtractor:
    """Extractor facial MediaPipe + FACS con decodificadores narrativos.

    Produce FACSReading con AU scores, pose de cabeza, dirección
    de mirada y propiedades narrativas (inner_conflict, social_mask, etc.).
    """

    def __init__(self, config: CaptureConfig = DEFAULT_CONFIG):
        self.config = config
        self._face_landmarker = None
        self._au_classifier = None
        self._initialized = False

    def initialize(self) -> bool:
        """Carga MediaPipe Face Landmarker y clasificador FACS."""
        try:
            # MediaPipe Face Landmarker
            logger.info("FacialExtractor: loading MediaPipe Face Landmarker...")
            # NOTE: En producción se carga con:
            #   mp.tasks.vision.FaceLandmarker.create_from_options(...)
            # Stub mode para validar interfaz.
            self._initialized = True
            logger.info("FacialExtractor initialized (stub mode)")
            return True
        except Exception as e:
            logger.error(f"FacialExtractor init failed: {e}")
            return False

    def extract(self, frame: np.ndarray) -> FACSReading:
        """Extrae lectura FACS completa de un frame.

        Args:
            frame: Frame RGB (H, W, 3) como numpy array.

        Returns:
            FACSReading con AU scores, pose, mirada y blendshapes.
        """
        t0 = time.time()

        # Paso 1: MediaPipe — detectar landmarks faciales
        landmarks, blendshapes, head_pose = self._run_mediapipe(frame)

        # Paso 2: OpenGraphAU — clasificar AUs
        au_scores = self._run_au_classifier(frame, landmarks)

        # Paso 3: Estimar dirección de mirada
        gaze = self._estimate_gaze(landmarks)

        reading = FACSReading(
            au_scores=au_scores,
            head_pose=head_pose,
            gaze_direction=gaze,
            blendshape_scores=blendshapes,
        )

        elapsed_ms = (time.time() - t0) * 1000
        if elapsed_ms > self.config.max_extraction_latency_ms:
            logger.warning(f"Facial extraction slow: {elapsed_ms:.1f}ms")

        return reading

    def detect_narrative_patterns(self, reading: FACSReading) -> list[dict]:
        """Detecta patrones narrativos FACS activos.

        Returns:
            Lista de patrones detectados con label y confianza.
        """
        detected = []
        for pattern_key, spec in NARRATIVE_FACS_PATTERNS.items():
            required = spec["required"]
            absent = spec.get("absent", [])
            label = spec["label"]

            # Verificar que todos los AUs requeridos estén activos (>0.3)
            req_active = all(
                reading.au_scores.get(au, 0.0) > 0.3 for au in required
            )
            # Verificar que los AUs que deben estar ausentes lo estén (<0.2)
            abs_inactive = all(
                reading.au_scores.get(au, 0.0) < 0.2 for au in absent
            )

            if req_active and abs_inactive:
                confidence = min(
                    reading.au_scores.get(au, 0.0) for au in required
                )
                detected.append({
                    "pattern": pattern_key,
                    "label": label,
                    "confidence": confidence,
                    "active_aus": {au: reading.au_scores.get(au, 0.0) for au in required},
                })

        return detected

    def to_modality_vector(self, reading: FACSReading) -> ModalityVector:
        """Convierte FACSReading en vector normalizado para fusión TFN."""
        vec = []
        # AU scores en orden canónico
        for au_name in sorted(AU_DESCRIPTIONS.keys()):
            vec.append(reading.au_scores.get(au_name, 0.0))
        # Pose de cabeza
        vec.extend([
            reading.head_pose.get("pitch", 0.0) / 90.0,
            reading.head_pose.get("yaw", 0.0) / 90.0,
            reading.head_pose.get("roll", 0.0) / 90.0,
        ])
        # Mirada
        vec.extend([
            reading.gaze_direction.get("x", 0.0),
            reading.gaze_direction.get("y", 0.0),
        ])
        # Métricas narrativas derivadas
        vec.extend([
            reading.inner_conflict,
            float(reading.social_mask),
            reading.panic_shock,
            float(reading.gaze_aversion),
        ])

        # Pad/truncar a facial_dim
        target_dim = self.config.facial_dim
        if len(vec) < target_dim:
            vec.extend([0.0] * (target_dim - len(vec)))
        elif len(vec) > target_dim:
            vec = vec[:target_dim]

        # Normalizar L2
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = (np.array(vec) / norm).tolist()

        return ModalityVector(modality="facial", vector=vec)

    # ── Métodos internos (stubs para producción) ─────

    def _run_mediapipe(
        self, frame: np.ndarray
    ) -> tuple[np.ndarray, dict, dict]:
        """Ejecuta MediaPipe Face Landmarker (stub).

        Returns:
            (landmarks_478x3, blendshape_dict, head_pose_dict)
        """
        h, w = frame.shape[:2]
        n_landmarks = 478
        landmarks = np.random.uniform(0, 1, (n_landmarks, 3)).astype(np.float32)
        landmarks[:, 0] *= w
        landmarks[:, 1] *= h

        blendshapes = {
            "browDownLeft": 0.1, "browDownRight": 0.1,
            "browInnerUp": 0.2, "browOuterUpLeft": 0.05,
            "jawOpen": 0.15, "mouthSmileLeft": 0.3,
            "mouthSmileRight": 0.3, "eyeBlinkLeft": 0.05,
        }

        head_pose = {"pitch": -5.0, "yaw": 3.0, "roll": -1.0}

        return landmarks, blendshapes, head_pose

    def _run_au_classifier(
        self, frame: np.ndarray, landmarks: np.ndarray
    ) -> dict[str, float]:
        """Ejecuta clasificador FACS / OpenGraphAU (stub).

        En producción: ResNet50 backbone + clasificadores binarios por AU.
        """
        return {
            "AU1": 0.3, "AU2": 0.1, "AU4": 0.5,
            "AU5": 0.1, "AU6": 0.6, "AU7": 0.2,
            "AU9": 0.1, "AU12": 0.7, "AU14": 0.0,
            "AU15": 0.1, "AU17": 0.2, "AU20": 0.0,
            "AU23": 0.1, "AU25": 0.3, "AU26": 0.1,
            "AU45": 0.05,
        }

    def _estimate_gaze(self, landmarks: np.ndarray) -> dict[str, float]:
        """Estima dirección de mirada desde landmarks oculares (stub)."""
        return {"x": 0.05, "y": -0.02}
