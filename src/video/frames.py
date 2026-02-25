"""
Módulo de extracción de frames de video.

Responsabilidades:
- Generar frames según estrategia configurable
- Controlar densidad de muestreo
- Retornar referencias a frames con metadata
"""

from typing import List

import cv2

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
