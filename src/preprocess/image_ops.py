"""
Módulo de operaciones de preprocesamiento de imágenes.

Responsabilidades:
- Redimensionar imágenes
- Aplicar ROI (región de interés)
- Comprimir imágenes
- Guardar y cargar frames
"""

from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np


def resize_image(frame: np.ndarray, max_side: int) -> np.ndarray:
    """Redimensiona una imagen manteniendo el aspect ratio.
    
    La imagen se redimensiona de manera que el lado más largo sea max_side,
    manteniendo la proporción original.
    
    Args:
        frame: Imagen como array de numpy (H, W, C) o (H, W).
        max_side: Tamaño máximo del lado más largo en píxeles.
    
    Returns:
        np.ndarray: Imagen redimensionada.
    
    Raises:
        ValueError: Si max_side es inválido o frame está vacío.
    """
    if max_side <= 0:
        raise ValueError(f"max_side debe ser mayor que 0, recibido: {max_side}")
    
    if frame.size == 0:
        raise ValueError("El frame está vacío")
    
    h, w = frame.shape[:2]
    
    # Si ya es más pequeño, no redimensionar
    if max(h, w) <= max_side:
        return frame.copy()
    
    # Calcular nuevas dimensiones manteniendo aspect ratio
    if h > w:
        # Alto es mayor
        new_h = max_side
        new_w = int(w * (max_side / h))
    else:
        # Ancho es mayor o igual
        new_w = max_side
        new_h = int(h * (max_side / w))
    
    # Redimensionar
    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return resized


def apply_roi(
    frame: np.ndarray, roi: Tuple[int, int, int, int]
) -> np.ndarray:
    """Aplica una región de interés (ROI) a un frame.
    
    Args:
        frame: Imagen como array de numpy (H, W, C) o (H, W).
        roi: Tupla (x, y, width, height) definiendo la región de interés.
    
    Returns:
        np.ndarray: Frame recortado según la ROI.
    
    Raises:
        ValueError: Si la ROI es inválida o está fuera de los límites del frame.
    """
    if len(roi) != 4:
        raise ValueError(f"ROI debe tener 4 elementos (x, y, width, height), recibido: {roi}")
    
    x, y, width, height = roi
    
    if width <= 0 or height <= 0:
        raise ValueError(f"Ancho y alto de ROI deben ser mayores que 0, recibido: {width}x{height}")
    
    h, w = frame.shape[:2]
    
    # Validar que la ROI está dentro de los límites
    if x < 0 or y < 0:
        raise ValueError(f"ROI no puede tener coordenadas negativas: x={x}, y={y}")
    
    if x + width > w or y + height > h:
        raise ValueError(
            f"ROI está fuera de los límites del frame: "
            f"frame={w}x{h}, ROI=({x}, {y}, {width}, {height})"
        )
    
    # Aplicar recorte
    cropped = frame[y : y + height, x : x + width]
    return cropped.copy()


def compress_image(frame: np.ndarray, quality: int = 85) -> bytes:
    """Comprime una imagen a JPEG.
    
    Args:
        frame: Imagen como array de numpy (H, W, C) en formato BGR.
        quality: Calidad JPEG (0-100, mayor = mejor calidad).
    
    Returns:
        bytes: Imagen comprimida como bytes.
    
    Raises:
        ValueError: Si quality está fuera de rango o frame está vacío.
    """
    if quality < 0 or quality > 100:
        raise ValueError(f"quality debe estar entre 0 y 100, recibido: {quality}")
    
    if frame.size == 0:
        raise ValueError("El frame está vacío")
    
    # Convertir BGR a RGB si es necesario (OpenCV usa BGR, JPEG espera RGB)
    if len(frame.shape) == 3 and frame.shape[2] == 3:
        # Asumimos que viene en BGR de OpenCV, convertir a RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    else:
        frame_rgb = frame
    
    # Comprimir a JPEG
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
    success, encoded = cv2.imencode(".jpg", frame_rgb, encode_params)
    
    if not success:
        raise RuntimeError("Error al comprimir la imagen")
    
    return encoded.tobytes()


def save_frame(
    frame: np.ndarray, output_path: str, quality: int = 85
) -> str:
    """Guarda un frame como imagen JPEG.
    
    Args:
        frame: Imagen como array de numpy (H, W, C) en formato BGR.
        output_path: Ruta donde guardar la imagen.
        quality: Calidad JPEG (0-100, mayor = mejor calidad).
    
    Returns:
        str: Ruta absoluta del archivo guardado.
    
    Raises:
        ValueError: Si quality está fuera de rango o frame está vacío.
        IOError: Si no se puede escribir el archivo.
    """
    if frame.size == 0:
        raise ValueError("El frame está vacío")
    
    # Crear directorio si no existe
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Guardar imagen
    success = cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    
    if not success:
        raise IOError(f"No se pudo guardar el frame en: {output_path}")
    
    return str(path.resolve())


def load_frame(image_path: str) -> np.ndarray:
    """Carga un frame desde un archivo de imagen.
    
    Args:
        image_path: Ruta al archivo de imagen.
    
    Returns:
        np.ndarray: Imagen cargada en formato BGR (compatible con OpenCV).
    
    Raises:
        FileNotFoundError: Si el archivo no existe.
        IOError: Si no se puede leer el archivo.
    """
    path = Path(image_path)
    
    if not path.exists():
        raise FileNotFoundError(f"El archivo de imagen no existe: {image_path}")
    
    # Cargar imagen (OpenCV carga en BGR)
    frame = cv2.imread(str(path))
    
    if frame is None:
        raise IOError(f"No se pudo cargar la imagen: {image_path}")
    
    return frame


def extract_frame_from_video(
    video_path: str, frame_idx: int
) -> Optional[np.ndarray]:
    """Extrae un frame específico de un video.
    
    Args:
        video_path: Ruta al archivo de video.
        frame_idx: Índice del frame a extraer (0-based).
    
    Returns:
        np.ndarray: Frame extraído, o None si no se pudo leer.
    
    Raises:
        RuntimeError: Si no se puede abrir el video.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el video: {video_path}")
    
    try:
        # Posicionar en el frame deseado
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        
        # Leer frame
        ret, frame = cap.read()
        
        if not ret:
            return None
        
        return frame
    
    finally:
        cap.release()
