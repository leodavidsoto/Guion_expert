"""
Smoke test — Sistema de Captura Multimodal.
============================================
Verifica que todos los subsistemas se inicializan y procesan
datos correctamente sin dependencias pesadas (modo stub).
"""
import sys
import json
import numpy as np

# Ensure capture package is importable
sys.path.insert(0, ".")

from capture import CaptureOrchestrator, CaptureConfig
from capture.schemas import (
    BTStamp, FACSReading, KinematicSkeleton, VocalEmbedding,
    ActorIdentityTensor, BiometricFrame, ContinuityAlert,
    CharacterArchetype, ScoresDatabaseEntry,
)
from capture.extractors import KinematicExtractor, FacialExtractor, AcousticExtractor
from capture.fusion import TensorFusionNetwork
from capture.vector_store import VectorStore
from capture.continuity import ContinuityCritic
from capture.serialization import tensor_to_jsonld, serialize_to_jsonld_string


def test_schemas():
    """Test all Pydantic schemas."""
    print("  [1/8] Schemas...", end=" ")
    stamp = BTStamp(frame_counter=1, device_id="cam_0")
    assert stamp.corrected_time > 0

    facs = FACSReading(au_scores={"AU1": 0.7, "AU4": 0.9, "AU6": 0.1, "AU12": 0.8})
    assert facs.inner_conflict > 0.5
    assert facs.social_mask is True

    skel = KinematicSkeleton(posture_openness=0.8, spatial_velocity=1.2)
    assert skel.power_imbalance_vector > 0

    vocal = VocalEmbedding(embedding_vector=[0.1]*192, syllabic_rate=4.5)
    assert vocal.embedding_dim == 192

    tensor = ActorIdentityTensor(actor_id="test", fused_tensor=[0.5]*256)
    assert len(tensor.to_embedding()) == 256

    frame = BiometricFrame(btstamp=stamp, facs=facs, skeleton=skel)
    assert "facial" in frame.available_modalities()
    assert "kinematic" in frame.available_modalities()

    arch = CharacterArchetype(
        name="Test", source="Test Film",
        want="want", need="need", flaw="flaw", arc_type="positive"
    )
    assert arch.arc_type == "positive"

    print("OK ✅")


def test_extractors():
    """Test extractors in stub mode."""
    print("  [2/8] Extractors...", end=" ")
    config = CaptureConfig()

    kine = KinematicExtractor(config)
    kine.initialize()
    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    skel = kine.extract(frame)
    assert len(skel.joints) > 0
    vec_k = kine.to_modality_vector(skel)
    assert len(vec_k.vector) == config.kinematic_dim

    face = FacialExtractor(config)
    face.initialize()
    facs = face.extract(frame)
    assert len(facs.au_scores) > 0
    patterns = face.detect_narrative_patterns(facs)
    assert isinstance(patterns, list)
    vec_f = face.to_modality_vector(facs)
    assert len(vec_f.vector) == config.facial_dim

    acou = AcousticExtractor(config)
    acou.initialize()
    audio = np.random.randn(16000).astype(np.float32) * 0.1
    vocal = acou.extract(audio)
    assert vocal.embedding_dim == 192
    vec_a = acou.to_modality_vector(vocal)
    assert len(vec_a.vector) == config.acoustic_dim

    print("OK ✅")


def test_fusion():
    """Test TFN fusion."""
    print("  [3/8] Fusion TFN...", end=" ")
    config = CaptureConfig()
    tfn = TensorFusionNetwork(config)
    tfn.initialize()

    from capture.schemas import ModalityVector
    z_k = ModalityVector(modality="kinematic", vector=[0.1]*config.kinematic_dim)
    z_f = ModalityVector(modality="facial", vector=[0.2]*config.facial_dim)
    z_a = ModalityVector(modality="acoustic", vector=[0.3]*config.acoustic_dim)

    tensor = tfn.fuse(z_k, z_f, z_a, actor_id="test_actor")
    assert tensor.fusion_dimension == config.fusion_output_dim
    assert -1.0 <= tensor.emotional_valence <= 1.0
    assert 0.0 <= tensor.sarcasm_score <= 1.0

    # Test cross-attention
    q = np.random.randn(10, 64).astype(np.float32)
    k = np.random.randn(20, 64).astype(np.float32)
    v = np.random.randn(20, 128).astype(np.float32)
    out = tfn.cross_attention(q, k, v)
    assert out.shape == (10, 128)

    print("OK ✅")


def test_vector_store():
    """Test FAISS vector store (numpy fallback)."""
    print("  [4/8] Vector Store...", end=" ")
    config = CaptureConfig()
    store = VectorStore(config)
    store.initialize()

    tensor1 = ActorIdentityTensor(
        actor_id="rust", character_name="Rust Cohle",
        fused_tensor=[0.1]*config.fusion_output_dim,
    )
    tensor2 = ActorIdentityTensor(
        actor_id="rust", character_name="Rust Cohle",
        fused_tensor=[0.12]*config.fusion_output_dim,
    )
    tensor3 = ActorIdentityTensor(
        actor_id="marty", character_name="Marty Hart",
        fused_tensor=[0.9]*config.fusion_output_dim,
    )

    store.add(tensor1)
    store.add(tensor2)
    store.add(tensor3)
    assert store.size == 3

    # Search
    results = store.search(
        np.array([0.11]*config.fusion_output_dim),
        k=2, actor_id="rust"
    )
    assert len(results) == 2
    assert results[0]["metadata"]["actor_id"] == "rust"

    # Centroid
    centroid = store.cluster_centroid("rust")
    assert centroid is not None
    assert len(centroid) == config.fusion_output_dim

    print("OK ✅")


