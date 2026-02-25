"""
Tests unitarios para el módulo I/O.

Verifica:
- Conversión de ConsolidatedResult a FinalResult
- Guardado de resultados en JSON
- Impresión de resumen
- Configuración de logging
"""

import json
import logging
import tempfile
from pathlib import Path

import pytest

from src.io.logging import log_metrics, setup_logger
from src.io.outputs import print_summary, save_result, save_result_json, to_final_result
from src.models.schemas import (
    ConsolidatedPallet,
    ConsolidatedProduct,
    ConsolidatedResult,
    FinalResult,
    PalletEstimate,
    ProductEstimate,
)


# ----------------------------
# Tests de outputs
# ----------------------------
def test_to_final_result_basic():
    """Test básico de conversión a FinalResult."""
    consolidated = ConsolidatedResult(
        video_id="VID_001",
        pallets=[
            ConsolidatedPallet(
                pallet_id="P1",
                products=[
                    ConsolidatedProduct(
                        product="Leche",
                        brand="Cremigal",
                        estimated_boxes=10,
                        confidence=0.9,
                        evidence_frames=3,
                    )
                ],
            )
        ],
    )
    
    final = to_final_result(consolidated)
    
    assert isinstance(final, FinalResult)
    assert final.video_id == "VID_001"
    assert len(final.pallets) == 1
    assert final.pallets[0].pallet_id == "P1"
    assert len(final.pallets[0].products) == 1
    assert final.pallets[0].products[0].product == "Leche"
    assert final.pallets[0].products[0].estimated_boxes == 10
    assert final.pallets[0].products[0].confidence == 0.9


def test_to_final_result_with_summary():
    """Test de conversión con processing_summary."""
    consolidated = ConsolidatedResult(
        video_id="VID_001",
        pallets=[],
    )
    
    summary = {"frames_processed": 10, "duration_seconds": 5.2}
    final = to_final_result(consolidated, processing_summary=summary)
    
    assert final.processing_summary == summary


def test_to_final_result_multiple_pallets():
    """Test de conversión con múltiples pallets."""
    consolidated = ConsolidatedResult(
        video_id="VID_001",
        pallets=[
            ConsolidatedPallet(
                pallet_id="P1",
                products=[
                    ConsolidatedProduct(
                        product="Leche",
                        estimated_boxes=10,
                        confidence=0.9,
                        evidence_frames=3,
                    )
                ],
            ),
            ConsolidatedPallet(
                pallet_id="P2",
                products=[
                    ConsolidatedProduct(
                        product="Yogurt",
                        estimated_boxes=15,
                        confidence=0.8,
                        evidence_frames=2,
                    )
                ],
            ),
        ],
    )
    
    final = to_final_result(consolidated)
    
    assert len(final.pallets) == 2
    pallet_ids = {p.pallet_id for p in final.pallets}
    assert "P1" in pallet_ids
    assert "P2" in pallet_ids


def test_save_result_json():
    """Test de guardado de resultado en JSON."""
    result = FinalResult(
        video_id="VID_001",
        pallets=[
            PalletEstimate(
                pallet_id="P1",
                products=[
                    ProductEstimate(
                        product="Leche",
                        brand="Cremigal",
                        estimated_boxes=10,
                        confidence=0.9,
                    )
                ],
            )
        ],
    )
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "result.json"
        save_result_json(result, str(output_path))
        
        assert output_path.exists()
        
        # Verificar contenido
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        assert data["video_id"] == "VID_001"
        assert len(data["pallets"]) == 1
        assert data["pallets"][0]["pallet_id"] == "P1"


def test_save_result_json_creates_directory():
    """Test que save_result_json crea el directorio si no existe."""
    result = FinalResult(video_id="VID_001", pallets=[])
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "subdir" / "result.json"
        save_result_json(result, str(output_path))
        
        assert output_path.exists()
        assert output_path.parent.exists()


def test_save_result():
    """Test de save_result (alias de save_result_json)."""
    result = FinalResult(video_id="VID_001", pallets=[])
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "result.json"
        saved_path = save_result(result, str(output_path))
        
        assert saved_path == output_path
        assert output_path.exists()


def test_print_summary(capsys):
    """Test de impresión de resumen."""
    result = FinalResult(
        video_id="VID_001",
        pallets=[
            PalletEstimate(
                pallet_id="P1",
                products=[
                    ProductEstimate(
                        product="Leche",
                        brand="Cremigal",
                        estimated_boxes=10,
                        confidence=0.9,
                    ),
                    ProductEstimate(
                        product="Yogurt",
                        estimated_boxes=15,
                        confidence=0.8,
                    ),
                ],
            )
        ],
    )
    
    print_summary(result)
    captured = capsys.readouterr()
    
    assert "VID_001" in captured.out
    assert "P1" in captured.out
    assert "Leche" in captured.out
    assert "Yogurt" in captured.out
    assert "10 cajas" in captured.out
    assert "15 cajas" in captured.out
    assert "Total de cajas: 25" in captured.out


def test_print_summary_with_processing_summary(capsys):
    """Test de impresión de resumen con processing_summary."""
    result = FinalResult(
        video_id="VID_001",
        pallets=[],
        processing_summary={"frames_processed": 10, "duration_seconds": 5.2},
    )
    
    print_summary(result)
    captured = capsys.readouterr()
    
    assert "Resumen de Procesamiento" in captured.out
    assert "frames_processed" in captured.out or "10" in captured.out


# ----------------------------
# Tests de logging
# ----------------------------
def test_setup_logger():
    """Test de configuración de logger."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = setup_logger(tmpdir, "test_run", console=False)
        
        assert isinstance(logger, logging.Logger)
        assert logger.name.startswith("dinamic_gemini_")
        assert logger.level == logging.INFO


def test_setup_logger_creates_log_file():
    """Test que setup_logger crea el archivo de log."""
    import uuid
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Usar run_id único para evitar conflictos
        run_id = f"test_run_{uuid.uuid4().hex[:8]}"
        logger = setup_logger(tmpdir, run_id, console=False)
        logger.info("Test message")
        
        # Forzar flush y cerrar handlers
        for handler in logger.handlers:
            handler.flush()
            handler.close()
        
        log_file = Path(tmpdir) / run_id / "processing.log"
        assert log_file.exists()
        
        # Verificar contenido
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        assert "Test message" in content


def test_setup_logger_console():
    """Test que setup_logger puede escribir a consola."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = setup_logger(tmpdir, "test_run", console=True)
        
        # Debería tener al menos 1 handler (archivo), y si console=True, también consola
        assert len(logger.handlers) >= 1
        # Verificar que hay un StreamHandler (consola)
        has_console = any(
            isinstance(h, logging.StreamHandler) for h in logger.handlers
        )
        assert has_console


def test_log_metrics():
    """Test de logging de métricas."""
    import uuid
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Usar run_id único para evitar conflictos
        run_id = f"test_run_{uuid.uuid4().hex[:8]}"
        logger = setup_logger(tmpdir, run_id, console=False)
        
        log_metrics(logger, "frame_extraction", {"frames_extracted": 10, "duration": 2.5})
        
        # Forzar flush y cerrar handlers
        for handler in logger.handlers:
            handler.flush()
            handler.close()
        
        log_file = Path(tmpdir) / run_id / "processing.log"
        assert log_file.exists()
        
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        assert "[frame_extraction]" in content
        assert "frames_extracted=10" in content
        assert "duration=2.5" in content
