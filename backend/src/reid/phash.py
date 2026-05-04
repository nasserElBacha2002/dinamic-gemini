"""
Filtro pHash para candidatos Re-ID (Sprint 6B).

US-6B.4: filter_with_phash filtra por distancia Hamming <= max_dist entre ROIs del par.
"""

import logging
from typing import Any

import imagehash

logger = logging.getLogger(__name__)


def _roi_phashes_from_sig(sig: Any) -> list[str]:
    """Extrae lista de roi_phashes (hex) de una firma; vacía si no hay o no aplica."""
    if sig is None:
        return []
    if isinstance(sig, dict):
        phashes = sig.get("roi_phashes")
    else:
        phashes = getattr(sig, "roi_phashes", None)
    if not phashes or not isinstance(phashes, list):
        return []
    return [p for p in phashes if isinstance(p, str) and p.strip()]


def filter_with_phash(
    candidates: list[tuple[str, str]],
    signatures: dict[str, Any],
    max_dist: int = 10,
) -> list[tuple[str, str]]:
    """Filtra candidatos por distancia Hamming de pHash entre ROIs del par.

    Para cada par (track_id_a, track_id_b):
    - Si algún track_id no está en signatures o no tiene roi_phashes, se descarta el par.
    - Se convierte cada hex a imagehash.ImageHash y se calcula la distancia mínima
      entre cualquier par de hashes (track_a vs track_b).
    - Si min_dist <= max_dist el par pasa.

    Args:
        candidates: Lista de (track_id_a, track_id_b) en orden canónico.
        signatures: Dict track_id -> firma (TrackSignature o dict con roi_phashes).
        max_dist: Distancia Hamming máxima permitida (default 10).

    Returns:
        Sublista de pares que pasan el filtro, en el mismo orden que candidates.
    """
    result: list[tuple[str, str]] = []
    for tid_a, tid_b in candidates:
        try:
            if tid_a not in signatures or tid_b not in signatures:
                continue
            sig_a = signatures[tid_a]
            sig_b = signatures[tid_b]
            phashes_a = _roi_phashes_from_sig(sig_a)
            phashes_b = _roi_phashes_from_sig(sig_b)
            if not phashes_a or not phashes_b:
                continue
            hashes_a = []
            hashes_b = []
            for h in phashes_a:
                try:
                    hashes_a.append(imagehash.hex_to_hash(h))
                except (TypeError, ValueError):
                    continue
            for h in phashes_b:
                try:
                    hashes_b.append(imagehash.hex_to_hash(h))
                except (TypeError, ValueError):
                    continue
            if not hashes_a or not hashes_b:
                continue
            min_dist = min(ha - hb for ha in hashes_a for hb in hashes_b)
            if min_dist <= max_dist:
                result.append((tid_a, tid_b))
        except Exception as e:  # noqa: BLE001
            logger.debug("filter_with_phash skip pair %s: %s", (tid_a, tid_b), e)
            continue
    return result