def test_continuity():
    """Test Continuity Critic."""
    print("  [5/8] Continuity Critic...", end=" ")
    config = CaptureConfig(ooc_threshold=0.3, drift_threshold=0.15)
    store = VectorStore(config)
    store.initialize()
    critic = ContinuityCritic(store, config)

    # Register character
    critic.register_character(
        actor_id="rust", character_name="Rust Cohle",
        flaw="Nihilismo como armadura",
        behavioral_notes="Frases cortas, seco, usa silencio como amenaza"
    )

    # Add baseline tensors — consistent "nihilistic" direction
    dim = config.fusion_output_dim
    baseline_dir = np.zeros(dim, dtype=np.float32)
    baseline_dir[:dim//2] = 1.0  # Energy in first half only
    baseline_dir = baseline_dir / np.linalg.norm(baseline_dir)
    for _ in range(5):
        noise = np.random.uniform(-0.02, 0.02, dim).astype(np.float32)
        t = ActorIdentityTensor(
            actor_id="rust",
            fused_tensor=(baseline_dir + noise).tolist(),
        )
        store.add(t)

    # Test with wildly different tensor (orthogonal direction → should OOC)
    ooc_dir = np.zeros(dim, dtype=np.float32)
    ooc_dir[dim//2:] = 1.0  # Energy in SECOND half — orthogonal to baseline
    ooc_dir = ooc_dir / np.linalg.norm(ooc_dir)
    ooc_tensor = ActorIdentityTensor(
        actor_id="rust",
        fused_tensor=ooc_dir.tolist(),
        emotional_valence=0.9,
        emotional_arousal=0.9,
    )
    ooc_alerts = critic.validate(ooc_tensor, "scene-008")
    assert len(ooc_alerts) > 0, f"Expected OOC alert, got none. Distance may be below threshold."
    assert ooc_alerts[0].alert_type == "OOC"

    # Generate report
    report = critic.generate_report(ooc_alerts)
    assert "RECHAZADO" in report or "ALERTAS" in report

    print("OK ✅")


def test_serialization():
    """Test JSON-LD output."""
    print("  [6/8] JSON-LD Serialization...", end=" ")
    tensor = ActorIdentityTensor(
        actor_id="rust",
        character_name="Rust Cohle",
        emotional_valence=-0.6,
        emotional_arousal=0.3,
        sarcasm_score=0.4,
        fusion_dimension=256,
    )
    doc = tensor_to_jsonld(tensor, {
        "name": "Rust Cohle",
        "want": "Resolver el caso Dora Lange",
        "need": "Encontrar significado en un universo indiferente",
        "flaw": "Nihilismo como armadura",
        "vocal_dna": "Frases cortas. Seco. Silencio como amenaza.",
    })
    jsonld_str = serialize_to_jsonld_string(doc)
    parsed = json.loads(jsonld_str)
    assert parsed["@type"] == "Person"
    assert "performanceRole" in parsed
    assert parsed["capture:emotionalValence"] == -0.6

    print("OK ✅")


def test_orchestrator():
    """Test full orchestrator pipeline."""
    print("  [7/8] Orchestrator...", end=" ")
    orch = CaptureOrchestrator()
    assert orch.initialize()

    # Process frame
    frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    audio = np.random.randn(16000).astype(np.float32) * 0.1

    tensor = orch.process_frame(frame, audio, actor_id="test_actor")
    assert isinstance(tensor, ActorIdentityTensor)
    assert tensor.actor_id == "test_actor"
    assert len(tensor.fused_tensor) > 0

    # Process multiple frames
    for i in range(5):
        orch.process_frame(frame, audio, actor_id="test_actor")
    assert orch.vector_store.size == 6

    # Sonic prescription
    prescription = orch.get_sonic_prescription(tensor)
    assert prescription is not None

    # Export JSON-LD
    jsonld = orch.export_tensor_jsonld(tensor)
    assert "@type" in jsonld

    # Status
    status = orch.get_status()
    assert status["initialized"] is True
    assert status["frames_processed"] == 6

    print("OK ✅")


def test_archetypes_and_scores():
    """Test canonical data banks."""
    print("  [8/8] Data Banks...", end=" ")
    from capture.orchestrator import CANONICAL_ARCHETYPES, SCORES_DATABASE

    assert len(CANONICAL_ARCHETYPES) >= 6
    assert CANONICAL_ARCHETYPES[0].name == "Walter White"
    assert CANONICAL_ARCHETYPES[0].arc_type == "negative"

    assert len(SCORES_DATABASE) >= 5
    assert SCORES_DATABASE[0].film == "Joker"

    print("OK ✅")


if __name__ == "__main__":
    print("\n🎬 Smoke Test — Sistema de Captura Multimodal\n")
    test_schemas()
    test_extractors()
    test_fusion()
    test_vector_store()
    test_continuity()
    test_serialization()
    test_orchestrator()
    test_archetypes_and_scores()
    print("\n✅ All 8 tests passed — Capture system ready for integration.\n")
