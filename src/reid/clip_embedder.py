"""
Verificación CLIP para pares Re-ID (Sprint 6B).

US-6B.5: interfaz estable con stub por defecto (embedder=None → []) y capa
pluggable: si se pasa embedder(path) -> List[float], se confirman pares por
similitud coseno >= min_sim. Sin dependencias GPU por defecto.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Similitud coseno entre dos vectores. Devuelve 0.0 si alguna norma es 0."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    n1 = sum(x * x for x in vec1) ** 0.5
    n2 = sum(x * x for x in vec2) ** 0.5
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    return dot / (n1 * n2)


def _roi_paths_from_sig(sig: Any) -> List[str]:
    """Extrae roi_paths de una firma (TrackSignature o dict). Lista vacía si no hay."""
    if sig is None:
        return []
    if isinstance(sig, dict):
        paths = sig.get("roi_paths")
    else:
        paths = getattr(sig, "roi_paths", None)
    if not paths or not isinstance(paths, list):
        return []
    return [p for p in paths if p is not None and isinstance(p, str) and p.strip()]


def verify_with_clip(
    candidates: List[Tuple[str, str]],
    signatures: Dict[str, Any],
    min_sim: float = 0.92,
    embedder: Optional[Callable[[str], List[float]]] = None,
) -> List[Tuple[str, str]]:
    """Confirma pares de tracks por similitud CLIP (o stub si embedder es None).

    - Si embedder es None: modo stub, devuelve [] (comportamiento seguro para CI).
    - Si embedder está definido: para cada par (a, b) se toma el primer roi_path
      de cada firma, se obtienen embeddings y se calcula similitud coseno; si
      sim >= min_sim se confirma el par.

    Args:
        candidates: Lista de (track_id_a, track_id_b) tras pHash.
        signatures: Dict track_id -> firma (TrackSignature o dict con roi_paths).
        min_sim: Similitud coseno mínima para confirmar (0..1).
        embedder: Opcional; callable path -> List[float]. Si None, stub → [].

    Returns:
        Lista de pares confirmados, en el mismo orden que candidates.
    """
    if embedder is None:
        return []

    result: List[Tuple[str, str]] = []
    for (tid_a, tid_b) in candidates:
        try:
            if tid_a not in signatures or tid_b not in signatures:
                continue
            sig_a = signatures[tid_a]
            sig_b = signatures[tid_b]
            paths_a = _roi_paths_from_sig(sig_a)
            paths_b = _roi_paths_from_sig(sig_b)
            if not paths_a or not paths_b:
                continue
            path_a = paths_a[0]
            path_b = paths_b[0]
            emb_a = embedder(path_a)
            emb_b = embedder(path_b)
            if not emb_a or not emb_b:
                continue
            sim = cosine_similarity(emb_a, emb_b)
            if sim >= min_sim:
                result.append((tid_a, tid_b))
        except Exception as e:  # noqa: BLE001
            logger.debug("verify_with_clip skip pair %s: %s", (tid_a, tid_b), e)
            continue
    return result
