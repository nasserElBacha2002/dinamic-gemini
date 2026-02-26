"""
CLI principal y orquestación del pipeline completo.

Integra todas las fases:
1. Cargar configuración
2. Validar video
3. Extraer frames
4. Seleccionar y preprocesar frames
5. Enviar a Gemini
6. Consolidar resultados
7. Exportar JSON
8. Mostrar resumen
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

from src.config import load_settings
from src.consolidate.consolidate import consolidate
from src.io.logging import log_metrics, setup_logger
from src.io.outputs import (
    frame_results_to_final_result,
    print_summary,
    save_result,
    to_final_result,
)
from src.io.sanitize import sanitize_video_id
from src.llm.gemini_client import GeminiClient
from src.preprocess.selectors import prepare_frames_for_api, select_frames
from src.preprocess.similarity import filter_similar_frames_fast
from src.video.frames import extract_frames
from src.video.ingest import load_video_metadata, validate_video_file


def parse_args() -> argparse.Namespace:
    """Parsea argumentos de línea de comandos.
    
    Returns:
        Namespace con los argumentos parseados.
    """
    parser = argparse.ArgumentParser(
        description="Sistema de inventario por video usando Gemini API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Procesar video con configuración por defecto
  python -m src.app video.mp4

  # Especificar FPS de extracción y video ID
  python -m src.app video.mp4 --video-id VID_001 --extract-fps 0.5

  # Usar filtro de similitud para reducir costos
  python -m src.app video.mp4 --filter-similar --similarity-threshold 0.90

  # Modo debug (guarda frames)
  python -m src.app video.mp4 --debug

  # Procesar todo el video con stride 5 (acelera sin truncar)
  python -m src.app video.mp4 --frame-stride 5

  # Limitar a 200 frames (modo debug/performance)
  python -m src.app video.mp4 --max-frames 200
        """,
    )
    
    # Argumento requerido
    parser.add_argument(
        "video_path",
        type=str,
        help="Ruta al archivo de video a procesar",
    )
    
    # Argumentos opcionales
    parser.add_argument(
        "--video-id",
        type=str,
        default=None,
        help="ID único del video (default: nombre del archivo sin extensión). Caracteres permitidos: letras, números, _, -, .; los espacios se normalizan a _.",
    )
    
    parser.add_argument(
        "--extract-fps",
        type=float,
        default=None,
        help="FPS objetivo para extracción de frames (default: desde config o 0.5)",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        metavar="N",
        help="Máximo de frames a procesar (default: sin límite). Solo para debug/performance.",
    )
    parser.add_argument(
        "--frame-stride",
        type=int,
        default=None,
        metavar="N",
        help="Cada cuántos frames tomar (1 = todos). Default: desde config o 1.",
    )
    parser.add_argument(
        "--time-limit-sec",
        type=float,
        default=None,
        metavar="SEC",
        help="Procesar solo frames con timestamp <= SEC segundos (default: sin límite).",
    )
    parser.add_argument(
        "--strategy",
        type=str,
        choices=["all"],
        default="all",
        help="Selección de frames: 'all' = todos los frames (única opción soportada).",
    )
    
    parser.add_argument(
        "--resize-max-side",
        type=int,
        default=None,
        help="Tamaño máximo del lado más largo para redimensionar (default: desde config o 1280)",
    )
    
    parser.add_argument(
        "--prompt-profile",
        type=str,
        default="multi_frame_consolidated",
        help="Perfil de prompt a usar (default: multi_frame_consolidated)",
    )
    
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directorio de salida (default: desde config o 'output')",
    )
    
    parser.add_argument(
        "--filter-similar",
        action="store_true",
        help="Filtrar frames similares antes de enviar a Gemini",
    )
    
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.95,
        help="Umbral de similitud para filtrar frames (default: 0.95)",
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Modo debug: guarda frames procesados",
    )
    
    parser.add_argument(
        "--raw-gemini",
        action="store_true",
        help="Omitir consolidación: guardar solo lo que devuelve Gemini (un pallet por frame).",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="No mostrar resumen en consola",
    )
    
    return parser.parse_args()


def get_video_id(video_path: str, provided_id: Optional[str]) -> str:
    """Obtiene el ID del video.
    
    Args:
        video_path: Ruta al video.
        provided_id: ID proporcionado por el usuario (opcional).
    
    Returns:
        ID del video a usar.
    """
    if provided_id:
        return provided_id
    
    # Usar nombre del archivo sin extensión
    return Path(video_path).stem


