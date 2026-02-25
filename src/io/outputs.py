"""
Módulo de I/O para exportación de resultados.

Proporciona funciones para convertir resultados consolidados a formato final
y guardarlos en diferentes formatos.
"""

import json
from pathlib import Path
from typing import Optional

from src.models.schemas import (
    ConsolidatedResult,
    FinalResult,
    PalletEstimate,
    ProductEstimate,
)


def to_final_result(
    consolidated: ConsolidatedResult,
    processing_summary: Optional[dict] = None,
) -> FinalResult:
    """Convierte un ConsolidatedResult a FinalResult (formato de salida final).
    
    Mapea los resultados consolidados (con estadísticas internas) a un formato
    simple y limpio para exportación.
    
    Args:
        consolidated: Resultado consolidado con estadísticas.
        processing_summary: Resumen opcional del procesamiento (tiempos, frames, etc.).
    
    Returns:
        FinalResult con formato simple para exportación.
    
    Examples:
        >>> from src.models.schemas import ConsolidatedResult, ConsolidatedPallet, ConsolidatedProduct
        >>> consolidated = ConsolidatedResult(
        ...     video_id="VID_001",
        ...     pallets=[ConsolidatedPallet(
        ...         pallet_id="P1",
        ...         products=[ConsolidatedProduct(
        ...             product="Leche",
        ...             estimated_boxes=10,
        ...             confidence=0.9,
        ...             evidence_frames=3
        ...         )]
        ...     )]
        ... )
        >>> final = to_final_result(consolidated)
        >>> final.video_id
        'VID_001'
    """
    pallets = []
    for p in consolidated.pallets:
        products = [
            ProductEstimate(
                brand=cp.brand,
                product=cp.product,
                estimated_boxes=cp.estimated_boxes,
                confidence=cp.confidence,
            )
            for cp in p.products
        ]
        pallets.append(PalletEstimate(pallet_id=p.pallet_id, products=products))
    
    return FinalResult(
        video_id=consolidated.video_id,
        pallets=pallets,
        processing_summary=processing_summary,
    )


def save_result_json(result: FinalResult, output_path: str) -> None:
    """Guarda un FinalResult como archivo JSON.
    
    Args:
        result: Resultado final a guardar.
        output_path: Ruta donde guardar el archivo JSON.
    
    Raises:
        IOError: Si no se puede escribir el archivo.
    
    Examples:
        >>> result = FinalResult(video_id="VID_001", pallets=[])
        >>> save_result_json(result, "output/result.json")
    """
    output_file = Path(output_path)
    
    # Crear directorio si no existe
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Convertir a dict y guardar como JSON
    result_dict = result.model_dump(mode="json", exclude_none=True)
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result_dict, f, indent=2, ensure_ascii=False)
    
    return output_file


def save_result(result: FinalResult, output_path: str) -> Path:
    """Guarda un FinalResult (alias de save_result_json para compatibilidad).
    
    Args:
        result: Resultado final a guardar.
        output_path: Ruta donde guardar el archivo JSON.
    
    Returns:
        Path al archivo guardado.
    """
    return save_result_json(result, output_path)


def print_summary(result: FinalResult) -> None:
    """Imprime un resumen legible del resultado en consola.
    
    Args:
        result: Resultado final a resumir.
    
    Examples:
        >>> result = FinalResult(video_id="VID_001", pallets=[])
        >>> print_summary(result)
    """
    print("=" * 60)
    print("📊 Resumen de Resultados")
    print("=" * 60)
    print(f"📹 Video ID: {result.video_id}")
    print(f"📦 Pallets detectados: {len(result.pallets)}")
    print()
    
    total_products = 0
    total_boxes = 0
    
    for pallet in result.pallets:
        print(f"📦 Pallet: {pallet.pallet_id}")
        for product in pallet.products:
            total_products += 1
            total_boxes += product.estimated_boxes
            brand_str = f" ({product.brand})" if product.brand else ""
            print(
                f"   • {product.product}{brand_str}: "
                f"{product.estimated_boxes} cajas "
                f"(confianza: {product.confidence:.2f})"
            )
        print()
    
    print("=" * 60)
    print("📈 Totales")
    print("=" * 60)
    print(f"   - Productos únicos: {total_products}")
    print(f"   - Total de cajas: {total_boxes}")
    print()
    
    # Mostrar resumen de procesamiento si está disponible
    if result.processing_summary:
        print("=" * 60)
        print("⚙️  Resumen de Procesamiento")
        print("=" * 60)
        for key, value in result.processing_summary.items():
            print(f"   - {key}: {value}")
        print()
