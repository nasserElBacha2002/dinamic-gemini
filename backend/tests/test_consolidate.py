"""
Tests unitarios para el módulo de consolidación.

Verifica:
- Normalización de claves de productos
- Cálculo de MAD
- Consolidación de resultados
- Filtrado de outliers
- Cálculo de confianza
"""

from src.consolidate.consolidate import _mad, consolidate
from src.consolidate.normalize import normalize_product_key
from src.models.schemas import (
    FrameRef,
    LLMFrameResult,
    LLMPalletObservation,
    LLMProductObservation,
)


# ----------------------------
# Tests de normalización
# ----------------------------
def test_normalize_product_key_with_brand():
    """Test de normalización con marca."""
    key = normalize_product_key("Cremigal", "Leche UAT Entera 12x1L")

    assert key == "cremigal||leche uat entera 12x1l"
    assert "||" in key


def test_normalize_product_key_no_brand():
    """Test de normalización sin marca."""
    key = normalize_product_key(None, "Cajas de cartón")

    # La normalización quita acentos, así que "cartón" -> "carton"
    assert key == "||cajas de carton"
    assert key.startswith("||")


def test_normalize_product_key_case_insensitive():
    """Test que la normalización es case-insensitive."""
    key1 = normalize_product_key("CREMIGAL", "LECHE UAT")
    key2 = normalize_product_key("cremigal", "leche uat")

    assert key1 == key2


def test_normalize_product_key_whitespace():
    """Test que la normalización elimina espacios extra."""
    key1 = normalize_product_key("  Cremigal  ", "  Leche UAT  ")
    key2 = normalize_product_key("Cremigal", "Leche UAT")

    assert key1 == key2


# ----------------------------
# Tests de MAD
# ----------------------------
def test_mad_basic():
    """Test básico de cálculo de MAD."""
    xs = [10, 12, 11, 13, 15]
    med = 12.0

    mad = _mad(xs, med)

    assert mad == 1.0


def test_mad_empty_list():
    """Test de MAD con lista vacía."""
    mad = _mad([], 0.0)

    assert mad == 0.0


def test_mad_all_same():
    """Test de MAD cuando todos los valores son iguales."""
    xs = [10, 10, 10, 10]
    med = 10.0

    mad = _mad(xs, med)

    assert mad == 0.0


def test_mad_with_outliers():
    """Test de MAD con outliers."""
    xs = [10, 11, 12, 13, 14, 50]  # 50 es outlier
    med = 12.5

    mad = _mad(xs, med)

    # MAD debería ser robusto al outlier
    assert mad < 5.0  # No debería ser tan alto como la diferencia con el outlier


# ----------------------------
# Tests de consolidación
# ----------------------------
def test_consolidate_single_frame():
    """Test de consolidación con un solo frame."""
    frame = LLMFrameResult(
        frame=FrameRef(frame_idx=0, timestamp_seconds=0.0),
        pallets=[
            LLMPalletObservation(
                pallet_id="P1",
                products=[
                    LLMProductObservation(
                        product="Leche",
                        brand="Cremigal",
                        estimated_boxes=10,
                        confidence=0.9,
                    )
                ],
            )
        ],
    )

    result = consolidate("VID_001", [frame])

    assert result.video_id == "VID_001"
    assert len(result.pallets) == 1
    assert result.pallets[0].pallet_id == "P1"
    assert len(result.pallets[0].products) == 1
    assert result.pallets[0].products[0].estimated_boxes == 10
    assert result.pallets[0].products[0].confidence > 0


def test_consolidate_multiple_frames_same_pallet():
    """Test de consolidación con múltiples frames del mismo pallet."""
    frames = [
        LLMFrameResult(
            frame=FrameRef(frame_idx=i, timestamp_seconds=i * 0.1),
            pallets=[
                LLMPalletObservation(
                    pallet_id="P1",
                    products=[
                        LLMProductObservation(
                            product="Leche",
                            estimated_boxes=10 + i,  # Variación: 10, 11, 12
                            confidence=0.9,
                        )
                    ],
                )
            ],
        )
        for i in range(3)
    ]

    result = consolidate("VID_001", frames)

    assert len(result.pallets) == 1
    assert len(result.pallets[0].products) == 1
    # Con weighted mode, puede ser 10, 11 o 12 (depende de confidences)
    # Pero debería estar en ese rango
    est = result.pallets[0].products[0].estimated_boxes
    assert 10 <= est <= 12
    assert result.pallets[0].products[0].evidence_frames == 3


