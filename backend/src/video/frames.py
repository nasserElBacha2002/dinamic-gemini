"""
Módulo de extracción de frames de video.

Responsabilidades:
- Generar frames según estrategia configurable
- Controlar densidad de muestreo
- Retornar referencias a frames con metadata
- (v2.0) Extracción de frames representativos para análisis global
- (Stage 5) Estrategia "optimized": menos redundancia, sin blur, cobertura completa
"""

from typing import Optional

import cv2
import numpy as np

from src.models.schemas import FrameRef

# Strategy constants for extract_representative_frames
STRATEGY_UNIFORM = "uniform"
STRATEGY_OPTIMIZED = "optimized"
DEFAULT_STRATEGY = STRATEGY_OPTIMIZED
MIN_FRAMES_FALLBACK = 10


def extract_frames(video_path: str, target_fps: float) -> list[FrameRef]:
    """Extrae frames de un video según un FPS objetivo.

    Args:
        video_path: Ruta al archivo de video.
        target_fps: FPS objetivo para la extracción (ej: 1.0 = 1 frame por segundo).

    Returns:
        List[FrameRef]: Lista de referencias a frames extraídos.

    Raises:
        RuntimeError: Si no se puede abrir el video.
        ValueError: Si target_fps es inválido.
    """
    if target_fps <= 0:
        raise ValueError(f"target_fps debe ser mayor que 0, recibido: {target_fps}")

    # Abrir video
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el video: {video_path}")

    try:
        # Obtener FPS del video
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        if video_fps <= 0:
            # Fallback a 30 fps si no se puede determinar
            video_fps = 30.0

        # Calcular step (cada cuántos frames extraer)
        # Si target_fps = 1.0 y video_fps = 30.0, step = 30 (extraer cada 30 frames)
        step = max(1, int(round(video_fps / target_fps)))

        frames: list[FrameRef] = []
        frame_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Extraer frame si corresponde según el step
            if frame_idx % step == 0:
                timestamp_seconds = frame_idx / video_fps
                h, w = frame.shape[:2]

                frames.append(
                    FrameRef(
                        frame_idx=frame_idx,
                        timestamp_seconds=timestamp_seconds,
                        width=w,
                        height=h,
                    )
                )

            frame_idx += 1

        return frames

    finally:
        cap.release()


def extract_frames_uniform(
    video_path: str, max_frames: int, start_frame: int = 0
) -> list[FrameRef]:
    """Extrae frames de manera uniforme distribuyendo max_frames a lo largo del video.

    Args:
        video_path: Ruta al archivo de video.
        max_frames: Número máximo de frames a extraer.
        start_frame: Frame inicial (default: 0).

    Returns:
        List[FrameRef]: Lista de referencias a frames extraídos.

    Raises:
        RuntimeError: Si no se puede abrir el video.
        ValueError: Si max_frames es inválido.
    """
    if max_frames <= 0:
        raise ValueError(f"max_frames debe ser mayor que 0, recibido: {max_frames}")

    # Abrir video
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el video: {video_path}")

    try:
        # Obtener metadata del video
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        if video_fps <= 0:
            video_fps = 30.0

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            raise ValueError("No se pudo determinar el número total de frames")

        # Calcular step para distribución uniforme
        # Si tenemos 100 frames y queremos 10, step = 10
        available_frames = total_frames - start_frame
        if available_frames <= 0:
            return []

        if max_frames >= available_frames:
            # Si queremos más frames de los disponibles, extraer todos
            step = 1
        else:
            step = available_frames // max_frames

        frames: list[FrameRef] = []
        frame_idx = start_frame

        # Posicionar en el frame inicial
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        while len(frames) < max_frames and frame_idx < total_frames:
            ret, frame = cap.read()
            if not ret:
                break

            # Extraer frame si corresponde
            if (frame_idx - start_frame) % step == 0:
                timestamp_seconds = frame_idx / video_fps
                h, w = frame.shape[:2]

                frames.append(
                    FrameRef(
                        frame_idx=frame_idx,
                        timestamp_seconds=timestamp_seconds,
                        width=w,
                        height=h,
                    )
                )

            frame_idx += 1

        return frames

    finally:
        cap.release()


def _dhash(frame: np.ndarray, size: tuple[int, int] = (9, 8)) -> int:
    """Compute 64-bit difference hash (dHash) using OpenCV + numpy. Grayscale 9x8, left-right diffs."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, size, interpolation=cv2.INTER_AREA)
    # Left-right gradient: 1 if right > left else 0 → 8*8 = 64 bits
    diff = resized[:, 1:] > resized[:, :-1]
    bits = np.packbits(diff.astype(np.uint8))
    return int.from_bytes(bits.tobytes()[:8], byteorder="big")


def _hamming_distance(h1: int, h2: int) -> int:
    """Number of bit differences between two 64-bit hashes."""
    return (h1 ^ h2).bit_count()


def _blur_metric(frame: np.ndarray) -> float:
    """Variance of Laplacian; lower = blurrier. OpenCV-only."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _extract_representative_frames_uniform(
    cap: cv2.VideoCapture,
    total_frames: int,
    max_frames: int,
) -> tuple[list[np.ndarray], list[int]]:
    """Uniform sampling: return (frames, indices). Caller holds cap open."""
    if max_frames >= total_frames:
        indices_to_try = list(range(total_frames))
    else:
        step = total_frames / max_frames
        indices_to_try = [int(i * step) for i in range(max_frames)]
    frames: list[np.ndarray] = []
    picked_indices: list[int] = []
    for idx in indices_to_try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret or frame is None:
            continue
        frames.append(frame.copy())
        picked_indices.append(idx)
    return frames, picked_indices


