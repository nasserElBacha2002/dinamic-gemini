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
from src.io.outputs import print_summary, save_result, to_final_result
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
        help="ID único del video (default: nombre del archivo sin extensión)",
    )
    
    parser.add_argument(
        "--extract-fps",
        type=float,
        default=None,
        help="FPS objetivo para extracción de frames (default: desde config o 0.5)",
    )
    
    parser.add_argument(
        "--strategy",
        type=str,
        choices=["uniform", "first_n", "distributed", "all"],
        default="all",
        help="Estrategia de selección de frames (default: all)",
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
    
    # Obtener video ID
    video_id = get_video_id(str(video_path), args.video_id)
    
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
    
    # Configurar logging
    logger = setup_logger(str(output_path), run_id, console=True)
    logger.info(f"🚀 Iniciando procesamiento de video: {video_path}")
    logger.info(f"📹 Video ID: {video_id}")
    logger.info(f"🆔 Run ID: {run_id}")
    
    try:
        # 1. Cargar metadata del video
        start_time = time.time()
        logger.info("📊 Cargando metadata del video...")
        video_metadata = load_video_metadata(str(video_path))
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
        logger.info(f"✅ Frames extraídos: {len(frames)}")
        log_metrics(
            logger,
            "frame_extraction",
            {
                "frames_extracted": len(frames),
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
                frames, str(video_path), similarity_threshold=args.similarity_threshold
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
        logger.info(f"✅ Frames seleccionados: {len(selected_frames)}")
        
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
        )
        
        frame_results = client.analyze_frames(
            selected_frames,
            image_paths,
            prompt_profile=args.prompt_profile,
        )
        
        logger.info(f"✅ Análisis completado: {len(frame_results)} resultados")
        log_metrics(
            logger,
            "gemini_analysis",
            {
                "frames_analyzed": len(frame_results),
                "duration_seconds": time.time() - start_gemini,
            },
        )
        
        # 7. Consolidar resultados
        logger.info("📊 Consolidando resultados...")
        start_consolidate = time.time()
        consolidated = consolidate(
            video_id=video_id,
            frame_results=frame_results,
            n_target=len(selected_frames),
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
        
        # 8. Convertir a formato final
        processing_summary = {
            "frames_extracted": len(frames),
            "frames_selected": len(selected_frames),
            "frames_analyzed": len(frame_results),
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
