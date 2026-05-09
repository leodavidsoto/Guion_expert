"""
Schemas Pydantic — Sistema de Captura Multimodal.
==================================================
Tipos centrales que fluyen entre todos los subsistemas del capture pipeline.
Diseñados para serializar como JSON-LD y alimentar la Story Bible vectorial.
"""
from __future__ import annotations

import time
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ============================================================
# BTStamp — Sello de Bloque y Tiempo Aumentado
# ============================================================

class BTStamp(BaseModel):
    """Sello temporal sincronizado NTP para cada paquete multimodal.

    Combina un contador incremental de la cámara con el reloj local
    estrictamente sincronizado a un servidor NTP central. Garantiza
    alineación sub-frame entre modalidades.
    """
    frame_counter: int = Field(ge=0, description="Contador incremental del dispositivo de captura.")
    timestamp_unix: float = Field(
        default_factory=time.time,
        description="Unix timestamp sincronizado NTP (seconds.microseconds).",
    )
    device_id: str = Field(default="cam_0", description="ID del dispositivo origen.")
    ntp_offset_ms: float = Field(
        default=0.0,
        description="Offset NTP medido en ms respecto al servidor central.",
    )

    @property
    def corrected_time(self) -> float:
        """Timestamp corregido por el offset NTP."""
        return self.timestamp_unix - (self.ntp_offset_ms / 1000.0)


# ============================================================
# FACS — Facial Action Coding System
# ============================================================

class FACSReading(BaseModel):
    """Lectura FACS de un fotograma facial.

    Mapea Unidades de Acción (AU) a intensidades 0.0-1.0 y las
    traduce a estados emocionales narrativos para el pipeline.
    """
    au_scores: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Diccionario AU → intensidad (0.0-1.0). "
            "Ej: {'AU1': 0.7, 'AU4': 0.9, 'AU6': 0.1, 'AU12': 0.8}."
        ),
    )
    head_pose: dict[str, float] = Field(
        default_factory=lambda: {"pitch": 0.0, "yaw": 0.0, "roll": 0.0},
        description="Pose de cabeza en grados (Procrustes Analysis).",
    )
    gaze_direction: dict[str, float] = Field(
        default_factory=lambda: {"x": 0.0, "y": 0.0},
        description="Dirección de mirada normalizada (-1 a 1).",
    )
    blendshape_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Coeficientes de formas combinadas de MediaPipe.",
    )

    # ── Decodificadores narrativos ──────────────────────────

    @property
    def inner_conflict(self) -> float:
        """AU1 + AU4 co-activación → aflicción emocional profunda."""
        return min(
            self.au_scores.get("AU1", 0.0) * self.au_scores.get("AU4", 0.0) * 2.0,
            1.0,
        )

    @property
    def social_mask(self) -> bool:
        """Sonrisa de Pan Am: AU12 sin AU6 → cortesía obligada / falsedad."""
        au12 = self.au_scores.get("AU12", 0.0)
        au6 = self.au_scores.get("AU6", 0.0)
        return au12 > 0.5 and au6 < 0.2

    @property
    def panic_shock(self) -> float:
        """AU5 + AU26 → pánico y shock."""
        return min(
            self.au_scores.get("AU5", 0.0) * self.au_scores.get("AU26", 0.0) * 2.0,
            1.0,
        )

    @property
    def gaze_aversion(self) -> bool:
        """Evitación de contacto visual (indicador de mentira o sumisión)."""
        return abs(self.gaze_direction.get("x", 0.0)) > 0.3


# ============================================================
# Cinemática Estructural — MotionBERT skeleton
# ============================================================