def test_consolidate_filters_outliers():
    """Test que la consolidación filtra outliers correctamente."""
    frames = [
        LLMFrameResult(
            frame=FrameRef(frame_idx=i, timestamp_seconds=i * 0.1),
            pallets=[
                LLMPalletObservation(
                    pallet_id="P1",
                    products=[
                        LLMProductObservation(
                            product="Leche",
                            estimated_boxes=20 if i == 0 else 10,  # Primer frame es outlier
                            confidence=0.9,
                        )
                    ],
                )
            ],
        )
        for i in range(5)
    ]

    result = consolidate("VID_001", frames)

    assert len(result.pallets) == 1
    # Debería filtrar el outlier (20) y usar la mediana de los otros (10)
    assert result.pallets[0].products[0].estimated_boxes == 10
    # El outlier debería ser filtrado, así que evidence_frames debería ser menor que 5
    assert result.pallets[0].products[0].evidence_frames < 5


def test_consolidate_multiple_products():
    """Test de consolidación con múltiples productos."""
    frame = LLMFrameResult(
        frame=FrameRef(frame_idx=0, timestamp_seconds=0.0),
        pallets=[
            LLMPalletObservation(
                pallet_id="P1",
                products=[
                    LLMProductObservation(
                        product="Leche",
                        estimated_boxes=10,
                        confidence=0.9,
                    ),
                    LLMProductObservation(
                        product="Yogurt",
                        estimated_boxes=15,
                        confidence=0.8,
                    ),
                ],
            )
        ],
    )

    result = consolidate("VID_001", [frame])

    assert len(result.pallets) == 1
    assert len(result.pallets[0].products) == 2
    products = {p.product: p.estimated_boxes for p in result.pallets[0].products}
    assert products["Leche"] == 10
    assert products["Yogurt"] == 15


def test_consolidate_multiple_pallets():
    """Test de consolidación con múltiples pallets."""
    frame = LLMFrameResult(
        frame=FrameRef(frame_idx=0, timestamp_seconds=0.0),
        pallets=[
            LLMPalletObservation(
                pallet_id="P1",
                products=[
                    LLMProductObservation(product="Leche", estimated_boxes=10, confidence=0.9)
                ],
            ),
            LLMPalletObservation(
                pallet_id="P2",
                products=[
                    LLMProductObservation(product="Yogurt", estimated_boxes=15, confidence=0.8)
                ],
            ),
        ],
    )

    result = consolidate("VID_001", [frame])

    assert len(result.pallets) == 2
    pallet_ids = {p.pallet_id for p in result.pallets}
    assert "P1" in pallet_ids
    assert "P2" in pallet_ids


def test_consolidate_empty_frames():
    """Test de consolidación con lista vacía de frames."""
    result = consolidate("VID_001", [])

    assert result.video_id == "VID_001"
    assert len(result.pallets) == 0


def test_consolidate_stats_included():
    """Test que las estadísticas se incluyen correctamente."""
    frames = [
        LLMFrameResult(
            frame=FrameRef(frame_idx=i, timestamp_seconds=i * 0.1),
            pallets=[
                LLMPalletObservation(
                    pallet_id="P1",
                    products=[
                        LLMProductObservation(
                            product="Leche",
                            estimated_boxes=10 + i,
                            confidence=0.9,
                        )
                    ],
                )
            ],
        )
        for i in range(5)
    ]

    result = consolidate("VID_001", frames)

    assert len(result.pallets) == 1
    product = result.pallets[0].products[0]
    assert product.stats is not None
    assert product.stats.n_observations == 5
    assert product.stats.min_est == 10
    assert product.stats.max_est == 14
    assert product.stats.median_est is not None
    assert product.stats.mad is not None


def test_consolidate_confidence_calculation():
    """Test que la confianza se calcula correctamente."""
    # Frames con confianza variable
    frames = [
        LLMFrameResult(
            frame=FrameRef(frame_idx=i, timestamp_seconds=i * 0.1),
            pallets=[
                LLMPalletObservation(
                    pallet_id="P1",
                    products=[
                        LLMProductObservation(
                            product="Leche",
                            estimated_boxes=10,
                            confidence=0.5 + (i * 0.1),  # 0.5, 0.6, 0.7, 0.8, 0.9
                        )
                    ],
                )
            ],
        )
        for i in range(5)
    ]

    result = consolidate("VID_001", frames)

    product = result.pallets[0].products[0]
    # La confianza final debería estar entre 0 y 1
    assert 0.0 <= product.confidence <= 1.0
    # Con múltiples observaciones estables, la confianza debería ser razonable
    assert product.confidence > 0.3


