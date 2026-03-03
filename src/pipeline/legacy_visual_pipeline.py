"""
Legacy visual pipeline (v1.x).

Encapsulates all execution logic: track-based path and frame-based path.
Preserves current behaviour 100%. Used when --mode legacy (or hybrid stub).
"""

import time
from pathlib import Path
from typing import Any

from src.config import Settings
from src.consolidate.consolidate import consolidate
from src.io.logging import log_metrics
from src.io.outputs import (
    frame_results_to_final_result,
    print_summary,
    save_result,
    to_final_result,
)
from src.llm.gemini_client import GeminiClient
from src.models.schemas import FinalResult, PalletEstimate, ProductEstimate
from src.pipeline.orchestrator import run_pipeline
from src.preprocess.selectors import prepare_frames_for_api, select_frames
from src.preprocess.similarity import filter_similar_frames_fast
from src.video.frames import extract_frames
from src.video.ingest import load_video_metadata


class LegacyVisualPipeline:
    """Encapsulates all current execution logic from app (track + frame-based)."""

    def run(
        self,
        video_path: str,
        *,
        settings: Settings,
        video_id: str,
        output_path: Path,
        run_id: str,
        logger: Any,
        args: Any,
    ) -> int:
        """
        Run legacy pipeline. Preserves current behaviour 100%.

        Returns:
            Exit code (0 = success, 1 = error, 2 = validation error, 130 = interrupted).
        """
        start_time = time.time()
        logger.info("📊 Cargando metadata del video...")
        video_metadata = load_video_metadata(video_path)
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

        if getattr(args, "track_pipeline", False):
            return self._run_track_path(
                video_path=video_path,
                settings=settings,
                video_id=video_id,
                output_path=output_path,
                run_id=run_id,
                logger=logger,
                args=args,
            )

        return self._run_frame_path(
            video_path=video_path,
            settings=settings,
            video_id=video_id,
            output_path=output_path,
            run_id=run_id,
            logger=logger,
            args=args,
            start_time=start_time,
        )

    def _run_track_path(
        self,
        video_path: str,
        settings: Settings,
        video_id: str,
        output_path: Path,
        run_id: str,
        logger: Any,
        args: Any,
    ) -> int:
        if getattr(args, "synthetic", False):
            settings = settings.model_copy(update={"use_synthetic_detection": True})
            logger.info("🧪 Modo sintético: 2 bboxes fijos por frame (sin detector real)")
        elif getattr(args, "heuristic", False):
            settings = settings.model_copy(update={"detector_mode": "heuristic"})
            logger.info("🔍 Detector heurístico OpenCV activado (sin ML)")
        if getattr(args, "reid_enabled", False):
            settings = settings.model_copy(update={"reid_enabled": True})
            logger.info("🔗 Re-ID habilitado (Sprint 6B): firma → gating → pHash → CLIP → merge.")
        if getattr(args, "debug_view_selection", False):
            settings = settings.model_copy(update={"debug_view_selection": True})
            logger.info("🔍 Debug de selección de vistas activado (view_selection_debug + manifest reasons).")
        extract_fps = getattr(args, "extract_fps", None) or settings.extract_fps
        logger.info("🛤️  Ejecutando pipeline por tracks (Sprint A)...")
        track_results, summary = run_pipeline(
            video_path,
            video_id=video_id,
            settings=settings,
            output_dir=str(output_path),
            run_id=run_id,
            extract_fps=extract_fps,
            prompt_profile=getattr(args, "prompt_profile", "multi_view_per_track"),
            save_debug_frames=getattr(args, "debug", False),
            save_annotated_views=getattr(args, "save_annotated", False),
        )
        pallets = []
        for track_id, obs in track_results:
            if obs is None:
                continue
            products = [
                ProductEstimate(
                    brand=p.brand,
                    product=p.product,
                    estimated_boxes=p.estimated_boxes,
                    confidence=p.confidence,
                )
                for p in obs.products
            ]
            pallets.append(PalletEstimate(pallet_id=track_id, products=products))
        final_result = FinalResult(
            video_id=video_id,
            pallets=pallets,
            processing_summary={**summary, "track_pipeline": True},
        )
        run_output_dir = output_path / video_id / run_id
        run_output_dir.mkdir(parents=True, exist_ok=True)
        result_file = run_output_dir / "result.json"
        save_result(final_result, str(result_file))
        logger.info("💾 Resultado guardado: %s", result_file)
        logger.info(
            "📊 tracks_detected=%s tracks_ok=%s",
            summary.get("tracks_detected", 0),
            summary.get("tracks_ok", 0),
        )
        if not getattr(args, "no_summary", False):
            print()
            print_summary(final_result)
        logger.info("✅ Procesamiento (track-pipeline) completado")
        return 0

    def _run_frame_path(
        self,
        video_path: str,
        settings: Settings,
        video_id: str,
        output_path: Path,
        run_id: str,
        logger: Any,
        args: Any,
        start_time: float,
    ) -> int:
        extract_fps = getattr(args, "extract_fps", None) or settings.extract_fps
        logger.info("🎬 Extrayendo frames (target_fps=%s)...", extract_fps)
        frames = extract_frames(video_path, target_fps=extract_fps)
        total_frames_estimated = len(frames)
        frame_stride = getattr(args, "frame_stride", None) or settings.frame_stride
        max_frames = getattr(args, "max_frames", None) or settings.max_frames_to_send
        time_limit_sec = getattr(args, "time_limit_sec", None) or settings.time_limit_sec
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

        if getattr(args, "filter_similar", False):
            logger.info(
                "🔍 Filtrando frames similares (threshold=%s)...",
                getattr(args, "similarity_threshold", 0.95),
            )
            start_filter = time.time()
            frames = filter_similar_frames_fast(
                frames,
                video_path,
                similarity_threshold=getattr(args, "similarity_threshold", 0.95),
                sample_size=settings.similarity_sample_size,
            )
            logger.info("✅ Frames después de filtrado: %s", len(frames))
            log_metrics(
                logger,
                "similarity_filter",
                {
                    "frames_after_filter": len(frames),
                    "duration_seconds": time.time() - start_filter,
                },
            )

        strategy = getattr(args, "strategy", "all")
        logger.info("📋 Seleccionando frames (estrategia=%s)...", strategy)
        selected_frames = select_frames(frames, strategy=strategy)
        if frame_stride > 1:
            selected_frames = selected_frames[::frame_stride]
            logger.info("✅ Tras stride=%s: %s frames", frame_stride, len(selected_frames))
        else:
            logger.info("✅ Frames seleccionados: %s", len(selected_frames))
        if time_limit_sec is not None:
            selected_frames = [f for f in selected_frames if f.timestamp_seconds <= time_limit_sec]
            logger.info("✅ Tras time_limit_sec=%s: %s frames", time_limit_sec, len(selected_frames))
        if max_frames is not None and len(selected_frames) > max_frames:
            logger.info(
                "📐 Frames truncados a max_frames=%s (seleccionados: %s)",
                max_frames,
                len(selected_frames),
            )
            selected_frames = selected_frames[:max_frames]

        if not selected_frames:
            logger.error("❌ No hay frames seleccionados para procesar")
            return 1

        logger.info("🖼️  Preprocesando frames...")
        start_preprocess = time.time()
        resize_max_side = getattr(args, "resize_max_side", None) or settings.resize_max_side
        image_paths, run_id_actual = prepare_frames_for_api(
            selected_frames,
            video_path,
            str(output_path),
            resize_max_side=resize_max_side,
            quality=settings.jpeg_quality,
            video_id=video_id,
            run_id=run_id,
            save_frames=getattr(args, "debug", False),
        )
        logger.info("✅ Frames preprocesados: %s", len(image_paths))
        log_metrics(
            logger,
            "preprocessing",
            {
                "frames_preprocessed": len(image_paths),
                "duration_seconds": time.time() - start_preprocess,
            },
        )

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
        prompt_profile = getattr(args, "prompt_profile", "multi_frame_consolidated")
        frame_results = client.analyze_frames(
            selected_frames,
            image_paths,
            prompt_profile=prompt_profile,
        )

        if (
            len(frame_results) == 1
            and not frame_results[0].pallets
            and frame_results[0].raw_text
            and "ERROR" in frame_results[0].raw_text
        ):
            logger.error("❌ Error en análisis LLM: %s", frame_results[0].raw_text)
            return 1

        logger.info("✅ Análisis completado: %s resultados", len(frame_results))
        log_metrics(
            logger,
            "gemini_analysis",
            {
                "frames_analyzed": len(frame_results),
                "duration_seconds": time.time() - start_gemini,
            },
        )

        if getattr(args, "raw_gemini", False):
            logger.info("📋 Modo raw-gemini: omitiendo consolidación")
            processing_summary = {
                "frames_extracted": len(frames),
                "frames_selected": len(selected_frames),
                "frames_analyzed": len(selected_frames),
                "pallets_detected": len(frame_results),
                "total_duration_seconds": time.time() - start_time,
                "extract_fps": extract_fps,
                "strategy": strategy,
                "prompt_profile": prompt_profile,
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
            logger.info("✅ Consolidación completada: %s pallets", len(consolidated.pallets))
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
                "strategy": strategy,
                "prompt_profile": prompt_profile,
            }
            final_result = to_final_result(consolidated, processing_summary=processing_summary)

        run_output_dir = output_path / video_id / run_id_actual
        result_file = run_output_dir / "result.json"
        save_result(final_result, str(result_file))
        logger.info("💾 Resultado guardado: %s", result_file)
        logger.info("📊 frames_processed=%s (inventario completo en este run)", len(selected_frames))

        if not getattr(args, "no_summary", False):
            print()
            print_summary(final_result)

        logger.info("✅ Procesamiento completado exitosamente")
        return 0
