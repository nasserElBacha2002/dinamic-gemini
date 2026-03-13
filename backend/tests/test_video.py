"""
Tests unitarios para el módulo de video.

Verifica:
- Carga de metadata de video
- Validación de archivos
- Extracción de frames
- Manejo de errores
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from src.models.schemas import FrameRef, VideoMetadata
from src.video.frames import extract_frames, extract_frames_uniform
from src.video.ingest import load_video_metadata, validate_video_file


# ----------------------------
# Tests de ingest.py
# ----------------------------
def test_load_video_metadata_file_not_found():
    """Test que se lanza error si el archivo no existe."""
    with pytest.raises(FileNotFoundError):
        load_video_metadata("/path/that/does/not/exist.mp4")


def test_load_video_metadata_invalid_format():
    """Test que se lanza error si el formato no es soportado."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        tmp_path = tmp.name
    
    try:
        with pytest.raises(ValueError, match="Formato de video no soportado"):
            load_video_metadata(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_load_video_metadata_success():
    """Test de carga exitosa de metadata (mock de OpenCV)."""
    # Crear un video temporal de prueba usando OpenCV
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name
    
    try:
        # Crear un video simple con OpenCV
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(tmp_path, fourcc, 30.0, (640, 480))
        
        # Escribir algunos frames
        for i in range(90):  # 3 segundos a 30 fps
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            frame[:] = (i % 255, (i * 2) % 255, (i * 3) % 255)
            out.write(frame)
        
        out.release()
        
        # Cargar metadata
        metadata = load_video_metadata(tmp_path, video_id="TEST_VID")
        
        assert isinstance(metadata, VideoMetadata)
        assert metadata.video_id == "TEST_VID"
        assert metadata.fps > 0
        assert metadata.duration_seconds > 0
        assert metadata.width == 640
        assert metadata.height == 480
        assert Path(metadata.file_path).exists()
    
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_load_video_metadata_auto_id():
    """Test que se genera video_id automáticamente si no se proporciona."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name
    
    try:
        # Crear video simple
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(tmp_path, fourcc, 30.0, (640, 480))
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        out.write(frame)
        out.release()
        
        # Cargar sin video_id
        metadata = load_video_metadata(tmp_path)
        
        # El video_id debería ser el nombre del archivo sin extensión
        expected_id = Path(tmp_path).stem
        assert metadata.video_id == expected_id
    
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_validate_video_file_valid():
    """Test de validación de archivo válido."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name
    
    try:
        # Crear video simple
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(tmp_path, fourcc, 30.0, (640, 480))
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        out.write(frame)
        out.release()
        
        assert validate_video_file(tmp_path) is True
    
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_validate_video_file_not_found():
    """Test de validación de archivo inexistente."""
    assert validate_video_file("/path/that/does/not/exist.mp4") is False


def test_validate_video_file_invalid():
    """Test de validación de archivo inválido."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        tmp_path = tmp.name
        tmp.write(b"not a video")
    
    try:
        assert validate_video_file(tmp_path) is False
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ----------------------------
# Tests de frames.py
# ----------------------------
def test_extract_frames_invalid_target_fps():
    """Test que se lanza error si target_fps es inválido."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name
    
    try:
        # Crear video simple
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(tmp_path, fourcc, 30.0, (640, 480))
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        out.write(frame)
        out.release()
        
        with pytest.raises(ValueError):
            extract_frames(tmp_path, target_fps=0)
        
        with pytest.raises(ValueError):
            extract_frames(tmp_path, target_fps=-1)
    
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_extract_frames_success():
    """Test de extracción exitosa de frames."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name
    
    try:
        # Crear video de 3 segundos a 30 fps (90 frames)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(tmp_path, fourcc, 30.0, (640, 480))
        
        for i in range(90):
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            frame[:] = (i % 255, 0, 0)
            out.write(frame)
        
        out.release()
        
        # Extraer a 1 fps (debería dar ~3 frames)
        frames = extract_frames(tmp_path, target_fps=1.0)
        
        assert len(frames) > 0
        assert all(isinstance(f, FrameRef) for f in frames)
        
        # Verificar que los frames tienen metadata correcta
        for frame in frames:
            assert frame.frame_idx >= 0
            assert frame.timestamp_seconds >= 0
            assert frame.width == 640
            assert frame.height == 480
        
        # Verificar que los timestamps son crecientes
        timestamps = [f.timestamp_seconds for f in frames]
        assert timestamps == sorted(timestamps)
    
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_extract_frames_high_target_fps():
    """Test de extracción con target_fps alto (debería extraer más frames)."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name
    
    try:
        # Crear video de 1 segundo a 30 fps (30 frames)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(tmp_path, fourcc, 30.0, (640, 480))
        
        for i in range(30):
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            out.write(frame)
        
        out.release()
        
        # Extraer a 10 fps (debería dar ~10 frames)
        frames_10fps = extract_frames(tmp_path, target_fps=10.0)
        
        # Extraer a 1 fps (debería dar ~1 frame)
        frames_1fps = extract_frames(tmp_path, target_fps=1.0)
        
        assert len(frames_10fps) > len(frames_1fps)
    
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_extract_frames_uniform_invalid_max_frames():
    """Test que se lanza error si max_frames es inválido."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name
    
    try:
        # Crear video simple
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(tmp_path, fourcc, 30.0, (640, 480))
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        out.write(frame)
        out.release()
        
        with pytest.raises(ValueError):
            extract_frames_uniform(tmp_path, max_frames=0)
        
        with pytest.raises(ValueError):
            extract_frames_uniform(tmp_path, max_frames=-1)
    
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_extract_frames_uniform_success():
    """Test de extracción uniforme exitosa."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name
    
    try:
        # Crear video de 3 segundos a 30 fps (90 frames)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(tmp_path, fourcc, 30.0, (640, 480))
        
        for i in range(90):
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            out.write(frame)
        
        out.release()
        
        # Extraer 10 frames uniformemente distribuidos
        frames = extract_frames_uniform(tmp_path, max_frames=10)
        
        assert len(frames) == 10
        assert all(isinstance(f, FrameRef) for f in frames)
        
        # Verificar que están distribuidos uniformemente
        frame_indices = [f.frame_idx for f in frames]
        assert frame_indices == sorted(frame_indices)
        
        # Verificar que el primer frame es 0 (o start_frame)
        assert frames[0].frame_idx == 0
    
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_extract_frames_uniform_with_start():
    """Test de extracción uniforme con start_frame."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name
    
    try:
        # Crear video de 3 segundos a 30 fps (90 frames)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(tmp_path, fourcc, 30.0, (640, 480))
        
        for i in range(90):
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            out.write(frame)
        
        out.release()
        
        # Extraer 5 frames empezando desde el frame 30
        frames = extract_frames_uniform(tmp_path, max_frames=5, start_frame=30)
        
        assert len(frames) <= 5
        if len(frames) > 0:
            assert frames[0].frame_idx >= 30
    
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_extract_frames_empty_video():
    """Test de extracción de frames de video vacío."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name
    
    try:
        # Crear video vacío (solo header)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(tmp_path, fourcc, 30.0, (640, 480))
        out.release()
        
        # OpenCV puede no poder leer videos sin frames, esto es esperado
        # Intentar extraer frames - puede fallar o retornar lista vacía
        try:
            frames = extract_frames(tmp_path, target_fps=1.0)
            # Si no falla, debería retornar lista vacía
            assert isinstance(frames, list)
            assert len(frames) == 0
        except RuntimeError:
            # Es válido que falle si el video no tiene frames
            pass
    
    finally:
        Path(tmp_path).unlink(missing_ok=True)