def main() -> int:
    """Función principal del CLI.
    
    Returns:
        Exit code (0 = éxito, >0 = error).
    """
    args = parse_args()
    
    # Cargar configuración
    settings = load_settings()
    
    # Validar video
    video_path = Path(args.video_path)
    if not video_path.exists():
        print(f"❌ Error: Video no encontrado: {video_path}", file=sys.stderr)
        return 1
    
    if not validate_video_file(str(video_path)):
        print(f"❌ Error: Archivo de video inválido: {video_path}", file=sys.stderr)
        return 1
    
    # Obtener video ID y sanitizar para evitar path traversal (Bloque 1 / US-1.1)
    raw_video_id = get_video_id(str(video_path), args.video_id)
    video_id = sanitize_video_id(raw_video_id)
    
    # Configurar directorio de salida
    output_dir = args.output_dir or settings.output_dir
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Generar run_id único
    from datetime import datetime
    import hashlib
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_hash = hashlib.md5(f"{video_id}_{timestamp}".encode()).hexdigest()[:8]
    run_id = f"{timestamp}_{run_hash}"
    
    # Configurar logging (Bloque 4 / US-4.1: log en mismo dir que result.json)
    logger = setup_logger(str(output_path), video_id, run_id, console=True)
    logger.info(f"🚀 Iniciando procesamiento de video: {video_path}")
    logger.info(f"📹 Video ID: {video_id}")
    if raw_video_id != video_id:
        logger.info(f"   (video_id sanitizado desde: {raw_video_id!r})")
    logger.info(f"🆔 Run ID: {run_id}")
    
    try:
        # 1. Cargar metadata del video
        start_time = time.time()
        logger.info("📊 Cargando metadata del video...")
        video_metadata = load_video_metadata(str(video_path))
        logger.info(
            "📐 video_duration=%.1fs fps=%.2f (total_frames se conoce tras extracción)",
            video_metadata.duration_seconds,
            video_metadata.fps,
        )
        log_metrics(
            logger,
            "video_metadata",
            {
                "duration_seconds": video_metadata.duration_seconds,
                "fps": video_metadata.fps,
                "width": video_metadata.width,
                "height": video_metadata.height,
            },
        )
        
        # 2. Extraer frames
        extract_fps = args.extract_fps if args.extract_fps is not None else settings.extract_fps
        logger.info(f"🎬 Extrayendo frames (target_fps={extract_fps})...")
        frames = extract_frames(str(video_path), target_fps=extract_fps)
        total_frames_estimated = len(frames)
        frame_stride = args.frame_stride if args.frame_stride is not None else settings.frame_stride
        max_frames = args.max_frames if args.max_frames is not None else settings.max_frames_to_send
        time_limit_sec = args.time_limit_sec if args.time_limit_sec is not None else settings.time_limit_sec
        logger.info(
            "📐 total_frames_estimated=%s frame_stride=%s max_frames=%s time_limit_sec=%s",
            total_frames_estimated,
            frame_stride,
            max_frames if max_frames is not None else "sin límite",
            time_limit_sec if time_limit_sec is not None else "sin límite",
        )
        log_metrics(
            logger,
            "frame_extraction",
            {
                "frames_extracted": len(frames),
                "total_frames_estimated": total_frames_estimated,
                "frame_stride": frame_stride,
                "max_frames": max_frames,
                "duration_seconds": time.time() - start_time,
            },
        )
        
        if not frames:
            logger.error("❌ No se pudieron extraer frames del video")
            return 1
        
        # 3. Filtrar frames similares (opcional)
        if args.filter_similar:
            logger.info(
                f"🔍 Filtrando frames similares (threshold={args.similarity_threshold})..."
            )
            start_filter = time.time()
            frames = filter_similar_frames_fast(
                frames,
                str(video_path),
                similarity_threshold=args.similarity_threshold,
                sample_size=settings.similarity_sample_size,
            )
            logger.info(f"✅ Frames después de filtrado: {len(frames)}")
            log_metrics(
                logger,
                "similarity_filter",
                {
                    "frames_after_filter": len(frames),
                    "duration_seconds": time.time() - start_filter,
                },
            )
        
        # 4. Seleccionar frames según estrategia
        logger.info(f"📋 Seleccionando frames (estrategia={args.strategy})...")
        selected_frames = select_frames(frames, strategy=args.strategy)
        # Aplicar stride (1 = todos; >1 acelera sin truncar por error)
        if frame_stride > 1:
            selected_frames = selected_frames[::frame_stride]
            logger.info(f"✅ Tras stride={frame_stride}: {len(selected_frames)} frames")
        else:
            logger.info(f"✅ Frames seleccionados: {len(selected_frames)}")
        # Filtrar por tiempo si se definió time_limit_sec
        if time_limit_sec is not None:
            selected_frames = [f for f in selected_frames if f.timestamp_seconds <= time_limit_sec]
            logger.info(f"✅ Tras time_limit_sec={time_limit_sec}: {len(selected_frames)} frames")
        # Límite explícito solo si el usuario lo definió (--max-frames o MAX_FRAMES_TO_SEND)
        if max_frames is not None and len(selected_frames) > max_frames:
            logger.info(
                f"📐 Frames truncados a max_frames={max_frames} (seleccionados: {len(selected_frames)})"
            )
            selected_frames = selected_frames[:max_frames]
        
        if not selected_frames:
            logger.error("❌ No hay frames seleccionados para procesar")
            return 1
        
        # 5. Preprocesar frames (resize, guardar)
        logger.info("🖼️  Preprocesando frames...")
        start_preprocess = time.time()
        resize_max_side = (
            args.resize_max_side
            if args.resize_max_side is not None
            else settings.resize_max_side
        )
        image_paths, run_id_actual = prepare_frames_for_api(
            selected_frames,
            str(video_path),
            str(output_path),
            resize_max_side=resize_max_side,
            quality=settings.jpeg_quality,
            video_id=video_id,
            run_id=run_id,
            save_frames=args.debug,
        )
        logger.info(f"✅ Frames preprocesados: {len(image_paths)}")
        log_metrics(
            logger,
            "preprocessing",
            {
                "frames_preprocessed": len(image_paths),
                "duration_seconds": time.time() - start_preprocess,
            },
        )
        
        # 6. Enviar a Gemini
        logger.info("🤖 Enviando frames a Gemini API...")
        start_gemini = time.time()
        
        if not settings.gemini_api_key:
            logger.error("❌ GEMINI_API_KEY no configurada")
            return 1
        
        client = GeminiClient(
            api_key=settings.gemini_api_key,
            model_name=settings.gemini_model_name,
            max_retries=settings.gemini_max_retries,
            retry_delay=settings.gemini_retry_delay,
        )
        
        frame_results = client.analyze_frames(
            selected_frames,
            image_paths,
            prompt_profile=args.prompt_profile,
        )

        # Bloque 6 / US-6.2: fallar el proceso si Gemini devolvió error (ej. carga de imágenes)
        if (
            len(frame_results) == 1
            and not frame_results[0].pallets
            and frame_results[0].raw_text
            and "ERROR" in frame_results[0].raw_text
        ):
            logger.error("❌ Error en análisis LLM: %s", frame_results[0].raw_text)
            return 1
        
        logger.info(f"✅ Análisis completado: {len(frame_results)} resultados")
        log_metrics(
            logger,
            "gemini_analysis",
            {
                "frames_analyzed": len(frame_results),
                "duration_seconds": time.time() - start_gemini,
            },
        )
        
        # 7. Consolidar o usar resultado crudo de Gemini
        if args.raw_gemini:
            logger.info("📋 Modo raw-gemini: omitiendo consolidación")
            processing_summary = {
                "frames_extracted": len(frames),
                "frames_selected": len(selected_frames),
                "frames_analyzed": len(selected_frames),
                "pallets_detected": len(frame_results),  # un pallet por frame
                "total_duration_seconds": time.time() - start_time,
                "extract_fps": extract_fps,
                "strategy": args.strategy,
                "prompt_profile": args.prompt_profile,
                "raw_gemini": True,
            }
            final_result = frame_results_to_final_result(
                frame_results, video_id=video_id, processing_summary=processing_summary
            )
        else:
            logger.info("📊 Consolidando resultados...")
            start_consolidate = time.time()
            consolidated = consolidate(
                video_id=video_id,
                frame_results=frame_results,
                n_target=len(selected_frames),
                mad_threshold=settings.consolidation_mad_threshold,
                min_evidence_frames=settings.consolidation_min_evidence_frames,
                min_confidence=settings.consolidation_min_confidence,
            )
            logger.info(
                f"✅ Consolidación completada: {len(consolidated.pallets)} pallets"
            )
            log_metrics(
                logger,
                "consolidation",
                {
                    "pallets_consolidated": len(consolidated.pallets),
                    "duration_seconds": time.time() - start_consolidate,
                },
            )
            processing_summary = {
                "frames_extracted": len(frames),
                "frames_selected": len(selected_frames),
                "frames_analyzed": len(selected_frames),
                "pallets_detected": len(consolidated.pallets),
                "total_duration_seconds": time.time() - start_time,
                "extract_fps": extract_fps,
                "strategy": args.strategy,
                "prompt_profile": args.prompt_profile,
            }
            final_result = to_final_result(consolidated, processing_summary=processing_summary)
        
        # 9. Guardar resultado
        run_output_dir = output_path / video_id / run_id_actual
        result_file = run_output_dir / "result.json"
        save_result(final_result, str(result_file))
        logger.info(f"💾 Resultado guardado: {result_file}")
        logger.info("📊 frames_processed=%s (inventario completo en este run)", len(selected_frames))
        
        # 10. Mostrar resumen
        if not args.no_summary:
            print()
            print_summary(final_result)
        
        logger.info("✅ Procesamiento completado exitosamente")
        return 0
        
    except KeyboardInterrupt:
        logger.warning("⚠️  Procesamiento interrumpido por el usuario")
        return 130
    except Exception as e:
        logger.exception(f"❌ Error durante el procesamiento: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
