"""
Orquestador del Sistema de Captura Multimodal.
===============================================
Punto de entrada principal: coordina extractores, fusión TFN,
almacenamiento vectorial FAISS y Continuity Critic.

Uso:
    from capture import CaptureOrchestrator

    orch = CaptureOrchestrator()
    orch.initialize()
    orch.load_story_bible("output/.../story_bible.json")

    # Procesar frame
    tensor = orch.process_frame(video_frame, audio_chunk)

    # Validar continuidad
    alerts = orch.validate_continuity(tensor, scene_id="scene-007")
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np

from capture.schemas import (
    ActorIdentityTensor,
    BiometricFrame,
    BTStamp,
    ContinuityAlert,
    CharacterArchetype,
    ScoresDatabaseEntry,
)
from capture.config import CaptureConfig, DEFAULT_CONFIG
from capture.extractors.kinematic import KinematicExtractor
from capture.extractors.facial import FacialExtractor
from capture.extractors.acoustic import AcousticExtractor
from capture.fusion import TensorFusionNetwork
from capture.vector_store import VectorStore
from capture.continuity import ContinuityCritic
from capture.serialization import tensor_to_jsonld, serialize_to_jsonld_string

logger = logging.getLogger(__name__)


# ============================================================
# Banco canónico de arquetipos (few-shot para Experto Concepto)
# ============================================================

CANONICAL_ARCHETYPES: list[CharacterArchetype] = [
    CharacterArchetype(
        name="Walter White", source="Breaking Bad",
        want="Recaudar dinero antes de morir de cáncer",
        need="Ser visto y respetado como figura significativa",
        flaw="Orgullo patológico herido por abandonar Gray Matter",
        arc_type="negative",
    ),
    CharacterArchetype(
        name="Lady Bird", source="Lady Bird",
        want="Escapar de Sacramento y mudarse a Nueva York",
        need="Reconocer y reciprocar el amor de su madre",
        flaw="Desprecia superficialmente lo que más necesita",
        arc_type="positive",
    ),
    CharacterArchetype(
        name="Fleabag", source="Fleabag",
        want="Entregarse al sexo y caos como evasión",
        need="Perdonarse por la muerte de Boo",
        flaw="Autosabotaje sistemático como luto perverso",
        arc_type="positive",
    ),
    CharacterArchetype(
        name="Don Draper", source="Mad Men",
        want="Proyectar imagen del publicista impecable",
        need="Reconciliar identidad manufacturada con Dick Whitman",
        flaw="Vergüenza profunda por orígenes traumáticos",
        arc_type="complex",
    ),
    CharacterArchetype(
        name="Daenerys Targaryen", source="Game of Thrones",
        want="Recuperar el Trono de Hierro",
        need="Gobernar soltando resentimiento y odio",
        flaw="Mesianismo hereditario y superioridad moral",
        arc_type="negative",
    ),
    CharacterArchetype(
        name="Cleo", source="Roma",
        want="Trabajar para cuidar a la familia patrona",
        need="Reclamar y procesar su propio dolor",
        flaw="Auto-borrado por condición social y de género",
        arc_type="positive",
    ),
]


# ============================================================
# Banco de scores cinemáticos (ADN Sonoro)
# ============================================================

SCORES_DATABASE: list[ScoresDatabaseEntry] = [
    ScoresDatabaseEntry(
        film="Joker", composer="Hildur Guðnadóttir",
        aesthetic="Drama Psicológico, Denso", tonality="C menor",
        bpm_range="55-75", mood_tags=["dark", "intimate", "descending"],
        instrumentation="Violonchelo solitario, drones electrónicos sombríos, voces susurrantes",
    ),
    ScoresDatabaseEntry(
        film="Sicario", composer="Jóhann Jóhannsson",
        aesthetic="Suspenso, Presión Amenazante", tonality="D menor",
        bpm_range="40-60", mood_tags=["dread", "tension", "subsonic"],
        instrumentation="Violonchelos graves, subgraves, percusión de latido cardíaco",
    ),
    ScoresDatabaseEntry(
        film="The Social Network", composer="Trent Reznor & Atticus Ross",
        aesthetic="Drama Corporativo", tonality="A menor",
        bpm_range="90-120", mood_tags=["cold", "calculated", "pulsing"],
        instrumentation="Sintetizadores analógicos fríos, ritmos minimalistas pulsantes",
    ),
    ScoresDatabaseEntry(
        film="Under the Skin", composer="Mica Levi",
        aesthetic="Horror de Vanguardia", tonality="Atonal",
        bpm_range="70-110", mood_tags=["alien", "friction", "fragmented"],
        instrumentation="Fricción de cuerdas, vibrato extremo, percusión arrítmica",
    ),
    ScoresDatabaseEntry(
        film="Arrival", composer="Jóhann Jóhannsson",
        aesthetic="Melancolía Reflexiva, Sci-Fi", tonality="A menor",
        bpm_range="50-70", mood_tags=["reflective", "ethereal", "melancholic"],
        instrumentation="Pianos con ataque inhibido, polifonía vocal grave, drones etéreos",
    ),
]


class CaptureOrchestrator:
    """Orquestador principal del Sistema de Captura Multimodal.

    Coordina el flujo completo:
        Frame → Extractores (paralelo) → Fusión TFN → FAISS → QA
    """

    def __init__(self, config: CaptureConfig = DEFAULT_CONFIG):
        self.config = config
        self.kinematic = KinematicExtractor(config)
        self.facial = FacialExtractor(config)
        self.acoustic = AcousticExtractor(config)
        self.fusion = TensorFusionNetwork(config)
        self.vector_store = VectorStore(config)
        self.critic = ContinuityCritic(self.vector_store, config)
        self._initialized = False
        self._story_bible = None
        self._frame_count = 0

    def initialize(self) -> bool:
        """Inicializa todos los subsistemas."""
        logger.info("Initializing Multimodal Capture System...")
        t0 = time.time()

        ok = all([
            self.kinematic.initialize(),
            self.facial.initialize(),
            self.acoustic.initialize(),
            self.fusion.initialize(),
            self.vector_store.initialize(),
        ])

        elapsed = time.time() - t0
        self._initialized = ok
        logger.info(f"Capture system {'ready' if ok else 'FAILED'} ({elapsed:.1f}s)")
        return ok

    def load_story_bible(self, path: str) -> bool:
        """Carga Story Bible y registra personajes en el Continuity Critic."""
        bible_path = Path(path)
        if not bible_path.exists():
            logger.error(f"Story Bible not found: {path}")
            return False

        with open(bible_path) as f:
            self._story_bible = json.load(f)

        # Registrar personajes
        for char in self._story_bible.get("characters", []):
            actor_id = char["name"].lower().replace(" ", "_")
            self.critic.register_character(
                actor_id=actor_id,
                character_name=char["name"],
                flaw=char.get("flaw", ""),
                want=char.get("want", ""),
                need=char.get("need", ""),
                behavioral_notes=char.get("vocal_dna", ""),
            )

        logger.info(
            f"Story Bible loaded: {len(self._story_bible.get('characters', []))} characters"
        )
        return True

    def process_frame(
        self,
        video_frame: np.ndarray,
        audio_chunk: Optional[np.ndarray] = None,
        actor_id: str = "actor_0",
        device_id: str = "cam_0",
    ) -> ActorIdentityTensor:
        """Procesa un frame completo: extracción → fusión → almacenamiento.

        Args:
            video_frame: Frame RGB (H, W, 3).
            audio_chunk: Audio mono float32 (opcional).
            actor_id: ID del actor para el tensor.
            device_id: ID del dispositivo.

        Returns:
            ActorIdentityTensor fusionado.
        """
        t0 = time.time()
        self._frame_count += 1

        # 1. Crear BTStamp
        btstamp = BTStamp(
            frame_counter=self._frame_count,
            device_id=device_id,
        )

        # 2. Extraer modalidades (en producción: paralelo via asyncio)
        skeleton = self.kinematic.extract(video_frame)
        facs = self.facial.extract(video_frame)

        vocal = None
        if audio_chunk is not None and len(audio_chunk) > 0:
            vocal = self.acoustic.extract(audio_chunk)

        # 3. Convertir a vectores de modalidad
        z_k = self.kinematic.to_modality_vector(skeleton)
        z_f = self.facial.to_modality_vector(facs)
        z_a = self.acoustic.to_modality_vector(vocal) if vocal else self._zero_acoustic()

        # 4. Fusión TFN
        tensor = self.fusion.fuse(
            z_kinematic=z_k,
            z_facial=z_f,
            z_acoustic=z_a,
            actor_id=actor_id,
            btstamp=btstamp,
        )

        # 5. Almacenar en FAISS
        self.vector_store.add(tensor)

        elapsed_ms = (time.time() - t0) * 1000
        if elapsed_ms > self.config.max_frame_latency_ms:
            logger.warning(f"Frame {self._frame_count} slow: {elapsed_ms:.1f}ms")

        return tensor

    def validate_continuity(
        self,
        tensor: ActorIdentityTensor,
        scene_id: str = "",
    ) -> list[ContinuityAlert]:
        """Valida un tensor contra el historial del personaje."""
        return self.critic.validate(tensor, scene_id)

    def get_sonic_prescription(
        self,
        tensor: ActorIdentityTensor,
    ) -> Optional[ScoresDatabaseEntry]:
        """Prescribe score cinemático basado en el estado emocional del tensor.

        Cruza emotional_valence + arousal con el banco de scores.
        """
        valence = tensor.emotional_valence
        arousal = tensor.emotional_arousal

        best_match = None
        best_score = -1.0

        for entry in SCORES_DATABASE:
            # Scoring simple por tags
            match_score = 0.0
            if valence < -0.3 and "dark" in entry.mood_tags:
                match_score += 0.4
            if valence < -0.3 and "tension" in entry.mood_tags:
                match_score += 0.3
            if arousal < 0.3 and "reflective" in entry.mood_tags:
                match_score += 0.3
            if arousal > 0.7 and "pulsing" in entry.mood_tags:
                match_score += 0.3
            if valence > 0.3 and "ethereal" in entry.mood_tags:
                match_score += 0.2

            if match_score > best_score:
                best_score = match_score
                best_match = entry

        return best_match

    def export_tensor_jsonld(
        self,
        tensor: ActorIdentityTensor,
    ) -> str:
        """Exporta tensor como JSON-LD para el Master Stack."""
        char_profile = None
        if self._story_bible:
            for char in self._story_bible.get("characters", []):
                cid = char["name"].lower().replace(" ", "_")
                if cid == tensor.actor_id:
                    char_profile = char
                    break

        doc = tensor_to_jsonld(tensor, char_profile)
        return serialize_to_jsonld_string(doc)

    def get_status(self) -> dict:
        """Estado del sistema completo."""
        return {
            "initialized": self._initialized,
            "frames_processed": self._frame_count,
            "vectors_stored": self.vector_store.size,
            "story_bible_loaded": self._story_bible is not None,
            "characters_registered": len(self.critic._character_constraints),
            "archetypes_available": len(CANONICAL_ARCHETYPES),
            "scores_database_size": len(SCORES_DATABASE),
        }

    # ── Helpers ──────────────────────────────────────

    def _zero_acoustic(self):
        """Vector acústico nulo para frames sin audio."""
        from capture.schemas import ModalityVector
        return ModalityVector(
            modality="acoustic",
            vector=[0.0] * self.config.acoustic_dim,
            confidence=0.0,
        )
