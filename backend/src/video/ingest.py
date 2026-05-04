"""
Módulo de ingesta de video.

Responsabilidades:
- Validar archivo de video
- Extraer metadata (fps, duración, resolución)
- Manejar errores de formato
"""

from pathlib import Path
from typing import Optional

import cv2

from src.models.schemas import VideoMetadata


def load_video_metadata(video_path: str, video_id: Optional[str] = None) -> VideoMetadata:
    """Carga y valida metadata de un archivo de video.

    Args:
        video_path: Ruta al archivo de video.
        video_id: ID opcional del video. Si no se proporciona, se usa el nombre del archivo.

    Returns:
        VideoMetadata: Metadata del video validada.

    Raises:
        FileNotFoundError: Si el archivo no existe.
        RuntimeError: Si el video no se puede abrir o está corrupto.
        ValueError: Si el video no tiene metadata válida.
    """
    # Validar que el archivo existe
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"El archivo de video no existe: {video_path}")

    if not path.is_file():
        raise ValueError(f"La ruta no es un archivo: {video_path}")

    # Validar formato soportado (extensiones comunes)
    valid_extensions = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
    if path.suffix.lower() not in valid_extensions:
        raise ValueError(
            f"Formato de video no soportado: {path.suffix}. "
            f"Formatos soportados: {', '.join(valid_extensions)}"
        )

    # Abrir video con OpenCV
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el video: {video_path}")

    try:
        # Extraer metadata
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Validar que se obtuvieron valores válidos
        if fps <= 0:
            raise ValueError(f"FPS inválido o no disponible: {fps}")

        if frame_count <= 0:
            raise ValueError(f"Número de frames inválido: {frame_count}")

        if width <= 0 or height <= 0:
            raise ValueError(f"Resolución inválida: {width}x{height}")

        # Calcular duración
        duration_seconds = frame_count / fps

        # Generar video_id si no se proporciona
        if video_id is None:
            video_id = path.stem

        return VideoMetadata(
            video_id=video_id,
            file_path=str(path.resolve()),
            duration_seconds=duration_seconds,
            fps=fps,
            width=width,
            height=height,
        )

    finally:
        cap.release()


def validate_video_file(video_path: str) -> bool:
    """Valida rápidamente si un archivo de video puede ser abierto.

    Args:
        video_path: Ruta al archivo de video.

    Returns:
        bool: True si el video puede ser abierto, False en caso contrario.
    """
    try:
        path = Path(video_path)
        if not path.exists():
            return False

        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return False

        # Intentar leer un frame para verificar que no está corrupto
        ret, _ = cap.read()
        cap.release()

        return ret

    except Exception:
        return False
