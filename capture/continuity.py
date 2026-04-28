"""
Continuity Critic — QA vectorial biométrico.
=============================================
Valida vectores conductuales planificados contra el clúster
histórico del Actor Identity Tensor en FAISS.

Emite alertas OOC (Out-Of-Character) cuando la distancia
cosenoidal excede el umbral de tolerancia.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from capture.schemas import ActorIdentityTensor, ContinuityAlert
from capture.vector_store import VectorStore
from capture.config import CaptureConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


class ContinuityCritic:
    """Auditor vectorial de continuidad de personajes.

    Usa el clúster histórico del Actor Identity Tensor en FAISS
    para validar que nuevas acciones/expresiones sean coherentes
    con el perfil establecido del personaje.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        config: CaptureConfig = DEFAULT_CONFIG,
    ):
        self.store = vector_store
        self.config = config
        # Perfiles de personaje (Want/Need/Flaw → restricciones vectoriales)
        self._character_constraints: dict[str, dict] = {}

    def register_character(
        self,
        actor_id: str,
        character_name: str,
        flaw: str = "",
        want: str = "",
        need: str = "",
        behavioral_notes: str = "",
    ) -> None:
        """Registra restricciones narrativas de un personaje.

        Estas restricciones se usan para contextualizar las alertas OOC.
        """
        self._character_constraints[actor_id] = {
            "character_name": character_name,
            "flaw": flaw,
            "want": want,
            "need": need,
            "behavioral_notes": behavioral_notes,
        }

    def validate(
        self,
        tensor: ActorIdentityTensor,
        scene_id: str = "",
    ) -> list[ContinuityAlert]:
        """Valida un nuevo tensor contra el historial del personaje.

        Returns:
            Lista de alertas (vacía si todo OK).
        """
        alerts = []
        actor_id = tensor.actor_id

        # Obtener centroide del personaje
        centroid = self.store.cluster_centroid(actor_id)
        if centroid is None:
            # No hay historial — primera aparición, no se puede validar
            logger.debug(f"No history for {actor_id} — skipping validation")
            return alerts

        # Calcular distancia cosenoidal
        embedding = np.array(tensor.to_embedding(), dtype=np.float32)
        if len(embedding) < len(centroid):
            embedding = np.pad(embedding, (0, len(centroid) - len(embedding)))
        elif len(embedding) > len(centroid):
            embedding = embedding[:len(centroid)]

        distance = self.store.cosine_distance(embedding, centroid)
        constraints = self._character_constraints.get(actor_id, {})
        char_name = constraints.get("character_name", actor_id)

        # Check OOC (Out-Of-Character)
        if distance > self.config.ooc_threshold:
            severity = "critical" if distance > 0.6 else "high"
            alert = ContinuityAlert(
                alert_type="OOC",
                severity=severity,
                character_name=char_name,
                scene_id=scene_id,
                cosine_distance=distance,
                expected_behavior=self._describe_expected(actor_id, centroid),
                detected_behavior=self._describe_detected(tensor),
                recommendation=self._suggest_correction(actor_id, tensor, distance),
            )
            alerts.append(alert)
            logger.warning(
                f"OOC alert: {char_name} in {scene_id} "
                f"(distance={distance:.3f}, threshold={self.config.ooc_threshold})"
            )

        # Check drift gradual
        elif distance > self.config.drift_threshold:
            alert = ContinuityAlert(
                alert_type="DRIFT",
                severity="medium",
                character_name=char_name,
                scene_id=scene_id,
                cosine_distance=distance,
                expected_behavior=self._describe_expected(actor_id, centroid),
                detected_behavior=self._describe_detected(tensor),
                recommendation=(
                    f"Drift gradual detectado para {char_name}. "
                    f"El personaje se está alejando de su baseline. "
                    f"Verificar coherencia con Flaw: {constraints.get('flaw', 'N/A')}."
                ),
            )
            alerts.append(alert)

        # Check inconsistencia emocional inter-modal
        if tensor.deception_score > 0.7:
            alert = ContinuityAlert(
                alert_type="INCONSISTENCY",
                severity="low",
                character_name=char_name,
                scene_id=scene_id,
                cosine_distance=distance,
                expected_behavior="Coherencia inter-modal esperada",
                detected_behavior=(
                    f"Deception score alto ({tensor.deception_score:.2f}): "
                    f"inconsistencia entre modalidades kinematic/facial/acoustic."
                ),
                recommendation="Verificar si la inconsistencia es intencional (subtexto/sarcasmo).",
            )
            alerts.append(alert)

        return alerts

    def validate_batch(
        self,
        tensors: list[ActorIdentityTensor],
        scene_ids: Optional[list[str]] = None,
    ) -> list[ContinuityAlert]:
        """Valida un batch de tensores (ej. todas las escenas de un guion)."""
        all_alerts = []
        for i, tensor in enumerate(tensors):
            sid = scene_ids[i] if scene_ids and i < len(scene_ids) else f"scene-{i:03d}"
            alerts = self.validate(tensor, scene_id=sid)
            all_alerts.extend(alerts)
        return all_alerts

    def generate_report(self, alerts: list[ContinuityAlert]) -> str:
        """Genera reporte de continuidad legible."""
        if not alerts:
            return "QA_STATUS: APROBADO\nSCORE_GLOBAL: 1.00\nNo se detectaron problemas de continuidad."

        lines = [
            "QA_STATUS: RECHAZADO" if any(a.severity in ("critical", "high") for a in alerts) else "QA_STATUS: APROBADO_CON_ALERTAS",
        ]

        # Score basado en alertas
        penalty = sum(
            {"critical": 0.3, "high": 0.2, "medium": 0.1, "low": 0.05}.get(a.severity, 0)
            for a in alerts
        )
        score = max(0.0, 1.0 - penalty)
        lines.append(f"SCORE_GLOBAL: {score:.2f}")
        lines.append(f"ALERTAS_TOTAL: {len(alerts)}")
        lines.append("")

        for i, alert in enumerate(alerts, 1):
            lines.append(f"ALERTA_{i}:")
            lines.append(f"  Tipo: {alert.alert_type}")
            lines.append(f"  Severidad: {alert.severity}")
            lines.append(f"  Personaje: {alert.character_name}")
            lines.append(f"  Escena: {alert.scene_id}")
            lines.append(f"  Distancia coseno: {alert.cosine_distance:.3f}")
            lines.append(f"  Esperado: {alert.expected_behavior}")
            lines.append(f"  Detectado: {alert.detected_behavior}")
            lines.append(f"  Corrección: {alert.recommendation}")
            lines.append("")

        return "\n".join(lines)

    # ── Helpers descriptivos ─────────────────────────

    def _describe_expected(self, actor_id: str, centroid: np.ndarray) -> str:
        """Describe el comportamiento esperado basado en el clúster."""
        constraints = self._character_constraints.get(actor_id, {})
        flaw = constraints.get("flaw", "N/A")
        notes = constraints.get("behavioral_notes", "")
        return f"Baseline del personaje (Flaw: {flaw}). {notes}".strip()

    def _describe_detected(self, tensor: ActorIdentityTensor) -> str:
        """Describe el comportamiento detectado en el tensor."""
        parts = [f"Valence={tensor.emotional_valence:.2f}"]
        parts.append(f"Arousal={tensor.emotional_arousal:.2f}")
        if tensor.sarcasm_score > 0.3:
            parts.append(f"Sarcasm={tensor.sarcasm_score:.2f}")
        if tensor.deception_score > 0.3:
            parts.append(f"Deception={tensor.deception_score:.2f}")
        return ", ".join(parts)

    def _suggest_correction(
        self, actor_id: str, tensor: ActorIdentityTensor, distance: float
    ) -> str:
        """Sugiere corrección basada en la distancia y el perfil."""
        constraints = self._character_constraints.get(actor_id, {})
        char_name = constraints.get("character_name", actor_id)
        flaw = constraints.get("flaw", "desconocido")

        if distance > 0.6:
            return (
                f"CRÍTICO: {char_name} está actuando completamente fuera de carácter. "
                f"Recalibrar al Dialoguista (Experto 5) y Director Flow (Experto 7). "
                f"Recordar Flaw: '{flaw}'."
            )
        return (
            f"{char_name} muestra desviación significativa (dist={distance:.3f}). "
            f"El Dialoguista debe anclar al vocal_dna del Story Bible."
        )
