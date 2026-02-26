"""
Módulo de selección de frames.

Responsabilidades:
- Seleccionar frames según diferentes estrategias
- Preparar frames para envío a API (guardar a disco)
"""

import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Literal, Optional

from src.models.schemas import FrameRef
from src.preprocess.image_ops import extract_frame_from_video, resize_image, save_frame


def select_frames(
    frames: List[FrameRef],
    strategy: Literal["all"] = "all",
) -> List[FrameRef]:
    """Selecciona frames de una lista.
    
    Actualmente solo se soporta "all" (todos los frames). Las estrategias
    "uniform", "first_n" y "distributed" se eliminaron en Bloque 8.
    
    Args:
        frames: Lista de referencias a frames.
        strategy: Siempre "all" — retorna todos los frames.
    
    Returns:
        List[FrameRef]: Lista de frames seleccionados (copia).
    
    Raises:
        ValueError: Si strategy no es "all".
    """
    if not frames:
        return []
    if strategy != "all":
        raise ValueError(
            f"Estrategia no reconocida: {strategy}. "
            "Única estrategia válida: 'all'."
        )
    return frames.copy()


def prepare_frames_for_api(
    frames: List[FrameRef],
    video_path: str,
    output_dir: str,
    resize_max_side: int = 1280,
    quality: int = 85,
    video_id: str = "VID",
    run_id: Optional[str] = None,
    save_frames: bool = False,
) -> tuple[List[str], str]:
    """Prepara frames para envío a API: extrae, redimensiona y guarda a disco.
    
    Esta función:
    1. Extrae los frames reales del video
    2. Los redimensiona si es necesario
    3. Los guarda como imágenes JPEG en el directorio de salida
    4. Retorna las rutas a las imágenes guardadas y el run_id
    
    Cada ejecución crea su propio directorio único para evitar sobrescrituras.
    
    Args:
        frames: Lista de referencias a frames a procesar.
        video_path: Ruta al archivo de video.
        output_dir: Directorio base donde guardar las imágenes.
        resize_max_side: Tamaño máximo del lado al redimensionar.
        quality: Calidad JPEG (0-100).
        video_id: ID del video para nombrar los archivos.
        run_id: ID único de ejecución. Si no se proporciona, se genera uno.
        save_frames: Si True, guarda los frames (siempre se guardan para la API, este flag es para debug).
    
    Returns:
        tuple[List[str], str]: Lista de rutas absolutas a las imágenes guardadas y run_id.
    
    Raises:
        RuntimeError: Si no se puede abrir el video.
        IOError: Si no se puede guardar algún frame.
    """
    if not frames:
        return [], run_id or ""
    
    # Generar run_id único si no se proporciona
    if run_id is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        run_id = f"{timestamp}_{unique_id}"
    
    # Crear directorio de salida
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Crear subdirectorio único para esta ejecución
    # Estructura: output/<video_id>/<run_id>/frames/
    run_dir = output_path / video_id / run_id
    frames_dir = run_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    
    saved_paths: List[str] = []
    
    for i, frame_ref in enumerate(frames):
        # Extraer frame del video
        frame = extract_frame_from_video(video_path, frame_ref.frame_idx)
        
        if frame is None:
            # Si no se pudo extraer, saltar este frame
            continue
        
        # Redimensionar si es necesario
        if resize_max_side > 0:
            frame = resize_image(frame, resize_max_side)
        
        # Generar nombre de archivo
        filename = f"frame_{frame_ref.frame_idx:06d}_{i:03d}.jpg"
        filepath = frames_dir / filename
        
        # Guardar frame
        saved_path = save_frame(frame, str(filepath), quality=quality)
        saved_paths.append(saved_path)
    
    return saved_paths, run_id
