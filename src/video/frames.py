"""
Módulo de extracción de frames de video.

Responsabilidades:
- Generar frames según estrategia configurable
- Controlar densidad de muestreo
- Retornar referencias a frames con metadata
- (v2.0) Extracción de frames representativos para análisis global
"""

from typing import List, Tuple

import cv2
import numpy as np

from src.models.schemas import FrameRef


def extract_frames(video_path: str, target_fps: float) -> List[FrameRef]:
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
        
        frames: List[FrameRef] = []
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
) -> List[FrameRef]:
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
        
        frames: List[FrameRef] = []
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


def extract_representative_frames(
    video_path: str,
    max_frames: int = 25,
    strategy: str = "uniform",
) -> Tuple[List[np.ndarray], dict]:
    """Extrae frames representativos del video para análisis global (v2.0 hybrid).

    Muestreo uniforme a lo largo de la duración. Retorna arrays de píxeles en memoria
    y metadata (fps, frame_indices).

    frame_indices contiene solo los índices de frames que se leyeron correctamente;
    len(frame_indices) == len(frames) siempre. Si un frame falla al leer, no se
    añade a frames ni su índice a frame_indices.

    Args:
        video_path: Ruta al archivo de video.
        max_frames: Número máximo de frames a extraer.
        strategy: Estrategia de muestreo; solo "uniform" soportado.

    Returns:
        (frames, metadata): frames es List[np.ndarray] (BGR), metadata tiene
        "fps", "frame_indices" (índices realmente leídos, uno por frame).

    Raises:
        RuntimeError: Si no se puede abrir el video.
        ValueError: Si max_frames o strategy son inválidos.
    """
    if max_frames <= 0:
        raise ValueError(f"max_frames debe ser mayor que 0, recibido: {max_frames}")
    if strategy != "uniform":
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

        if max_frames >= total_frames:
            indices_to_try = list(range(total_frames))
        else:
            step = total_frames / max_frames
            indices_to_try = [int(i * step) for i in range(max_frames)]

        frames: List[np.ndarray] = []
        picked_indices: List[int] = []
        for idx in indices_to_try:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue
            frames.append(frame.copy())
            picked_indices.append(idx)
        return frames, {"fps": video_fps, "frame_indices": picked_indices}
    finally:
        cap.release()