class Joint3D(BaseModel):
    """Articulación 3D con coordenadas y confianza."""
    name: str
    x: float
    y: float
    z: float
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class KinematicSkeleton(BaseModel):
    """Esqueleto 3D completo de MotionBERT (DSTformer).

    Proyecta coordenadas 3D de alta precisión a partir de
    estimación 2D (AlphaPose/Halpe) + inferencia de profundidad Z.
    """
    joints: list[Joint3D] = Field(default_factory=list)
    proxemic_radius: float = Field(
        default=0.0,
        ge=0.0,
        description="Radio proxémico estimado en metros.",
    )
    posture_openness: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Apertura postural: 0=cerrado/defensivo, 1=expansivo/dominante.",
    )
    spatial_velocity: float = Field(
        default=0.0,
        ge=0.0,
        description="Velocidad espacial del centro de masa (m/s).",
    )

    @property
    def power_imbalance_vector(self) -> float:
        """Indicador de desequilibrio de poder basado en postura + movimiento."""
        return self.posture_openness * (1.0 + self.spatial_velocity * 0.5)


# ============================================================
# Identidad Acústica — ECAPA-TDNN
# ============================================================

class VocalEmbedding(BaseModel):
    """Vector de identidad vocal extraído por ECAPA-TDNN.

    Vector de longitud fija que aísla las características del
    hablante independientemente de las palabras pronunciadas.
    EER: 1.71% en verificación biométrica profunda.
    """
    speaker_id: str = Field(default="", description="ID asignado al hablante.")
    embedding_dim: int = Field(default=192, description="Dimensionalidad del embedding.")
    embedding_vector: list[float] = Field(
        default_factory=list,
        description="Vector ECAPA-TDNN de longitud fija.",
    )
    # Métricas Sorkin Dialogue-as-Music
    syllabic_rate: float = Field(default=0.0, ge=0.0, description="Sílabas por segundo.")
    pitch_mean_hz: float = Field(default=0.0, ge=0.0, description="Tono medio en Hz.")
    pitch_variance: float = Field(default=0.0, ge=0.0, description="Varianza de pitch.")
    volume_db: float = Field(default=0.0, description="Volumen RMS en dB.")
    overlap_ratio: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Ratio de diálogo superpuesto (overlapping dialogue).",
    )
    pause_anomaly_score: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Score de anomalía en pausas (non-sequitur detection).",
    )


# ============================================================
# ModalityVector — Representación por modalidad
# ============================================================

class ModalityVector(BaseModel):
    """Vector normalizado de una sola modalidad, listo para fusión tensorial."""
    modality: Literal["kinematic", "facial", "acoustic", "linguistic"] = Field(
        description="Tipo de modalidad.",
    )
    vector: list[float] = Field(description="Vector de representación normalizado.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    timestamp: float = Field(default_factory=time.time)


# ============================================================
# Actor Identity Tensor — Resultado de fusión multimodal
# ============================================================

class ActorIdentityTensor(BaseModel):
    """Tensor de Identidad del Actor — resultado de la fusión TFN.

    Disocia la dinámica de movimiento inherente (la acción realizada)
    de la identidad del sujeto (contenido fenotípico y vocal).

    Punto consolidado en el espacio latente que contiene:
    - Agrupaciones unimodales aisladas
    - Todas las combinaciones bimodales
    - El espectro trimodal completo
    """
    actor_id: str = Field(description="ID canónico del actor/personaje.")
    character_name: str = Field(default="", description="Nombre del personaje si mapeado.")

    # Vectores de modalidad fusionados
    kinematic_vector: list[float] = Field(default_factory=list)
    facial_vector: list[float] = Field(default_factory=list)
    acoustic_vector: list[float] = Field(default_factory=list)
    linguistic_vector: list[float] = Field(default_factory=list)

    # Tensor fusionado (producto exterior TFN)
    fused_tensor: list[float] = Field(
        default_factory=list,
        description="Tensor fusionado hiper-dimensional del producto exterior TFN.",
    )
    fusion_dimension: int = Field(default=0, description="Dimensionalidad del tensor fusionado.")

    # Métricas narrativas derivadas
    emotional_valence: float = Field(
        default=0.0, ge=-1.0, le=1.0,
        description="Valencia emocional: -1=negativa, 0=neutra, 1=positiva.",
    )
    emotional_arousal: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Arousal: 0=calma, 1=máxima activación.",
    )
    sarcasm_score: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Score de sarcasmo: fricción entre z_a positivo y z_v negativo.",
    )
    deception_score: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Score de engaño: inconsistencia inter-modal.",
    )

    # Timestamp
    btstamp: Optional[BTStamp] = None

    def to_embedding(self) -> list[float]:
        """Serializa el tensor para indexación FAISS."""
        if self.fused_tensor:
            return self.fused_tensor
        # Fallback: concatenar vectores de modalidad
        return self.kinematic_vector + self.facial_vector + self.acoustic_vector


