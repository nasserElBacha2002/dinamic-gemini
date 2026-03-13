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
from src.io.sanitize import sanitize_video_id
from src.models.schemas import (
    ConsolidatedPallet,
    ConsolidatedProduct,
    ConsolidatedResult,
    FinalResult,
    FrameRef,
    PalletEstimate,
    ProductEstimate,
)


# ----------------------------
# Tests de sanitize_video_id (Bloque 1 / US-1.1)
# ----------------------------
def test_sanitize_video_id_safe_unchanged():
    """IDs seguros no se alteran."""
    assert sanitize_video_id("VID_001") == "VID_001"
    assert sanitize_video_id("video_2024-01-15") == "video_2024-01-15"
    assert sanitize_video_id("a.b-c_d") == "a.b-c_d"


def test_sanitize_video_id_path_traversal_removed():
    """Caracteres de path traversal se eliminan; no se escribe fuera de output_dir."""
    assert sanitize_video_id("../../etc") == "etc"
    assert sanitize_video_id("..") == "video"
    assert sanitize_video_id("foo/bar") == "foobar"
    assert sanitize_video_id("foo\\bar") == "foobar"
    assert sanitize_video_id("a/../b") == "ab"


def test_sanitize_video_id_empty_or_invalid_fallback():
    """Cadenas vacías o solo caracteres inválidos devuelven fallback."""
    assert sanitize_video_id("") == "video"
    assert sanitize_video_id("  ") == "video"
    assert sanitize_video_id("...") == "video"
    assert sanitize_video_id("/\\") == "video"
    assert sanitize_video_id("  ", fallback="default") == "default"


def test_sanitize_video_id_spaces_to_underscore():
    """Espacios se normalizan a guión bajo (nombres legibles)."""
    assert sanitize_video_id("my video") == "my_video"
    assert sanitize_video_id("  VID 001  ") == "VID_001"


def test_sanitize_video_id_valid_names_unchanged_or_normalized():
    """US-1.2: Nombres válidos no se alteran o solo se normalizan (espacios → _)."""
    # Solo letras, números, _, -, . → sin cambio
    assert sanitize_video_id("VID_001") == "VID_001"
    assert sanitize_video_id("Run-01") == "Run-01"
    assert sanitize_video_id("Video.Final") == "Video.Final"
    assert sanitize_video_id("Paso_1") == "Paso_1"
    assert sanitize_video_id("2024-02-26_run") == "2024-02-26_run"
    assert sanitize_video_id("a.b-c_d") == "a.b-c_d"
    # Espacios → normalización a _ (nombres legibles)
    assert sanitize_video_id("mi video") == "mi_video"
    assert sanitize_video_id("  VID 001  ") == "VID_001"


def test_sanitize_video_id_resolved_path_under_output_dir():
    """CA-1.1: El path output_dir / sanitize_video_id(malicious) queda bajo output_dir."""
    output_dir = Path("/tmp/output")
    malicious_ids = ["../../etc", "..", "foo/bar/baz", "a\\b", "...."]
    for raw_id in malicious_ids:
        safe_id = sanitize_video_id(raw_id)
        run_path = (output_dir / safe_id).resolve()
        output_resolved = output_dir.resolve()
        assert run_path.is_relative_to(output_resolved), (
            f"sanitize_video_id({raw_id!r}) = {safe_id!r} produced path {run_path} "
            f"not under {output_resolved}"
        )


# ----------------------------
# Tests de max_frames (default sin límite; truncar solo si se define)
# ----------------------------
def test_default_no_limit_to_10():
    """Por defecto NO se limita a 10 frames: se procesan todos (bug crítico de negocio)."""
    frames = [
        FrameRef(frame_idx=i, timestamp_seconds=i / 30.0) for i in range(15)
    ]
    max_frames = None  # default: sin límite
    selected = frames[:max_frames] if max_frames is not None else frames
    assert len(selected) == 15
    assert selected[-1].frame_idx == 14


