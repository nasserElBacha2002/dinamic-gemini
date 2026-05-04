"""
Tests unitarios para el módulo de preprocesamiento.

Verifica:
- Redimensionado de imágenes
- Aplicación de ROI
- Compresión de imágenes
- Guardado y carga de frames
- Selección de frames
- Preparación de frames para API
"""

import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.models.schemas import FrameRef
from src.preprocess.image_ops import (
    apply_roi,
    compress_image,
    extract_frame_from_video,
    load_frame,
    resize_image,
    save_frame,
)
from src.preprocess.selectors import prepare_frames_for_api, select_frames
from src.preprocess.similarity import filter_similar_frames_fast


# ----------------------------
# Tests de image_ops.py
# ----------------------------
def test_resize_image_smaller():
    """Test que no redimensiona si la imagen ya es más pequeña."""
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    resized = resize_image(frame, max_side=200)

    assert resized.shape == frame.shape
    assert np.array_equal(resized, frame)


def test_resize_image_larger():
    """Test de redimensionado cuando la imagen es más grande."""
    frame = np.zeros((2000, 1000, 3), dtype=np.uint8)
    resized = resize_image(frame, max_side=1280)

    # El lado más largo debería ser 1280
    h, w = resized.shape[:2]
    assert max(h, w) == 1280

    # Debería mantener aspect ratio
    original_ratio = 2000 / 1000
    new_ratio = h / w
    assert abs(original_ratio - new_ratio) < 0.01


def test_resize_image_portrait():
    """Test de redimensionado de imagen vertical."""
    frame = np.zeros((2000, 500, 3), dtype=np.uint8)
    resized = resize_image(frame, max_side=1280)

    h, w = resized.shape[:2]
    assert h == 1280
    assert w < 1280


def test_resize_image_landscape():
    """Test de redimensionado de imagen horizontal."""
    frame = np.zeros((500, 2000, 3), dtype=np.uint8)
    resized = resize_image(frame, max_side=1280)

    h, w = resized.shape[:2]
    assert w == 1280
    assert h < 1280


def test_resize_image_invalid_max_side():
    """Test que se lanza error si max_side es inválido."""
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    with pytest.raises(ValueError):
        resize_image(frame, max_side=0)

    with pytest.raises(ValueError):
        resize_image(frame, max_side=-1)


def test_resize_image_empty_frame():
    """Test que se lanza error si el frame está vacío."""
    frame = np.array([])

    with pytest.raises(ValueError):
        resize_image(frame, max_side=1280)


def test_apply_roi_valid():
    """Test de aplicación de ROI válida."""
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[10:30, 20:40] = 255  # Marcar región

    roi = (20, 10, 20, 20)  # x, y, width, height
    cropped = apply_roi(frame, roi)

    assert cropped.shape == (20, 20, 3)
    assert np.all(cropped == 255)


def test_apply_roi_invalid():
    """Test que se lanza error si ROI es inválida."""
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    # ROI fuera de límites
    with pytest.raises(ValueError):
        apply_roi(frame, (0, 0, 200, 100))

    # Coordenadas negativas
    with pytest.raises(ValueError):
        apply_roi(frame, (-1, 0, 50, 50))

    # Dimensiones inválidas
    with pytest.raises(ValueError):
        apply_roi(frame, (0, 0, 0, 50))


def test_compress_image():
    """Test de compresión de imagen."""
    frame = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)

    compressed = compress_image(frame, quality=85)

    assert isinstance(compressed, bytes)
    assert len(compressed) > 0


def test_compress_image_invalid_quality():
    """Test que se lanza error si quality es inválido."""
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    with pytest.raises(ValueError):
        compress_image(frame, quality=150)

    with pytest.raises(ValueError):
        compress_image(frame, quality=-1)


def test_save_and_load_frame():
    """Test de guardado y carga de frame."""
    with tempfile.TemporaryDirectory() as tmpdir:
        frame = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        output_path = Path(tmpdir) / "test_frame.jpg"

        # Guardar
        saved_path = save_frame(frame, str(output_path), quality=85)
        assert Path(saved_path).exists()

        # Cargar
        loaded = load_frame(saved_path)
        assert loaded.shape == frame.shape
        # Nota: JPEG es lossy, así que no podemos comparar exactamente
        assert loaded.dtype == frame.dtype


