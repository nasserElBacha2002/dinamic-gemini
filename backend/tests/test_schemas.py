"""
Tests unitarios para los modelos Pydantic (schemas).

Verifica:
- Creación de modelos válidos
- Validación de campos
- Serialización JSON
- Validadores personalizados (confianza)
"""

import pytest
from pydantic import ValidationError

from src.models.schemas import (
    clamp01,
    MinifiedProduct,
    MinifiedPallet,
    MinifiedFrameResult,
    VideoMetadata,
    FrameRef,
    ProductEstimate,
    PalletEstimate,
    FinalResult,
    LLMProductObservation,
    LLMPalletObservation,
    LLMFrameResult,
    ConsolidationStats,
    ConsolidatedProduct,
    ConsolidatedPallet,
    ConsolidatedResult,
)


# ----------------------------
# Tests de helpers
# ----------------------------
def test_clamp01():
    """Test de la función clamp01."""
    assert clamp01(0.5) == 0.5
    assert clamp01(0.0) == 0.0
    assert clamp01(1.0) == 1.0
    assert clamp01(-0.5) == 0.0
    assert clamp01(1.5) == 1.0
    assert clamp01(2.0) == 1.0


# ----------------------------
# Tests de modelos minificados
# ----------------------------
def test_minified_product_valid():
    """Test de creación de MinifiedProduct válido."""
    product = MinifiedProduct(n="Leche UAT", r="12×7=84", q=84, c=0.93, b="Cremigal")
    assert product.n == "Leche UAT"
    assert product.q == 84
    assert product.c == 0.93
    assert product.b == "Cremigal"


def test_minified_product_confidence_clamp():
    """Test de validación de confianza en MinifiedProduct."""
    # Confianza dentro del rango válido
    product1 = MinifiedProduct(n="Test", r="counted", q=10, c=0.95)
    assert product1.c == 0.95
    
    # Confianza en los límites
    product2 = MinifiedProduct(n="Test", r="counted", q=10, c=0.0)
    assert product2.c == 0.0
    
    product3 = MinifiedProduct(n="Test", r="counted", q=10, c=1.0)
    assert product3.c == 1.0
    
    # Valores fuera de rango son rechazados por Pydantic antes del validador
    # (esto es el comportamiento esperado: validación estricta)
    with pytest.raises(ValidationError):
        MinifiedProduct(n="Test", r="x", q=10, c=1.5)
    
    with pytest.raises(ValidationError):
        MinifiedProduct(n="Test", r="x", q=10, c=-0.1)


def test_minified_product_negative_boxes():
    """Test que no permite cantidad negativa de cajas."""
    with pytest.raises(ValidationError):
        MinifiedProduct(n="Test", r="x", q=-1, c=0.5)


def test_minified_pallet_valid():
    """Test de creación de MinifiedPallet válido."""
    products = [
        MinifiedProduct(n="Producto 1", r="a", q=50, c=0.9),
        MinifiedProduct(n="Producto 2", r="b", q=30, c=0.85),
    ]
    pallet = MinifiedPallet(id="PALLET_001", p=products)
    assert pallet.id == "PALLET_001"
    assert len(pallet.p) == 2


def test_minified_frame_result_valid():
    """Test de creación de MinifiedFrameResult válido."""
    products = [MinifiedProduct(n="Producto", r="z", q=10, c=0.8)]
    pallets = [MinifiedPallet(id="P001", p=products)]
    result = MinifiedFrameResult(pallets=pallets)
    assert len(result.pallets) == 1


# ----------------------------
# Tests de metadata
# ----------------------------
def test_video_metadata_valid():
    """Test de creación de VideoMetadata válido."""
    metadata = VideoMetadata(
        video_id="VID_001",
        file_path="/path/to/video.mp4",
        duration_seconds=120.5,
        fps=30.0,
        width=1920,
        height=1080,
    )
    assert metadata.video_id == "VID_001"
    assert metadata.duration_seconds == 120.5
    assert metadata.fps == 30.0