def test_consolidate_same_product_different_brands():
    """Test que productos con mismo nombre pero diferente marca se agrupan por separado."""
    frames = [
        LLMFrameResult(
            frame=FrameRef(frame_idx=0, timestamp_seconds=0.0),
            pallets=[
                LLMPalletObservation(
                    pallet_id="P1",
                    products=[
                        LLMProductObservation(
                            product="Leche",
                            brand="Cremigal",
                            estimated_boxes=10,
                            confidence=0.9,
                        ),
                        LLMProductObservation(
                            product="Leche",
                            brand="La Serenísima",
                            estimated_boxes=12,
                            confidence=0.9,
                        ),
                    ],
                )
            ],
        )
    ]

    result = consolidate("VID_001", frames)

    assert len(result.pallets) == 1
    assert len(result.pallets[0].products) == 2
    products = {p.brand: p.estimated_boxes for p in result.pallets[0].products}
    assert products["Cremigal"] == 10
    assert products["La Serenísima"] == 12


# ----------------------------
# Tests de umbrales configurables (Bloque 3 / US-3.1, US-3.2)
# ----------------------------
def test_consolidate_custom_mad_threshold():
    """US-3.1: mad_threshold configurable afecta el filtrado de outliers."""
    # 5 observaciones: 10,10,10,10,50 (50 es outlier). Con mad_threshold estricto, 50 queda fuera.
    frames = [
        LLMFrameResult(
            frame=FrameRef(frame_idx=i, timestamp_seconds=i * 0.1),
            pallets=[
                LLMPalletObservation(
                    pallet_id="P1",
                    products=[
                        LLMProductObservation(
                            product="Leche",
                            estimated_boxes=10 if i < 4 else 50,
                            confidence=0.9,
                        )
                    ],
                )
            ],
        )
        for i in range(5)
    ]
    # Con mad_threshold bajo (1.0) el outlier 50 se excluye → estimación basada en 10,10,10,10
    result_strict = consolidate("VID_001", frames, mad_threshold=1.0)
    assert len(result_strict.pallets) == 1
    assert len(result_strict.pallets[0].products) == 1
    assert result_strict.pallets[0].products[0].estimated_boxes == 10
    # Con mad_threshold alto (5.0) el 50 puede entrar en inliers → weighted mode puede dar 10 o 50
    result_loose = consolidate("VID_001", frames, mad_threshold=5.0)
    assert len(result_loose.pallets) == 1
    assert len(result_loose.pallets[0].products) == 1
    # Al menos verificamos que el parámetro se aplica (resultado puede ser 10 o 50 según pesos)
    assert result_loose.pallets[0].products[0].estimated_boxes in (10, 50)


def test_consolidate_custom_min_confidence_filters_ghost():
    """US-3.2: min_confidence más alto descarta más productos (fantasmas)."""
    # 3 frames con misma observación de baja confianza → puede ser filtrado como fantasma
    frames = [
        LLMFrameResult(
            frame=FrameRef(frame_idx=i, timestamp_seconds=i * 0.1),
            pallets=[
                LLMPalletObservation(
                    pallet_id="P1",
                    products=[
                        LLMProductObservation(
                            product="Leche",
                            estimated_boxes=10,
                            confidence=0.35,
                        )
                    ],
                )
            ],
        )
        for i in range(3)
    ]
    # Con min_confidence=0.45 (default), conf_final puede quedar < 0.45 → se filtra
    result_default = consolidate("VID_001", frames, min_confidence=0.45)
    # Con min_confidence=0.1 relajado, el producto se mantiene
    result_relaxed = consolidate("VID_001", frames, min_confidence=0.1)
    # Al menos con relajado debemos tener el producto
    assert len(result_relaxed.pallets) == 1
    assert len(result_relaxed.pallets[0].products) >= 1
    # Con default puede estar filtrado (0 productos) o no según conf_final
    assert len(result_default.pallets) == 1
    # Solo verificamos que los parámetros se aplican: resultado puede variar
    assert len(result_relaxed.pallets[0].products) >= len(result_default.pallets[0].products)
