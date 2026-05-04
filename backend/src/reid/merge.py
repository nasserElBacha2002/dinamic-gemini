"""
Merge de tracks por Union-Find (DSU) para Re-ID (Sprint 6B).

US-6B.6: DSU sobre track_ids, componentes fusionados con observaciones
concatenadas, ordenadas por frame_idx/bbox y deduplicadas por (frame_idx, bbox).
Track_id del merged = mínimo del componente; salida ordenada determinista.
"""

from src.models.schemas import PalletObservation, PalletTrack


def _dsu_find(parent: dict[str, str], x: str) -> str:
    """Find con path compression. Retorna el representante (root) del componente."""
    if parent[x] != x:
        parent[x] = _dsu_find(parent, parent[x])
    return parent[x]


def _dsu_union(parent: dict[str, str], x: str, y: str) -> None:
    """Union por rank implícito: el menor track_id siempre es el root."""
    rx = _dsu_find(parent, x)
    ry = _dsu_find(parent, y)
    if rx == ry:
        return
    # Hacer que el menor id sea la raíz (determinismo)
    if rx < ry:
        parent[ry] = rx
    else:
        parent[rx] = ry


def _obs_key(o: PalletObservation) -> tuple[int, tuple[int, int, int, int]]:
    """Clave para deduplicación: (frame_idx, bbox)."""
    return (o.frame_idx, o.bbox)


def _merge_observations(
    observations: list[PalletObservation],
    merged_track_id: str,
) -> list[PalletObservation]:
    """Concatena, deduplica por (frame_idx, bbox) y ordena. Prefiere obs con roi_path y blur_score."""
    if not observations:
        return []
    # Agrupar por clave (frame_idx, bbox)
    by_key: dict[tuple[int, tuple[int, int, int, int]], list[PalletObservation]] = {}
    for o in observations:
        k = _obs_key(o)
        by_key.setdefault(k, []).append(o)
    # Por cada clave quedarse con la "mejor": preferir roi_path y blur_score no None
    best: list[PalletObservation] = []
    for group in by_key.values():
        chosen = max(
            group,
            key=lambda ob: (ob.roi_path is not None, ob.blur_score is not None),
        )
        best.append(chosen)
    # Ordenar por frame_idx, luego bbox como desempate
    best.sort(key=lambda o: (o.frame_idx, o.bbox))
    # Asignar merged track_id a todas las observaciones
    return [
        o.model_copy(update={"track_id": merged_track_id}) if o.track_id != merged_track_id else o
        for o in best
    ]


def merge_tracks_dsu(
    tracks: list[PalletTrack],
    confirmed_pairs: list[tuple[str, str]],
) -> list[PalletTrack]:
    """Fusiona tracks con Union-Find según pares confirmados (Re-ID).

    - Solo se consideran track_ids presentes en `tracks`. Pares con ids inexistentes se ignoran.
    - Pares se normalizan a (min_id, max_id) para determinismo.
    - Cada componente de tamaño 1 se devuelve como track original.
    - Componentes de tamaño > 1 se fusionan: track_id = min(componente), observaciones
      concatenadas, ordenadas por (frame_idx, bbox) y deduplicadas por (frame_idx, bbox).
    - Salida ordenada por (start_frame, end_frame, track_id).

    Args:
        tracks: Lista de tracks originales.
        confirmed_pairs: Lista de (track_id_a, track_id_b) confirmados por CLIP.

    Returns:
        Lista de tracks (originales o fusionados), determinista.
    """
    if not tracks:
        return []
    by_id: dict[str, PalletTrack] = {t.track_id: t for t in tracks}
    valid_ids: set[str] = set(by_id.keys())

    # DSU: solo nodos que existen en tracks
    parent: dict[str, str] = {tid: tid for tid in valid_ids}

    for a, b in confirmed_pairs:
        if a not in valid_ids or b not in valid_ids:
            continue
        pa = (min(a, b), max(a, b))
        _dsu_union(parent, pa[0], pa[1])

    # Componentes: root -> set de track_ids
    components: dict[str, set[str]] = {}
    for tid in valid_ids:
        root = _dsu_find(parent, tid)
        components.setdefault(root, set()).add(tid)

    result: list[PalletTrack] = []
    for root in sorted(components.keys()):
        comp = components[root]
        if len(comp) == 1:
            result.append(by_id[root])
            continue
        # Merge: merged_track_id = root (ya es el min del componente por nuestro union)
        merged_track_id = root
        base_track = by_id[merged_track_id]
        all_obs: list[PalletObservation] = []
        for tid in sorted(comp):
            all_obs.extend(by_id[tid].observations)
        merged_obs = _merge_observations(all_obs, merged_track_id)
        if not merged_obs:
            # Fallback: mantener base track
            result.append(base_track)
            continue
        start_frame = min(o.frame_idx for o in merged_obs)
        end_frame = max(o.frame_idx for o in merged_obs)
        merged_track = base_track.model_copy(
            update={
                "track_id": merged_track_id,
                "observations": merged_obs,
                "start_frame": start_frame,
                "end_frame": end_frame,
            }
        )
        result.append(merged_track)

    # Orden determinista: (start_frame, end_frame, track_id)
    result.sort(key=lambda t: (t.start_frame, t.end_frame, t.track_id))
    return result


def get_merge_map(
    tracks: list[PalletTrack],
    confirmed_pairs: list[tuple[str, str]],
) -> dict[str, list[str]]:
    """Construye mapa root_id -> [original track_ids] para componentes con más de un track.

    Útil para pipeline_debug/reid_merge_map sin modificar el schema de PalletTrack.
    """
    if not tracks:
        return {}
    valid_ids: set[str] = {t.track_id for t in tracks}
    parent: dict[str, str] = {tid: tid for tid in valid_ids}
    for a, b in confirmed_pairs:
        if a not in valid_ids or b not in valid_ids:
            continue
        _dsu_union(parent, min(a, b), max(a, b))
    components: dict[str, set[str]] = {}
    for tid in valid_ids:
        root = _dsu_find(parent, tid)
        components.setdefault(root, set()).add(tid)
    return {root: sorted(members) for root, members in components.items() if len(members) > 1}
