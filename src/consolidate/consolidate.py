"""
Módulo de consolidación de resultados multi-frame.

Aplica técnicas estadísticas (MAD, mediana) para consolidar observaciones
de múltiples frames del mismo pallet/producto en una estimación final robusta.
"""

import math
import statistics
from collections import defaultdict
from typing import Dict, List, Tuple

from src.consolidate.normalize import normalize_product_key
from src.models.schemas import (
    ConsolidationStats,
    ConsolidatedProduct,
    ConsolidatedPallet,
    ConsolidatedResult,
    LLMFrameResult,
)


def _mad(xs: List[int], med: float) -> float:
    """Calcula la Median Absolute Deviation (MAD) de una lista de valores.
    
    MAD es una medida robusta de dispersión que es menos sensible a outliers
    que la desviación estándar.
    
    Args:
        xs: Lista de valores enteros.
        med: Mediana de los valores.
    
    Returns:
        MAD como float. Retorna 0.0 si la lista está vacía.
    
    Examples:
        >>> _mad([10, 12, 11, 13, 15], 12.0)
        1.0
        
        >>> _mad([], 0.0)
        0.0
    """
    if not xs:
        return 0.0
    
    deviations = [abs(x - med) for x in xs]
    return float(statistics.median(deviations))


def consolidate(
    video_id: str,
    frame_results: List[LLMFrameResult],
    n_target: int = 8,
    mad_threshold: float = 3.0,
) -> ConsolidatedResult:
    """Consolida resultados de múltiples frames usando MAD y mediana.
    
    Agrupa observaciones por pallet_id y product_key, luego aplica:
    1. Cálculo de mediana y MAD
    2. Filtrado de outliers usando MAD
    3. Estimación final (mediana de inliers)
    4. Cálculo de confianza final (considerando estabilidad y cobertura)
    
    Args:
        video_id: ID del video procesado.
        frame_results: Lista de resultados de frames individuales.
        n_target: Número objetivo de observaciones para cobertura completa.
        mad_threshold: Factor k para filtrado de outliers (default: 3.0).
    
    Returns:
        ConsolidatedResult con pallets y productos consolidados.
    
    Examples:
        >>> from src.models.schemas import LLMFrameResult, FrameRef, LLMPalletObservation, LLMProductObservation
        >>> frame1 = LLMFrameResult(
        ...     frame=FrameRef(frame_idx=0, timestamp_seconds=0.0),
        ...     pallets=[LLMPalletObservation(
        ...         pallet_id="P1",
        ...         products=[LLMProductObservation(product="Leche", estimated_boxes=10, confidence=0.9)]
        ...     )]
        ... )
        >>> result = consolidate("VID_001", [frame1])
        >>> result.video_id
        'VID_001'
    """
    # Estructuras para agrupar observaciones
    # pallet_id -> product_key -> list of (estimated_boxes, confidence)
    buckets: Dict[str, Dict[str, List[Tuple[int, float]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    
    # Metadatos para reconstruir brand/product en el output
    # pallet_id -> product_key -> list of {"brand": ..., "product": ..., "confidence": ...}
    # Guardamos todas las observaciones para elegir la mejor después
    meta: Dict[str, Dict[str, List[Dict[str, Optional[str]]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    
    # Agrupar observaciones por pallet y producto
    for fr in frame_results:
        for pallet in fr.pallets:
            for prod in pallet.products:
                # Normalizar clave de producto
                product_key = normalize_product_key(prod.brand, prod.product)
                
                # Agregar observación al bucket
                buckets[pallet.pallet_id][product_key].append(
                    (prod.estimated_boxes, prod.confidence)
                )
                
                # Guardar metadatos (todas las observaciones)
                meta[pallet.pallet_id][product_key].append(
                    {
                        "brand": prod.brand,
                        "product": prod.product,
                        "confidence": prod.confidence,
                    }
                )
    
    # Consolidar cada pallet y producto
    consolidated_pallets: List[ConsolidatedPallet] = []
    
    for pallet_id, prod_map in buckets.items():
        consolidated_products: List[ConsolidatedProduct] = []
        
        for product_key, observations in prod_map.items():
            # Extraer valores y confianzas
            xs = [x for x, _ in observations]
            cs = [c for _, c in observations]
            
            if not xs:
                continue
            
            # Calcular mediana y MAD
            med = float(statistics.median(xs))
            mad = _mad(xs, med)
            
            # Filtrar outliers usando MAD
            if mad == 0:
                # Si MAD es 0, todos los valores son iguales (o muy cercanos)
                # Mantener solo los que son exactamente iguales a la mediana redondeada
                inliers = [(x, c) for (x, c) in observations if x == int(round(med))]
                if not inliers:
                    # Fallback: usar todas las observaciones
                    inliers = observations[:]
            else:
                # Filtrar usando threshold basado en MAD
                k = mad_threshold
                inliers = [
                    (x, c) for (x, c) in observations if abs(x - med) <= k * mad
                ]
                if not inliers:
                    # Fallback: usar todas las observaciones
                    inliers = observations[:]
            
            # Extraer valores y confianzas de inliers
            xs_in = [x for x, _ in inliers]
            cs_in = [c for _, c in inliers]
            
            # Recalcular MAD con inliers (mejora #3)
            med_in = float(statistics.median(xs_in))
            mad_in = _mad(xs_in, med_in)
            
            # Estimación final: weighted mode o mediana ponderada (mejora #5)
            # Agrupar conteos iguales y sumar confidences
            count_weights: Dict[int, float] = defaultdict(float)
            for x, c in inliers:
                count_weights[x] += c
            
            # Elegir el conteo con mayor peso total (weighted mode)
            if count_weights:
                est = max(count_weights.items(), key=lambda item: item[1])[0]
            else:
                # Fallback: mediana simple
                median_est = float(statistics.median(xs_in))
                est = int(round(median_est))
            
            # Calcular confianza final
            # 1. Confianza media de los inliers
            conf_mean = sum(cs_in) / max(1, len(cs_in))
            
            # 2. Factor de estabilidad usando MAD de inliers (mejora #3)
            if med_in > 0:
                stability_factor = math.exp(-(mad_in / max(1.0, med_in)))
            else:
                stability_factor = 1.0 if mad_in == 0 else 0.5
            
            # 3. Factor de cobertura (mejora #4: evitar división por cero)
            n_target_safe = max(1, n_target)
            coverage_factor = min(1.0, math.log(1 + len(inliers)) / math.log(1 + n_target_safe))
            
            # Confianza final: producto de los tres factores
            conf_final = max(0.0, min(1.0, conf_mean * stability_factor * coverage_factor))
            
            # Filtro de inclusión (mejora #8): descartar productos fantasmas
            # Solo aplicar si hay suficientes observaciones totales
            min_evidence_frames = 2
            min_confidence = 0.45
            if len(observations) >= 3:  # Solo filtrar si hay múltiples frames
                if len(inliers) < min_evidence_frames and conf_final < min_confidence:
                    # Producto fantasma: saltar
                    continue
            
            # Elegir mejor meta label (mejora #2): modo o más largo
            meta_list = meta[pallet_id][product_key]
            # Filtrar solo los que están en inliers (aproximado por índice)
            # Como no tenemos índice directo, usamos todas las observaciones
            # pero priorizamos por confianza y longitud
            
            # Opción 1: Más frecuente (modo)
            brand_counts: Dict[Optional[str], int] = defaultdict(int)
            product_counts: Dict[str, int] = defaultdict(int)
            brand_conf_sum: Dict[Optional[str], float] = defaultdict(float)
            product_conf_sum: Dict[str, float] = defaultdict(float)
            
            for m in meta_list:
                brand_counts[m["brand"]] += 1
                product_counts[m["product"]] += 1
                brand_conf_sum[m["brand"]] += m["confidence"]
                product_conf_sum[m["product"]] += m["confidence"]
            
            # Elegir brand: más frecuente, o si empate, mayor confianza promedio
            if brand_counts:
                best_brand = max(
                    brand_counts.items(),
                    key=lambda item: (item[1], brand_conf_sum[item[0]] / max(1, item[1])),
                )[0]
            else:
                best_brand = None
            
            # Elegir product: más largo (más completo) o más frecuente con mayor confianza
            if product_counts:
                best_product = max(
                    product_counts.items(),
                    key=lambda item: (
                        len(item[0]),  # Prioridad: más largo
                        item[1],  # Luego: más frecuente
                        product_conf_sum[item[0]] / max(1, item[1]),  # Luego: mayor confianza
                    ),
                )[0]
            else:
                best_product = meta_list[0]["product"] if meta_list else "Unknown"
            
            # Calcular mediana final para stats
            median_est = float(statistics.median(xs_in))
            
            # Crear producto consolidado
            consolidated_products.append(
                ConsolidatedProduct(
                    brand=best_brand,
                    product=best_product,
                    estimated_boxes=est,
                    confidence=conf_final,
                    evidence_frames=len(inliers),
                    stats=ConsolidationStats(
                        n_observations=len(observations),
                        n_inliers=len(inliers),
                        min_est=min(xs),
                        max_est=max(xs),
                        median_est=median_est,
                        mad=mad,
                        mad_inliers=mad_in,
                        conf_mean=conf_mean,
                        stability_factor=stability_factor,
                        coverage_factor=coverage_factor,
                    ),
                )
            )
        
        # Ordenar productos por estimated_boxes DESC, luego por product (mejora #9)
        consolidated_products.sort(
            key=lambda p: (-p.estimated_boxes, p.product.lower())
        )
        
        # Crear pallet consolidado
        consolidated_pallets.append(
            ConsolidatedPallet(pallet_id=pallet_id, products=consolidated_products)
        )
    
    # Ordenar pallets por pallet_id (mejora #9: orden determinístico)
    consolidated_pallets.sort(key=lambda p: p.pallet_id)
    
    return ConsolidatedResult(video_id=video_id, pallets=consolidated_pallets)