def test_save_frame_creates_directory():
    """Test que save_frame crea el directorio si no existe."""
    with tempfile.TemporaryDirectory() as tmpdir:
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        output_path = Path(tmpdir) / "new_dir" / "test_frame.jpg"

        # El directorio no existe
        assert not output_path.parent.exists()

        # Guardar debería crear el directorio
        save_frame(frame, str(output_path))

        assert output_path.exists()
        assert output_path.parent.exists()


def test_load_frame_not_found():
    """Test que se lanza error si el archivo no existe."""
    with pytest.raises(FileNotFoundError):
        load_frame("/path/that/does/not/exist.jpg")


def test_extract_frame_from_video():
    """Test de extracción de frame específico de video."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Crear video simple
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(tmp_path, fourcc, 30.0, (640, 480))

        # Escribir frames con colores diferentes
        for i in range(10):
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            frame[:] = (i * 25, 0, 0)  # Diferente color por frame
            out.write(frame)

        out.release()

        # Extraer frame específico
        frame = extract_frame_from_video(tmp_path, frame_idx=5)

        assert frame is not None
        assert frame.shape == (480, 640, 3)

    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ----------------------------
# Tests de selectors.py
# ----------------------------
def test_select_frames_all():
    """Test de selección de todos los frames (default)."""
    frames = [FrameRef(frame_idx=i, timestamp_seconds=i * 0.1) for i in range(20)]

    selected = select_frames(frames, strategy="all")

    assert len(selected) == 20
    assert len(selected) == len(frames)
    assert selected[0].frame_idx == 0
    assert selected[-1].frame_idx == 19


def test_select_frames_empty():
    """Test con lista vacía."""
    selected = select_frames([], strategy="all")

    assert len(selected) == 0


def test_select_frames_invalid_strategy():
    """Test que se lanza error si strategy no es 'all' (Bloque 8)."""
    frames = [FrameRef(frame_idx=i, timestamp_seconds=i * 0.1) for i in range(10)]
    with pytest.raises(ValueError, match="Única estrategia válida: 'all'"):
        select_frames(frames, strategy="invalid")


def test_prepare_frames_for_api():
    """Test de preparación de frames para API."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_video:
        video_path = tmp_video.name

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            # Crear video simple
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            out = cv2.VideoWriter(video_path, fourcc, 30.0, (640, 480))

            for i in range(10):
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                out.write(frame)

            out.release()

            # Crear referencias a frames
            frames = [
                FrameRef(frame_idx=i, timestamp_seconds=i * 0.1, width=640, height=480)
                for i in range(5)
            ]

            # Preparar frames
            image_paths, run_id = prepare_frames_for_api(
                frames, video_path, tmpdir, resize_max_side=320, video_id="TEST"
            )

            assert len(image_paths) == 5
            assert all(Path(p).exists() for p in image_paths)
            assert run_id is not None
            assert len(run_id) > 0

            # Verificar que las imágenes se guardaron en el directorio correcto
            # Estructura: tmpdir/TEST/<run_id>/frames/
            run_dir = Path(tmpdir) / "TEST" / run_id
            frames_dir = run_dir / "frames"
            assert frames_dir.exists()
            assert len(list(frames_dir.glob("*.jpg"))) == 5

        finally:
            Path(video_path).unlink(missing_ok=True)


def test_prepare_frames_for_api_empty():
    """Test con lista vacía de frames."""
    image_paths, run_id = prepare_frames_for_api([], "video.mp4", "output")

    assert len(image_paths) == 0
    assert run_id == ""


# ----------------------------
# Tests de similarity (Bloque 5: una apertura de video)
# ----------------------------
def test_filter_similar_frames_fast_single_open():
    """Bloque 5 / US-5.1: filter_similar_frames_fast abre el video una sola vez."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_video:
        video_path = tmp_video.name

    try:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(video_path, fourcc, 30.0, (64, 64))
        for i in range(15):
            frame = np.zeros((64, 64, 3), dtype=np.uint8)
            frame[:] = (i * 10 % 255, 0, 0)
            out.write(frame)
        out.release()

        frames = [FrameRef(frame_idx=i, timestamp_seconds=i / 30.0) for i in range(0, 15, 2)]
        filtered = filter_similar_frames_fast(
            frames, video_path, similarity_threshold=0.95, sample_size=32
        )
        assert len(filtered) >= 1
        assert len(filtered) <= len(frames)
        assert all(f.frame_idx in (fr.frame_idx for fr in frames) for f in filtered)
    finally:
        Path(video_path).unlink(missing_ok=True)
