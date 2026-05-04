"""
Módulo de normalización para consolidación.

Proporciona funciones para normalizar claves de productos y pallets
para agrupar observaciones del mismo producto/pallet.
"""

import re
import unicodedata
from typing import Optional


def _normalize_text(text: str) -> str:
    """Normaliza un texto de forma robusta.

    Aplica:
    - Lowercase
    - Trim
    - Quitar acentos
    - Quitar puntuación
    - Colapsar espacios múltiples a uno solo

    Args:
        text: Texto a normalizar.

    Returns:
        Texto normalizado.

    Examples:
        >>> _normalize_text("  LECHE UAT ENTERA 12x1L  ")
        'leche uat entera 12x1l'

        >>> _normalize_text("Cajas de cartón")
        'cajas de carton'
    """
    if not text:
        return ""

    # 1. Lowercase
    normalized = text.lower()

    # 2. Quitar acentos (NFD -> ASCII)
    normalized = unicodedata.normalize("NFD", normalized)
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")

    # 3. Quitar puntuación específica (mantener números y letras)
    # Quitar: . , ; : ! ? - _ ( ) [ ] { } " ' / \ | @ # $ % ^ & * + = ~ `
    # Mantener: números, letras, espacios
    normalized = re.sub(r"[^\w\s]", "", normalized)

    # 4. Colapsar espacios múltiples a uno solo
    normalized = re.sub(r"\s+", " ", normalized)

    # 5. Trim
    normalized = normalized.strip()

    return normalized


def normalize_product_key(brand: Optional[str], product: str) -> str:
    """Normaliza una clave de producto para agrupación (versión robusta).

    Combina brand y product en una clave única normalizada que permite
    agrupar observaciones del mismo producto incluso si hay variaciones
    en mayúsculas, acentos, puntuación o espacios.

    Args:
        brand: Marca del producto (opcional).
        product: Nombre o descripción del producto.

    Returns:
        Clave normalizada en formato "brand||product" (normalizada).

    Examples:
        >>> normalize_product_key("Cremigal", "Leche UAT Entera 12x1L")
        'cremigal||leche uat entera 12x1l'

        >>> normalize_product_key("CREMIGAL", "  LECHE UAT ENTERA  ")
        'cremigal||leche uat entera'

        >>> normalize_product_key(None, "Cajas de cartón")
        '||cajas de carton'
    """
    # Normalizar brand
    brand_normalized = ""
    if brand:
        brand_normalized = _normalize_text(brand)

    # Normalizar product
    product_normalized = _normalize_text(product)

    # Combinar con separador
    return f"{brand_normalized}||{product_normalized}"