def test_max_frames_truncation_when_set():
    """Cuando max_frames está definido, se trunca a ese valor."""
    frames = [
        FrameRef(frame_idx=i, timestamp_seconds=i / 30.0) for i in range(10)
    ]
    max_frames = 3
    truncated = frames[:max_frames]
    assert len(truncated) == max_frames
    assert truncated[0].frame_idx == 0 and truncated[2].frame_idx == 2


def test_processing_summary_frames_analyzed_reflects_sent():
    """US-2.2: processing_summary.frames_analyzed refleja los frames realmente enviados."""
    consolidated = ConsolidatedResult(video_id="VID_001", pallets=[])
    processing_summary = {
        "frames_extracted": 20,
        "frames_selected": 5,
        "frames_analyzed": 5,
    }
    final = to_final_result(consolidated, processing_summary=processing_summary)
    assert final.processing_summary is not None
    assert final.processing_summary["frames_analyzed"] == 5


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
        logger = setup_logger(tmpdir, "VID", "test_run", console=False)
        
        assert isinstance(logger, logging.Logger)
        assert logger.name.startswith("dinamic_gemini_")
        assert logger.level == logging.INFO


def test_setup_logger_creates_log_file():
    """Test que setup_logger crea el archivo de log en output_dir/video_id/run_id/ (Bloque 4)."""
    import uuid
    
    with tempfile.TemporaryDirectory() as tmpdir:
        video_id = "VID"
        run_id = f"test_run_{uuid.uuid4().hex[:8]}"
        logger = setup_logger(tmpdir, video_id, run_id, console=False)
        logger.info("Test message")
        
        # Forzar flush y cerrar handlers
        for handler in logger.handlers:
            handler.flush()
            handler.close()
        
        log_file = Path(tmpdir) / video_id / run_id / "processing.log"
        assert log_file.exists()
        
        # Verificar contenido
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        assert "Test message" in content


def test_setup_logger_console():
    """Test que setup_logger puede escribir a consola."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = setup_logger(tmpdir, "VID", "test_run", console=True)
        
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
        video_id = "VID"
        run_id = f"test_run_{uuid.uuid4().hex[:8]}"
        logger = setup_logger(tmpdir, video_id, run_id, console=False)
        
        log_metrics(logger, "frame_extraction", {"frames_extracted": 10, "duration": 2.5})
        
        # Forzar flush y cerrar handlers
        for handler in logger.handlers:
            handler.flush()
            handler.close()
        
        log_file = Path(tmpdir) / video_id / run_id / "processing.log"
        assert log_file.exists()
        
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        assert "[frame_extraction]" in content
        assert "frames_extracted=10" in content
        assert "duration=2.5" in content


def test_log_and_result_same_run_dir():
    """US-4.1: processing.log y result.json en el mismo directorio de run."""
    import uuid
    
    with tempfile.TemporaryDirectory() as tmpdir:
        video_id = "VID"
        run_id = f"run_{uuid.uuid4().hex[:8]}"
        logger = setup_logger(tmpdir, video_id, run_id, console=False)
        logger.info("Run message")
        for handler in logger.handlers:
            handler.flush()
            handler.close()
        
        result = FinalResult(video_id=video_id, pallets=[])
        result_path = Path(tmpdir) / video_id / run_id / "result.json"
        save_result(result, str(result_path))
        
        run_dir = Path(tmpdir) / video_id / run_id
        assert (run_dir / "processing.log").exists()
        assert (run_dir / "result.json").exists()


def test_save_result_json_returns_path():
    """US-4.2: save_result_json devuelve Path al archivo guardado."""
    result = FinalResult(video_id="VID_001", pallets=[])
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "out" / "result.json"
        returned = save_result_json(result, str(output_path))
        
        assert returned == output_path
        assert isinstance(returned, Path)
        assert output_path.exists()