# ============================================================
# BiometricFrame — Snapshot multimodal de un instante
# ============================================================

class BiometricFrame(BaseModel):
    """Snapshot multimodal de un instante temporal exacto.

    Agrupa la lectura FACS, el esqueleto cinemático y el embedding
    vocal sincronizados por un mismo BTStamp.
    """
    btstamp: BTStamp
    facs: Optional[FACSReading] = None
    skeleton: Optional[KinematicSkeleton] = None
    vocal: Optional[VocalEmbedding] = None

    # Metadatos del frame de video
    frame_width: int = Field(default=1920)
    frame_height: int = Field(default=1080)
    fps: float = Field(default=24.0)

    def available_modalities(self) -> list[str]:
        """Lista las modalidades disponibles en este frame."""
        mods = []
        if self.facs:
            mods.append("facial")
        if self.skeleton:
            mods.append("kinematic")
        if self.vocal:
            mods.append("acoustic")
        return mods


# ============================================================
# ContinuityAlert — Alerta del Continuity Critic
# ============================================================

class ContinuityAlert(BaseModel):
    """Alerta OOC (Out-Of-Character) emitida por el Continuity Critic.

    Se genera cuando la distancia cosenoidal entre un nuevo vector de
    acción y el clúster histórico del Actor Identity Tensor excede
    el umbral de tolerancia.
    """
    alert_type: Literal["OOC", "DRIFT", "INCONSISTENCY", "TEMPORAL_BREAK"] = Field(
        description="Tipo de alerta de continuidad.",
    )
    severity: Literal["low", "medium", "high", "critical"] = Field(
        default="medium",
        description="Severidad de la alerta.",
    )
    character_name: str = Field(description="Personaje afectado.")
    scene_id: str = Field(default="", description="ID de escena donde se detecta.")
    cosine_distance: float = Field(
        default=0.0, ge=0.0, le=2.0,
        description="Distancia cosenoidal respecto al clúster histórico.",
    )
    expected_behavior: str = Field(default="", description="Comportamiento esperado según Story Bible.")
    detected_behavior: str = Field(default="", description="Comportamiento detectado.")
    recommendation: str = Field(default="", description="Corrección sugerida.")


# ============================================================
# Character Want/Need/Flaw — Matriz canónica (Experto 2)
# ============================================================

class CharacterArchetype(BaseModel):
    """Entrada de la matriz Want/Need/Flaw para razonamiento por analogía.

    30 protagonistas canónicos pre-cargados para few-shot del Experto Concepto.
    """
    name: str = Field(description="Nombre del personaje.")
    source: str = Field(description="Película/serie de origen.")
    want: str = Field(description="Objetivo externo consciente.")
    need: str = Field(description="Necesidad interna inconsciente.")
    flaw: str = Field(description="Herida/defecto fatal.")
    arc_type: Literal[
        "positive", "negative", "complex", "static", "disillusionment", "corruption"
    ] = Field(description="Tipo de arco de transformación.")


# ============================================================
# ScoresDatabaseEntry — Banco de composiciones cinemáticas
# ============================================================

class ScoresDatabaseEntry(BaseModel):
    """Entrada del banco de composiciones cinemáticas para ADN Sonoro.

    Parametriza género, BPM y orquestación para generar Leitmotiv
    determinista inyectable en Suno Audio.
    """
    film: str
    composer: str
    aesthetic: str
    tonality: str
    bpm_range: str
    instrumentation: str
    mood_tags: list[str] = Field(default_factory=list)