def test_video_metadata_negative_values():
    """Test que no permite valores negativos o cero."""
    with pytest.raises(ValidationError):
        VideoMetadata(
            video_id="VID_001",
            file_path="/path/to/video.mp4",
            duration_seconds=-1.0,
            fps=30.0,
            width=1920,
            height=1080,
        )


def test_frame_ref_valid():
    """Test de creación de FrameRef válido."""
    frame = FrameRef(
        frame_idx=100,
        timestamp_seconds=3.33,
        image_path="/path/to/frame.jpg",
        width=1920,
        height=1080,
    )
    assert frame.frame_idx == 100
    assert frame.timestamp_seconds == 3.33
    assert frame.image_path == "/path/to/frame.jpg"


def test_frame_ref_optional_fields():
    """Test de FrameRef con campos opcionales."""
    frame = FrameRef(frame_idx=0, timestamp_seconds=0.0)
    assert frame.image_path is None
    assert frame.width is None
    assert frame.height is None


# ----------------------------
# Tests de modelos de salida
# ----------------------------
def test_product_estimate_valid():
    """Test de creación de ProductEstimate válido."""
    product = ProductEstimate(
        brand="Cremigal",
        product="Leche UAT Entera 12x1L",
        estimated_boxes=84,
        confidence=0.93,
    )
    assert product.brand == "Cremigal"
    assert product.estimated_boxes == 84
    assert product.confidence == 0.93


def test_product_estimate_confidence_clamp():
    """Test de validación de confianza en ProductEstimate."""
    # Confianza dentro del rango válido
    product = ProductEstimate(product="Test", estimated_boxes=10, confidence=0.85)
    assert product.confidence == 0.85
    
    # Valores fuera de rango son rechazados por Pydantic
    with pytest.raises(ValidationError):
        ProductEstimate(product="Test", estimated_boxes=10, confidence=2.0)
    
    with pytest.raises(ValidationError):
        ProductEstimate(product="Test", estimated_boxes=10, confidence=-0.1)


def test_pallet_estimate_valid():
    """Test de creación de PalletEstimate válido."""
    products = [
        ProductEstimate(product="Producto 1", estimated_boxes=50, confidence=0.9),
    ]
    pallet = PalletEstimate(pallet_id="PALLET_001", products=products)
    assert pallet.pallet_id == "PALLET_001"
    assert len(pallet.products) == 1


def test_final_result_valid():
    """Test de creación de FinalResult válido."""
    products = [
        ProductEstimate(product="Producto", estimated_boxes=10, confidence=0.8),
    ]
    pallets = [PalletEstimate(pallet_id="P001", products=products)]
    result = FinalResult(video_id="VID_001", pallets=pallets)
    assert result.video_id == "VID_001"
    assert len(result.pallets) == 1
    assert result.processing_summary is None


def test_final_result_with_summary():
    """Test de FinalResult con processing_summary."""
    products = [ProductEstimate(product="Test", estimated_boxes=10, confidence=0.8)]
    pallets = [PalletEstimate(pallet_id="P001", products=products)]
    summary = {"frames_processed": 10, "time_seconds": 5.5}
    result = FinalResult(
        video_id="VID_001", pallets=pallets, processing_summary=summary
    )
    assert result.processing_summary == summary


# ----------------------------
# Tests de modelos LLM
# ----------------------------
def test_llm_product_observation_valid():
    """Test de creación de LLMProductObservation válido."""
    obs = LLMProductObservation(
        product="Leche UAT",
        brand="Cremigal",
        estimated_boxes=84,
        confidence=0.93,
    )
    assert obs.product == "Leche UAT"
    assert obs.estimated_boxes == 84


def test_llm_pallet_observation_valid():
    """Test de creación de LLMPalletObservation válido."""
    products = [
        LLMProductObservation(product="Producto", estimated_boxes=10, confidence=0.8),
    ]
    pallet = LLMPalletObservation(pallet_id="P001", products=products)
    assert pallet.pallet_id == "P001"
    assert len(pallet.products) == 1


