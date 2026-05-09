"""
Vector Store — FAISS HNSW para Story Bible vectorial.
=====================================================
Almacena Actor Identity Tensors como embeddings y permite
búsqueda ANN (Approximate Nearest Neighbors) para el
Continuity Critic y la recuperación semántica.

Indexación: HNSW (Hierarchical Navigable Small World graphs)
Métricas: Distancia cosenoidal / L2 / Inner Product.

Requiere: numpy (faiss-cpu/faiss-gpu opcional)
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np

from capture.schemas import ActorIdentityTensor, ContinuityAlert
from capture.config import CaptureConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


class VectorStore:
    """Base de datos vectorial FAISS para el Story Bible.

    Almacena embeddings de ActorIdentityTensor indexados por personaje.
    Soporta HNSW, IVF y Flat según configuración.
    Si FAISS no está disponible, usa búsqueda bruta con numpy.
    """

    def __init__(self, config: CaptureConfig = DEFAULT_CONFIG):
        self.config = config
        self._index = None
        self._faiss_available = False
        self._vectors: list[np.ndarray] = []
        self._metadata: list[dict] = []
        self._dimension: int = config.fusion_output_dim
        self._initialized = False

    def initialize(self) -> bool:
        """Inicializa el índice FAISS o fallback numpy."""
        try:
            import faiss
            self._faiss_available = True
            self._index = self._create_faiss_index(faiss)
            logger.info(
                f"VectorStore: FAISS {self.config.faiss_index_type} "
                f"(dim={self._dimension})"
            )
        except ImportError:
            logger.warning("FAISS not available — using numpy brute-force")
            self._faiss_available = False

        self._initialized = True
        return True

    def add(
        self,
        tensor: ActorIdentityTensor,
        metadata: Optional[dict] = None,
    ) -> int:
        """Añade un tensor al índice.

        Returns:
            Índice (position) del vector añadido.
        """
        embedding = np.array(tensor.to_embedding(), dtype=np.float32)
        if len(embedding) != self._dimension:
            # Pad o truncar
            if len(embedding) < self._dimension:
                embedding = np.pad(embedding, (0, self._dimension - len(embedding)))
            else:
                embedding = embedding[:self._dimension]

        # Normalizar para cosine
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        idx = len(self._vectors)
        self._vectors.append(embedding)
        self._metadata.append({
            "idx": idx,
            "actor_id": tensor.actor_id,
            "character_name": tensor.character_name,
            "emotional_valence": tensor.emotional_valence,
            "emotional_arousal": tensor.emotional_arousal,
            "sarcasm_score": tensor.sarcasm_score,
            "timestamp": tensor.btstamp.timestamp_unix if tensor.btstamp else time.time(),
            **(metadata or {}),
        })

        if self._faiss_available and self._index is not None:
            import faiss
            self._index.add(embedding.reshape(1, -1))

        return idx

    def search(
        self,
        query_embedding: np.ndarray,
        k: int = 5,
        actor_id: Optional[str] = None,
    ) -> list[dict]:
        """Busca los k vecinos más cercanos.

        Args:
            query_embedding: Vector de consulta.
            k: Número de vecinos.
            actor_id: Opcional — filtrar por personaje.

        Returns:
            Lista de dicts con {idx, distance, metadata}.
        """
        if len(self._vectors) == 0:
            return []

        query = np.array(query_embedding, dtype=np.float32)
        if len(query) != self._dimension:
            if len(query) < self._dimension:
                query = np.pad(query, (0, self._dimension - len(query)))
            else:
                query = query[:self._dimension]

        norm = np.linalg.norm(query)
        if norm > 0:
            query = query / norm

        if self._faiss_available and self._index is not None:
            return self._search_faiss(query, k, actor_id)
        return self._search_numpy(query, k, actor_id)

    def cosine_distance(self, v1: np.ndarray, v2: np.ndarray) -> float:
        """Distancia cosenoidal entre dos vectores."""
        n1 = np.linalg.norm(v1)
        n2 = np.linalg.norm(v2)
        if n1 == 0 or n2 == 0:
            return 1.0
        sim = float(np.dot(v1, v2) / (n1 * n2))
        return 1.0 - sim

    def get_character_cluster(self, actor_id: str) -> list[np.ndarray]:
        """Obtiene todos los vectores históricos de un personaje."""
        return [
            self._vectors[m["idx"]]
            for m in self._metadata
            if m.get("actor_id") == actor_id
        ]

    def cluster_centroid(self, actor_id: str) -> Optional[np.ndarray]:
        """Calcula el centroide del clúster de un personaje."""
        vecs = self.get_character_cluster(actor_id)
        if not vecs:
            return None
        centroid = np.mean(vecs, axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 0:
            centroid = centroid / norm
        return centroid

    def save(self, path: Optional[str] = None) -> None:
        """Persiste el índice y metadatos a disco."""
        save_path = Path(path or self.config.vector_store_path or "capture_vectors")
        save_path.mkdir(parents=True, exist_ok=True)

        # Guardar vectores
        if self._vectors:
            np.save(save_path / "vectors.npy", np.array(self._vectors))
        # Guardar metadatos
        with open(save_path / "metadata.json", "w") as f:
            json.dump(self._metadata, f, indent=2, default=str)
        # Guardar índice FAISS
        if self._faiss_available and self._index is not None:
            import faiss
            faiss.write_index(self._index, str(save_path / "faiss.index"))

        logger.info(f"VectorStore saved: {len(self._vectors)} vectors → {save_path}")

    def load(self, path: Optional[str] = None) -> bool:
        """Carga el índice desde disco."""
        load_path = Path(path or self.config.vector_store_path or "capture_vectors")
        if not load_path.exists():
            return False

        vecs_path = load_path / "vectors.npy"
        meta_path = load_path / "metadata.json"

        if vecs_path.exists():
            self._vectors = list(np.load(vecs_path))
        if meta_path.exists():
            with open(meta_path) as f:
                self._metadata = json.load(f)

        # Reconstruir índice FAISS
        faiss_path = load_path / "faiss.index"
        if self._faiss_available and faiss_path.exists():
            import faiss
            self._index = faiss.read_index(str(faiss_path))
        elif self._faiss_available and self._vectors:
            import faiss
            self._index = self._create_faiss_index(faiss)
            vecs_array = np.array(self._vectors, dtype=np.float32)
            self._index.add(vecs_array)

        logger.info(f"VectorStore loaded: {len(self._vectors)} vectors")
        return True

    @property
    def size(self) -> int:
        return len(self._vectors)

    # ── Internos ─────────────────────────────────────

    def _create_faiss_index(self, faiss):
        """Crea el índice FAISS según configuración."""
        d = self._dimension
        idx_type = self.config.faiss_index_type.upper()

        if idx_type.startswith("HNSW"):
            m = int(idx_type.replace("HNSW", "") or "32")
            index = faiss.IndexHNSWFlat(d, m)
            index.hnsw.efConstruction = self.config.faiss_ef_construction
            index.hnsw.efSearch = self.config.faiss_ef_search
        elif idx_type.startswith("IVF"):
            nlist = int(idx_type.replace("IVF", "") or "256")
            quantizer = faiss.IndexFlatIP(d)
            index = faiss.IndexIVFFlat(quantizer, d, nlist)
        else:
            index = faiss.IndexFlatIP(d)

        return index

    def _search_faiss(
        self, query: np.ndarray, k: int, actor_id: Optional[str]
    ) -> list[dict]:
        """Búsqueda con FAISS."""
        import faiss
        k_search = min(k * 3 if actor_id else k, len(self._vectors))
        distances, indices = self._index.search(query.reshape(1, -1), k_search)

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self._metadata):
                continue
            meta = self._metadata[idx]
            if actor_id and meta.get("actor_id") != actor_id:
                continue
            results.append({
                "idx": int(idx),
                "distance": float(1.0 - dist),  # IP → cosine dist
                "metadata": meta,
            })
            if len(results) >= k:
                break
        return results

    def _search_numpy(
        self, query: np.ndarray, k: int, actor_id: Optional[str]
    ) -> list[dict]:
        """Búsqueda bruta con numpy (fallback sin FAISS)."""
        if not self._vectors:
            return []

        candidates = []
        for i, vec in enumerate(self._vectors):
            meta = self._metadata[i]
            if actor_id and meta.get("actor_id") != actor_id:
                continue
            dist = self.cosine_distance(query, vec)
            candidates.append({"idx": i, "distance": dist, "metadata": meta})

        candidates.sort(key=lambda x: x["distance"])
        return candidates[:k]