def _extract_representative_frames_optimized(
    cap: cv2.VideoCapture,
    total_frames: int,
    max_frames: int,
    min_gap_frames: int,
    hash_threshold: int,
    blur_threshold: float,
) -> tuple[list[np.ndarray], list[int]]:
    """Phase A: base candidates (uniform, 4x max_frames, step >= min_gap). Phase B: filter blur + redundancy. Fallback to uniform if < MIN_FRAMES_FALLBACK."""
    num_candidates = min(4 * max_frames, total_frames)
    step = max(min_gap_frames, total_frames // num_candidates) if num_candidates else 1
    candidate_indices: list[int] = []
    idx = 0
    while idx < total_frames and len(candidate_indices) < 4 * max_frames:
        candidate_indices.append(idx)
        idx += step
    if not candidate_indices:
        return [], []

    frames: list[np.ndarray] = []
    picked_indices: list[int] = []
    last_hash: Optional[int] = None

    for idx in candidate_indices:
        if len(frames) >= max_frames:
            break
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret or frame is None:
            continue
        if _blur_metric(frame) < blur_threshold:
            continue
        h = _dhash(frame)
        if last_hash is not None and _hamming_distance(last_hash, h) <= hash_threshold:
            continue
        last_hash = h
        frames.append(frame.copy())
        picked_indices.append(idx)

    if len(frames) < MIN_FRAMES_FALLBACK and total_frames > 0:
        need = min(MIN_FRAMES_FALLBACK - len(frames), max_frames - len(frames))
        if need > 0:
            picked_set = set(picked_indices)
            for i in range(need):
                idx = int((i + 0.5) * total_frames / need)
                idx = min(max(idx, 0), total_frames - 1)
                if idx in picked_set:
                    for delta in range(1, 6):
                        candidate = min(idx + delta, total_frames - 1)
                        if candidate not in picked_set:
                            idx = candidate
                            break
                    else:
                        continue
                if idx in picked_set:
                    continue
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if not ret or frame is None:
                    continue
                frames.append(frame.copy())
                picked_indices.append(idx)
                picked_set.add(idx)
                if len(frames) >= MIN_FRAMES_FALLBACK or len(frames) >= max_frames:
                    break

    return frames, picked_indices


def extract_representative_frames(
    video_path: str,
    max_frames: int = 25,
    strategy: str = DEFAULT_STRATEGY,
    min_gap_frames: int = 3,
    hash_threshold: int = 10,
    blur_threshold: float = 100.0,
) -> tuple[list[np.ndarray], dict]:
    """Extrae frames representativos del video para análisis global (v2.0 hybrid).

    Estrategias:
    - "uniform": muestreo uniforme (comportamiento clásico).
    - "optimized": candidatos uniformes 4x, filtro blur (Laplacian) + redundancia (dHash),
      fallback a uniform si quedan menos de MIN_FRAMES_FALLBACK.

    frame_indices contiene solo los índices de frames realmente leídos y aceptados;
    len(frame_indices) == len(frames) siempre.

    Args:
        video_path: Ruta al archivo de video.
        max_frames: Número máximo de frames a extraer.
        strategy: "uniform" o "optimized".
        min_gap_frames: Mínimo espacio entre índices candidatos (solo optimized).
        hash_threshold: Hamming distance <= este valor → considerado duplicado (solo optimized).
        blur_threshold: Variance of Laplacian por debajo → frame descartado por blur (solo optimized).

    Returns:
        (frames, metadata): metadata tiene "fps", "frame_indices".
    """
    if max_frames <= 0:
        raise ValueError(f"max_frames debe ser mayor que 0, recibido: {max_frames}")
    if strategy not in (STRATEGY_UNIFORM, STRATEGY_OPTIMIZED):
        raise ValueError(f"Estrategia no soportada: {strategy!r}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el video: {video_path}")

    try:
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        if video_fps <= 0:
            video_fps = 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            return [], {"fps": video_fps, "frame_indices": []}

        if strategy == STRATEGY_UNIFORM:
            frames, picked_indices = _extract_representative_frames_uniform(
                cap, total_frames, max_frames
            )
        else:
            frames, picked_indices = _extract_representative_frames_optimized(
                cap,
                total_frames,
                max_frames,
                min_gap_frames,
                hash_threshold,
                blur_threshold,
            )
        return frames, {"fps": video_fps, "frame_indices": picked_indices}
    finally:
        cap.release()