def test_llm_frame_result_valid():
    """Test de creación de LLMFrameResult válido."""
    frame = FrameRef(frame_idx=0, timestamp_seconds=0.0)
    products = [
        LLMProductObservation(product="Test", estimated_boxes=10, confidence=0.8),
    ]
    pallets = [LLMPalletObservation(pallet_id="P001", products=products)]
    result = LLMFrameResult(
        frame=frame,
        pallets=pallets,
        raw_text='{"pallets": []}',
        model_name="gemini-2.0-flash",
    )
    assert result.frame == frame
    assert len(result.pallets) == 1
    assert result.raw_text == '{"pallets": []}'
    assert result.model_name == "gemini-2.0-flash"


# ----------------------------
# Tests de modelos de consolidación
# ----------------------------
def test_consolidation_stats_valid():
    """Test de creación de ConsolidationStats válido."""
    stats = ConsolidationStats(
        n_observations=5,
        min_est=10,
        max_est=20,
        median_est=15.0,
        mad=2.5,
    )
    assert stats.n_observations == 5
    assert stats.median_est == 15.0
    assert stats.mad == 2.5


def test_consolidated_product_valid():
    """Test de creación de ConsolidatedProduct válido."""
    stats = ConsolidationStats(n_observations=3, min_est=10, max_est=12, median_est=11.0)
    product = ConsolidatedProduct(
        product="Leche UAT",
        brand="Cremigal",
        estimated_boxes=11,
        confidence=0.88,
        evidence_frames=3,
        stats=stats,
    )
    assert product.product == "Leche UAT"
    assert product.evidence_frames == 3
    assert product.stats == stats


def test_consolidated_pallet_valid():
    """Test de creación de ConsolidatedPallet válido."""
    products = [
        ConsolidatedProduct(
            product="Test", estimated_boxes=10, confidence=0.8, evidence_frames=2
        ),
    ]
    pallet = ConsolidatedPallet(pallet_id="P001", products=products)
    assert pallet.pallet_id == "P001"
    assert len(pallet.products) == 1


def test_consolidated_result_valid():
    """Test de creación de ConsolidatedResult válido."""
    products = [
        ConsolidatedProduct(
            product="Test", estimated_boxes=10, confidence=0.8, evidence_frames=2
        ),
    ]
    pallets = [ConsolidatedPallet(pallet_id="P001", products=products)]
    result = ConsolidatedResult(video_id="VID_001", pallets=pallets)
    assert result.video_id == "VID_001"
    assert len(result.pallets) == 1


# ----------------------------
# Tests de serialización JSON
# ----------------------------
def test_minified_product_json_serialization():
    """Test de serialización JSON de MinifiedProduct."""
    product = MinifiedProduct(n="Test", r="ok", q=10, c=0.8, b="Brand")
    json_data = product.model_dump()
    assert json_data["n"] == "Test"
    assert json_data["r"] == "ok"
    assert json_data["q"] == 10
    assert json_data["c"] == 0.8
    assert json_data["b"] == "Brand"


def test_final_result_json_serialization():
    """Test de serialización JSON de FinalResult."""
    products = [
        ProductEstimate(product="Test", estimated_boxes=10, confidence=0.8),
    ]
    pallets = [PalletEstimate(pallet_id="P001", products=products)]
    result = FinalResult(video_id="VID_001", pallets=pallets)
    json_data = result.model_dump()
    assert json_data["video_id"] == "VID_001"
    assert len(json_data["pallets"]) == 1
    assert json_data["pallets"][0]["pallet_id"] == "P001"


# ----------------------------
# Tests de validación extra="forbid"
# ----------------------------
def test_extra_fields_forbidden():
    """Test que los modelos rechazan campos extra."""
    with pytest.raises(ValidationError):
        MinifiedProduct(n="Test", r="x", q=10, c=0.8, extra_field="not_allowed")
    
    with pytest.raises(ValidationError):
        FinalResult(
            video_id="VID_001",
            pallets=[],
            extra_field="not_allowed",
        )
