"""
Utilidades de sanitización para rutas e identificadores.

Evita path traversal y caracteres inseguros en valores usados para
construir rutas de salida (p. ej. video_id). Stage 2.2.A: photo stored filenames.
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Caracteres permitidos en video_id (segmento de path seguro)
# Incluye letras, números, guión bajo, guión, punto.
_SAFE_VIDEO_ID_PATTERN = re.compile(r"[^a-zA-Z0-9_.-]")


def sanitize_video_id(value: str, fallback: str = "video") -> str:
    """Sanitiza un identificador de video para uso seguro en rutas.

    Elimina o reemplaza caracteres que podrían causar path traversal
    (por ejemplo '..', '/', '\\') o que no son seguros en nombres de
    directorio. Solo se mantienen letras, dígitos, '_', '-' y '.'.

    Espacios se reemplazan por '_' para mantener legibilidad.

    Args:
        value: Identificador crudo (p. ej. de --video-id o nombre de archivo).
        fallback: Valor a devolver si tras sanitizar la cadena queda vacía.

    Returns:
        Cadena segura para usar como segmento de path (sin .., /, \\).

    Examples:
        >>> sanitize_video_id("VID_001")
        'VID_001'
        >>> sanitize_video_id("../../etc")
        'etc'
        >>> sanitize_video_id("  ")
        'video'
    """
    if not value or not value.strip():
        logger.warning(
            "video_id vacío o solo espacios; usando fallback=%r (varias ejecuciones pueden compartir el mismo path base)",
            fallback,
        )
        return fallback

    # Normalizar espacios a guión bajo antes de filtrar
    normalized = value.strip().replace(" ", "_")

    # Eliminar cualquier carácter no permitido
    safe = _SAFE_VIDEO_ID_PATTERN.sub("", normalized)

    # Eliminar puntos/guiones consecutivos que podrían confundir (opcional:
    # ".." ya fue eliminado por el patrón; "." y "-" sí están permitidos)
    # Colapsar múltiples _ en uno
    safe = re.sub(r"_+", "_", safe)

    # Eliminar cualquier secuencia ".." (path traversal)
    while ".." in safe:
        safe = safe.replace("..", "")

    # Quitar _ - . al inicio y al final para evitar nombres vacíos visuales
    safe = safe.strip("_.-")

    if not safe:
        logger.warning(
            "video_id %r quedó vacío tras sanitizar; usando fallback=%r",
            value,
            fallback,
        )
        return fallback

    return safe


def photo_stored_filename(original_filename: str, index: int) -> str:
    """Return a safe, deterministic stored filename for a photo: {index:04d}_{slug}.jpg.

    Uses only the basename of original_filename; no path traversal (.., /, \\).
    Slug is alphanumeric + underscore/hyphen; empty slug becomes "image".

    Args:
        original_filename: Client-provided filename (may contain path or unsafe chars).
        index: 1-based photo index.

    Returns:
        Stored filename e.g. 0001_my_photo.jpg, 0002_image.jpg.
    """
    from src.evidence.paths import slug

    base = Path(original_filename or "").name.strip()
    if not base or ".." in base or "\\" in base or "/" in base:
        base = "image"
    slug_part = slug(base)
    if not slug_part:
        slug_part = "image"
    return f"{index:04d}_{slug_part}.jpg"
