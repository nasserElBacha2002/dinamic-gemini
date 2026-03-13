"""
Módulo de detección de similitud entre frames.

Responsabilidades:
- Comparar frames para detectar duplicados o muy similares
- Filtrar frames redundantes antes de enviar a API
"""

from typing import List, Optional, Tuple

import cv2
import numpy as np

from src.models.schemas import FrameRef
from src.preprocess.image_ops import read_frame_at


def calculate_frame_similarity(frame1: np.ndarray, frame2: np.ndarray) -> float:
    """Calcula la similitud entre dos frames usando histograma.
    
    Args:
        frame1: Primer frame como array numpy.
        frame2: Segundo frame como array numpy.
    
    Returns:
        float: Similitud entre 0.0 (completamente diferentes) y 1.0 (idénticos).
    """
    # Redimensionar a tamaño común para comparación más rápida
    size = (256, 256)
    frame1_resized = cv2.resize(frame1, size)
    frame2_resized = cv2.resize(frame2, size)
    
    # Convertir a escala de grises si es necesario
    if len(frame1_resized.shape) == 3:
        frame1_gray = cv2.cvtColor(frame1_resized, cv2.COLOR_BGR2GRAY)
    else:
        frame1_gray = frame1_resized
    
    if len(frame2_resized.shape) == 3:
        frame2_gray = cv2.cvtColor(frame2_resized, cv2.COLOR_BGR2GRAY)
    else:
        frame2_gray = frame2_resized
    
    # Calcular histograma
    hist1 = cv2.calcHist([frame1_gray], [0], None, [256], [0, 256])
    hist2 = cv2.calcHist([frame2_gray], [0], None, [256], [0, 256])
    
    # Comparar histogramas usando correlación
    similarity = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
    
    return float(similarity)


def _filter_similar_frames_with_cap(
    cap: cv2.VideoCapture,
    frames: List[FrameRef],
    similarity_threshold: float,
    sample_size: Optional[int],
) -> List[FrameRef]:
    """Lógica común de filtrado con un VideoCapture ya abierto (Bloque 5)."""
    if not frames or len(frames) == 1:
        return frames.copy() if frames else []

    filtered = [frames[0]]
    prev_frame = read_frame_at(cap, frames[0].frame_idx)
    if prev_frame is None:
        return frames.copy()

    prev_frame_small = (
        cv2.resize(prev_frame, (sample_size, sample_size))
        if sample_size
        else prev_frame
    )

    for current_frame_ref in frames[1:]:
        current_frame = read_frame_at(cap, current_frame_ref.frame_idx)
        if current_frame is None:
            continue
        current_small = (
            cv2.resize(current_frame, (sample_size, sample_size))
            if sample_size
            else current_frame
        )
        similarity = calculate_frame_similarity(prev_frame_small, current_small)
        if similarity < similarity_threshold:
            filtered.append(current_frame_ref)
            prev_frame = current_frame
            prev_frame_small = current_small

    return filtered


def filter_similar_frames(
    frames: List[FrameRef],
    video_path: str,
    similarity_threshold: float = 0.95,
) -> List[FrameRef]:
    """Filtra frames que son muy similares entre sí.
    
    Compara cada frame con el anterior y lo descarta si la similitud
    es mayor al threshold. Esto evita enviar frames casi idénticos a la API.
    Abre el video una sola vez (Bloque 5).
    
    Args:
        frames: Lista de referencias a frames.
        video_path: Ruta al archivo de video.
        similarity_threshold: Umbral de similitud (0.0-1.0). 
            Frames con similitud > threshold se descartan.
            Default: 0.95 (95% similar = descartar).
    
    Returns:
        List[FrameRef]: Lista filtrada de frames únicos.
    
    Raises:
        RuntimeError: Si no se puede abrir el video.
    """
    if not frames:
        return []
    if len(frames) == 1:
        return frames.copy()

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el video: {video_path}")
    try:
        return _filter_similar_frames_with_cap(
            cap, frames, similarity_threshold, sample_size=None
        )
    finally:
        cap.release()


def filter_similar_frames_fast(
    frames: List[FrameRef],
    video_path: str,
    similarity_threshold: float = 0.95,
    sample_size: int = 100,
) -> List[FrameRef]:
    """Versión optimizada que compara frames redimensionados más pequeños.
    
    Abre el video una sola vez (Bloque 5 / US-5.1).
    
    Args:
        frames: Lista de referencias a frames.
        video_path: Ruta al archivo de video.
        similarity_threshold: Umbral de similitud (0.0-1.0).
        sample_size: Tamaño al que redimensionar para comparación (más rápido).
    
    Returns:
        List[FrameRef]: Lista filtrada de frames únicos.
    """
    if not frames:
        return []
    if len(frames) == 1:
        return frames.copy()

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el video: {video_path}")
    try:
        return _filter_similar_frames_with_cap(
            cap, frames, similarity_threshold, sample_size=sample_size
        )
    finally:
        cap.release()
