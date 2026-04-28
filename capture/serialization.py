"""
Serialización JSON-LD — Salida ontológica del sistema de captura.
=================================================================
Traduce ActorIdentityTensor y BiometricFrame a JSON-LD con
esquemas Schema.org (Person, PerformanceRole) para
interoperabilidad con el Master Stack y motores generativos.
"""
from __future__ import annotations

import json
from typing import Optional

from capture.schemas import (
    ActorIdentityTensor,
    BiometricFrame,
    CharacterArchetype,
    ScoresDatabaseEntry,
)


# ============================================================
# Contexto JSON-LD base
# ============================================================

JSONLD_CONTEXT = {
    "@context": {
        "@vocab": "https://schema.org/",
        "capture": "https://guion-expert.dev/capture/",
        "facs": "https://guion-expert.dev/capture/facs/",
        "kinematic": "https://guion-expert.dev/capture/kinematic/",
        "acoustic": "https://guion-expert.dev/capture/acoustic/",
        "fusion": "https://guion-expert.dev/capture/fusion/",
    }
}


def tensor_to_jsonld(
    tensor: ActorIdentityTensor,
    character_profile: Optional[dict] = None,
) -> dict:
    """Serializa ActorIdentityTensor como JSON-LD Schema.org Person.

    Args:
        tensor: Tensor de identidad del actor.
        character_profile: Perfil del personaje del Story Bible (opcional).

    Returns:
        Diccionario JSON-LD compatible con Schema.org.
    """
    doc = {
        **JSONLD_CONTEXT,
        "@type": "Person",
        "@id": f"capture:actor/{tensor.actor_id}",
        "name": tensor.character_name or tensor.actor_id,
        "capture:actorId": tensor.actor_id,

        # Métricas narrativas derivadas de la fusión
        "capture:emotionalValence": tensor.emotional_valence,
        "capture:emotionalArousal": tensor.emotional_arousal,
        "capture:sarcasmScore": tensor.sarcasm_score,
        "capture:deceptionScore": tensor.deception_score,

        # Dimensionalidad del tensor
        "capture:fusionDimension": tensor.fusion_dimension,

        # Timestamp
        "capture:captureTimestamp": (
            tensor.btstamp.corrected_time if tensor.btstamp else None
        ),
    }

    # Agregar performanceRole si hay perfil de personaje
    if character_profile:
        doc["performanceRole"] = {
            "@type": "PerformanceRole",
            "characterName": character_profile.get("name", ""),
            "capture:want": character_profile.get("want", ""),
            "capture:need": character_profile.get("need", ""),
            "capture:flaw": character_profile.get("flaw", ""),
            "capture:vocalDna": character_profile.get("vocal_dna", ""),
            "capture:arcState": character_profile.get("arc_state", "in_progress"),
        }

    return doc


def frame_to_jsonld(frame: BiometricFrame) -> dict:
    """Serializa BiometricFrame como JSON-LD."""
    doc = {
        **JSONLD_CONTEXT,
        "@type": "capture:BiometricFrame",
        "capture:frameCounter": frame.btstamp.frame_counter,
        "capture:timestamp": frame.btstamp.corrected_time,
        "capture:deviceId": frame.btstamp.device_id,
        "capture:resolution": f"{frame.frame_width}x{frame.frame_height}",
        "capture:fps": frame.fps,
        "capture:modalities": frame.available_modalities(),
    }

    if frame.facs:
        doc["facs:reading"] = {
            "@type": "facs:FACSReading",
            "facs:auScores": frame.facs.au_scores,
            "facs:headPose": frame.facs.head_pose,
            "facs:gazeDirection": frame.facs.gaze_direction,
            "facs:innerConflict": frame.facs.inner_conflict,
            "facs:socialMask": frame.facs.social_mask,
            "facs:panicShock": frame.facs.panic_shock,
        }

    if frame.skeleton:
        doc["kinematic:skeleton"] = {
            "@type": "kinematic:Skeleton3D",
            "kinematic:jointCount": len(frame.skeleton.joints),
            "kinematic:proxemicRadius": frame.skeleton.proxemic_radius,
            "kinematic:postureOpenness": frame.skeleton.posture_openness,
            "kinematic:spatialVelocity": frame.skeleton.spatial_velocity,
        }

    if frame.vocal:
        doc["acoustic:vocal"] = {
            "@type": "acoustic:VocalEmbedding",
            "acoustic:speakerId": frame.vocal.speaker_id,
            "acoustic:syllabicRate": frame.vocal.syllabic_rate,
            "acoustic:pitchMeanHz": frame.vocal.pitch_mean_hz,
            "acoustic:volumeDb": frame.vocal.volume_db,
            "acoustic:overlapRatio": frame.vocal.overlap_ratio,
        }

    return doc


def archetype_to_jsonld(arch: CharacterArchetype) -> dict:
    """Serializa un arquetipo de personaje como JSON-LD."""
    return {
        **JSONLD_CONTEXT,
        "@type": "capture:CharacterArchetype",
        "name": arch.name,
        "capture:source": arch.source,
        "capture:want": arch.want,
        "capture:need": arch.need,
        "capture:flaw": arch.flaw,
        "capture:arcType": arch.arc_type,
    }


def score_entry_to_jsonld(entry: ScoresDatabaseEntry) -> dict:
    """Serializa entrada del banco de scores cinemáticos como JSON-LD."""
    return {
        **JSONLD_CONTEXT,
        "@type": "MusicComposition",
        "name": f"{entry.film} Score",
        "composer": {"@type": "Person", "name": entry.composer},
        "capture:film": entry.film,
        "capture:aesthetic": entry.aesthetic,
        "capture:tonality": entry.tonality,
        "capture:bpmRange": entry.bpm_range,
        "capture:instrumentation": entry.instrumentation,
        "capture:moodTags": entry.mood_tags,
    }


def serialize_to_jsonld_string(doc: dict, indent: int = 2) -> str:
    """Serializa un documento JSON-LD a string."""
    return json.dumps(doc, indent=indent, ensure_ascii=False, default=str)
