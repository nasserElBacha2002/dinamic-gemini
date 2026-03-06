"""
CLI principal. Thin entrypoint: parse args, validate, delegate to pipeline.
"""

import argparse
import hashlib
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import load_settings
from src.io.logging import setup_logger
from src.io.sanitize import sanitize_video_id
from src.pipeline.hybrid_inventory_pipeline import HybridInventoryPipeline
from src.video.ingest import validate_video_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sistema de inventario por video usando Gemini API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python -m src.app video.mp4
  python -m src.app video.mp4 --video-id VID_001 --extract-fps 0.5
  python -m src.app video.mp4 --track-pipeline --heuristic
  python -m src.app video.mp4 --mode hybrid
        """,
    )
    parser.add_argument("video_path", type=str, help="Ruta al archivo de video a procesar")
    parser.add_argument("--video-id", type=str, default=None, help="ID único del video (default: nombre del archivo sin extensión).")
    parser.add_argument("--extract-fps", type=float, default=None, help="FPS objetivo para extracción de frames.")
    parser.add_argument("--max-frames", type=int, default=None, metavar="N", help="Máximo de frames a procesar.")
    parser.add_argument("--frame-stride", type=int, default=None, metavar="N", help="Cada cuántos frames tomar (1 = todos).")
    parser.add_argument("--time-limit-sec", type=float, default=None, metavar="SEC", help="Procesar solo frames con timestamp <= SEC segundos.")
    parser.add_argument("--strategy", type=str, default="all", help="Selección de frames (actualmente solo 'all' soportado).")
    parser.add_argument("--resize-max-side", type=int, default=None, help="Tamaño máximo del lado más largo para redimensionar.")
    parser.add_argument("--prompt-profile", type=str, default="multi_frame_consolidated", help="Perfil de prompt a usar.")
    parser.add_argument("--output-dir", type=str, default=None, help="Directorio de salida.")
    parser.add_argument("--filter-similar", action="store_true", help="Filtrar frames similares antes de enviar a Gemini.")
    parser.add_argument("--similarity-threshold", type=float, default=0.95, help="Umbral de similitud para filtrar frames.")
    parser.add_argument("--debug", action="store_true", help="Modo debug: guarda frames procesados.")
    parser.add_argument("--raw-gemini", action="store_true", help="Omitir consolidación: guardar solo lo que devuelve Gemini.")
    parser.add_argument("--track-pipeline", action="store_true", help="Pipeline por tracks (detección → tracking → 1 request por track).")
    parser.add_argument("--synthetic", action="store_true", help="Con --track-pipeline: 2 bboxes fijos por frame.")
    parser.add_argument("--heuristic", action="store_true", help="Con --track-pipeline: detector heurístico OpenCV.")
    parser.add_argument("--save-annotated", action="store_true", help="Con --track-pipeline: guardar ROIs y frames anotados.")
    parser.add_argument("--reid-enabled", action="store_true", help="Sprint 6B: activar Re-ID. Requiere --track-pipeline.")
    parser.add_argument("--debug-view-selection", action="store_true", help="Debug de selección de vistas. Requiere --track-pipeline.")
    parser.add_argument("--no-summary", action="store_true", help="No mostrar resumen en consola")
    parser.add_argument(
        "--mode",
        type=str,
        choices=["hybrid"],
        default="hybrid",
        help="Modo de ejecución (v2.2: solo hybrid).",
    )
    return parser.parse_args()


def get_video_id(video_path: str, provided_id: Optional[str]) -> str:
    if provided_id:
        return provided_id
    return Path(video_path).stem


def main() -> int:
    args = parse_args()
    settings = load_settings()

    video_path = Path(args.video_path)
    if not video_path.exists():
        print(f"❌ Error: Video no encontrado: {video_path}", file=sys.stderr)
        return 1
    if not validate_video_file(str(video_path)):
        print(f"❌ Error: Archivo de video inválido: {video_path}", file=sys.stderr)
        return 1
    if getattr(args, "reid_enabled", False) and not getattr(args, "track_pipeline", False):
        print("❌ Error: --reid-enabled requiere --track-pipeline.", file=sys.stderr)
        return 2

    raw_video_id = get_video_id(str(video_path), args.video_id)
    video_id = sanitize_video_id(raw_video_id)
    output_dir = args.output_dir or settings.output_dir
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_hash = hashlib.md5(f"{video_id}_{timestamp}".encode()).hexdigest()[:8]
    run_id = f"{timestamp}_{run_hash}"

    logger = setup_logger(str(output_path), video_id, run_id, console=True)
    logger.info("🚀 Iniciando procesamiento de video: %s", video_path)
    logger.info("📹 Video ID: %s", video_id)
    if raw_video_id != video_id:
        logger.info("   (video_id sanitizado desde: %r)", raw_video_id)
    logger.info("🆔 Run ID: %s", run_id)
    logger.info("🔀 Modo: %s", args.mode)

    try:
        pipeline = HybridInventoryPipeline()
        return pipeline.process_video(
            str(video_path),
            mode=args.mode,
            settings=settings,
            video_id=video_id,
            output_path=output_path,
            run_id=run_id,
            logger=logger,
            args=args,
        )
    except KeyboardInterrupt:
        logger.warning("⚠️  Procesamiento interrumpido por el usuario")
        return 130
    except Exception as e:
        logger.exception("❌ Error durante el procesamiento: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
