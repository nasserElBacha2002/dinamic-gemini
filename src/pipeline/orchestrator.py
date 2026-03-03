"""
Orquestador del pipeline track-based (Sprint A).

Ejecuta: extraer frames → detectar → track → ROI → blur → seleccionar vistas → Gemini por track.
"""

import json
import logging
import time
from datetime import datetime
from itertools import groupby
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2

from src.config import Settings
from src.detection.pallet_detector import detect_pallets_per_frame
from src.llm.gemini_client import GeminiClient
from src.models.schemas import (
    BBox,
    LLMPalletObservation,
    PalletObservation,
    PalletTrack,
)
from src.preprocess.image_ops import read_frame_at
from src.roi.cropper import crop_roi
from src.roi.quality import calculate_blur_score
from src.tracking.track_builder import build_pallet_tracks
from src.tracking.tracker import MultiObjectTracker
from src.video.frames import extract_frames
from src.video.ingest import load_video_metadata
from src.view_selection.selector import select_views_per_track
from src.reid import run_reid_pipeline

logger = logging.getLogger(__name__)


def run_pipeline(
    video_path: str,
    video_id: str,
    settings: Settings,
    output_dir: str,
    run_id: str,
    extract_fps: float = 1.0,
    prompt_profile: str = "multi_view_per_track",
    save_debug_frames: bool = False,
    save_annotated_views: bool = False,
) -> Tuple[List[Tuple[str, Optional[LLMPalletObservation]]], Dict[str, Any]]:
    """Ejecuta el pipeline track-based (Sprint A).

    Args:
        video_path: Ruta al video.
        video_id: ID del video.
        settings: Configuración (detection, tracking, ROI, view selection).
        output_dir: Directorio base de salida (para ROIs si se guardan).
        run_id: ID de la ejecución.
        extract_fps: FPS para extracción de frames.
        prompt_profile: Perfil de prompt para Gemini.
        save_debug_frames: Si True, guarda los frames extraídos en output/.../debug_frames/.
        save_annotated_views: Si True, guarda ROIs anotados (borde + track_id/frame_idx) en rois_annotated/ y frames con bboxes en debug_frames_annotated/.

    Returns:
        (track_results, processing_summary): Lista de (track_id, pallet_obs o None) y resumen.
    """
    start_time = time.time()
    metadata = load_video_metadata(video_path)
    video_fps = metadata.fps
    detector_mode = "synthetic" if settings.use_synthetic_detection else (settings.detector_mode or "stub").strip().lower()
    if detector_mode not in ("stub", "heuristic", "synthetic"):
        detector_mode = "stub"

    # 1. Extraer referencias de frames
    frame_refs = extract_frames(video_path, target_fps=extract_fps)
    if not frame_refs:
        logger.warning("No se extrajeron frames")
        return [], _make_summary(
            0, 0, 0, 0, 0, start_time,
            pipeline_debug={"frame_count": 0, "frame_indices": [], "detector_mode": detector_mode, "detections_per_frame": [], "prompt_profile": prompt_profile},
        )
    if detector_mode == "stub" and not settings.use_synthetic_detection:
        logger.warning(
            "Detector en modo stub: no hay detecciones reales. Use DETECTOR_MODE=heuristic o --synthetic para obtener tracks."
        )

    run_dir = Path(output_dir) / video_id / run_id
    debug_frames_dir = (run_dir / "debug_frames") if save_debug_frames else None
    if debug_frames_dir is not None:
        debug_frames_dir.mkdir(parents=True, exist_ok=True)

    # 2. Detección + tracking (frame a frame)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"No se pudo abrir el video: {video_path}")
    tracker = MultiObjectTracker(
        min_hits=settings.tracker_min_hits,
        max_age=settings.tracker_max_age,
    )
    detections_per_frame: List[int] = []
    frame_indices_used: List[int] = []
    try:
        for ref in frame_refs:
            frame = read_frame_at(cap, ref.frame_idx)
            if frame is None:
                continue
            frame_indices_used.append(ref.frame_idx)
            detections: List[BBox] = detect_pallets_per_frame(
                frame,
                conf_threshold=settings.detection_conf_threshold,
                use_synthetic=settings.use_synthetic_detection,
                settings=settings,
            )
            detections_per_frame.append(len(detections))
            tracker.update(detections, ref.frame_idx)
            if save_debug_frames and debug_frames_dir is not None:
                out_path = debug_frames_dir / f"frame_{ref.frame_idx:06d}.jpg"
                cv2.imwrite(str(out_path), frame)
    finally:
        cap.release()

    tracked_data = tracker.get_tracks()
    tracks = build_pallet_tracks(tracked_data, video_fps=video_fps)
    tracks_detected = len(tracks)

    pipeline_debug: Dict[str, Any] = {
        "frame_count": len(frame_indices_used),
        "frame_indices": frame_indices_used,
        "detector_mode": detector_mode,
        "detections_per_frame": detections_per_frame,
        "prompt_profile": prompt_profile,
    }
    if save_debug_frames and debug_frames_dir is not None:
        pipeline_debug["debug_frames_dir"] = str(debug_frames_dir)

    det_summary = detections_per_frame if len(detections_per_frame) <= 15 else detections_per_frame[:10] + detections_per_frame[-3:]
    logger.info(
        "Pipeline analizó: frames=%d, índices (muestra)=%s, detector=%s, detecciones_por_frame=%s, tracks=%d",
        len(frame_indices_used),
        frame_indices_used[:5] if len(frame_indices_used) > 5 else frame_indices_used,
        detector_mode,
        det_summary,
        tracks_detected,
    )
    if detector_mode != "stub" and detections_per_frame:
        max_consecutive_zeros = max(
            (sum(1 for _ in g) for z, g in groupby(detections_per_frame) if z == 0),
            default=0,
        )
        if max_consecutive_zeros >= 5:
            logger.warning(
                "Detector %s: %d frames consecutivos con 0 detecciones. Revisar parámetros heurística o iluminación.",
                detector_mode,
                max_consecutive_zeros,
            )
    if not tracks:
        logger.info(
            "No se detectaron tracks (detector=%s devuelve %s detecciones).",
            detector_mode,
            "todas 0" if all(n == 0 for n in detections_per_frame) else detections_per_frame,
        )
        if detector_mode == "stub":
            logger.warning(
                "Para obtener tracks sin YOLO use: --heuristic (CLI) o DETECTOR_MODE=heuristic (env). Para pruebas use --synthetic."
            )
        return [], _make_summary(
            len(frame_refs), 0, 0, 0, 0, start_time,
            pipeline_debug=pipeline_debug,
        )

    # 3. ROI + blur por observación (re-abrir video para leer frames)
    cap2 = cv2.VideoCapture(video_path)
    if not cap2.isOpened():
        raise RuntimeError(f"No se pudo reabrir el video: {video_path}")
    roi_base = Path(output_dir) / video_id / run_id / "rois"
    roi_base.mkdir(parents=True, exist_ok=True)
    roi_annotated_base = (run_dir / "rois_annotated") if save_annotated_views else None
    if roi_annotated_base is not None:
        roi_annotated_base.mkdir(parents=True, exist_ok=True)
    updated_tracks: List[PalletTrack] = []
    try:
        for track in tracks:
            new_observations: List[PalletObservation] = []
            for obs in track.observations:
                frame = read_frame_at(cap2, obs.frame_idx)
                if frame is None:
                    new_observations.append(obs)
                    continue
                try:
                    roi_array, path_out = crop_roi(
                        obs.bbox,
                        frame,
                        padding_pct=settings.roi_padding_pct,
                        max_side=settings.roi_max_side,
                        quality=settings.roi_jpeg_quality,
                        output_path=str(roi_base / f"{track.track_id}_frame{obs.frame_idx}.jpg"),
                    )
                    blur = calculate_blur_score(roi_array)
                    if save_annotated_views and roi_annotated_base is not None and roi_array.size > 0:
                        roi_ann = roi_array.copy()
                        h, w = roi_ann.shape[:2]
                        cv2.rectangle(roi_ann, (0, 0), (w - 1, h - 1), (0, 255, 0), 2)
                        label = f"{track.track_id} f{obs.frame_idx}"
                        cv2.putText(
                            roi_ann, label, (5, min(25, h - 5)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA,
                        )
                        ann_path = roi_annotated_base / f"{track.track_id}_frame{obs.frame_idx}.jpg"
                        cv2.imwrite(str(ann_path), roi_ann)
                    new_observations.append(
                        obs.model_copy(update={"roi_path": path_out, "blur_score": blur})
                    )
                except Exception as e:
                    logger.debug("ROI/blur fallo para track %s frame %s: %s", track.track_id, obs.frame_idx, e)
                    new_observations.append(obs)
            updated_tracks.append(
                track.model_copy(update={"observations": new_observations})
            )
    finally:
        cap2.release()
    tracks = updated_tracks

    # 3b. Re-ID (Sprint 6B): opcional después de ROI+blur, antes de view selection
    if getattr(settings, "reid_enabled", False):
        tracks, reid_metrics = run_reid_pipeline(
            tracks,
            settings,
            video_width=getattr(metadata, "width", None),
            video_height=getattr(metadata, "height", None),
        )
        pipeline_debug.update(reid_metrics)
        logger.info(
            "Re-ID pipeline: tracks_before_reid=%s tracks_after_reid=%s tracks_merged_count=%s candidates=%s pairs_after_phash=%s pairs_confirmed=%s",
            reid_metrics.get("tracks_before_reid"),
            reid_metrics.get("tracks_after_reid"),
            reid_metrics.get("tracks_merged_count"),
            reid_metrics.get("reid_candidates_generated"),
            reid_metrics.get("reid_pairs_after_phash"),
            reid_metrics.get("reid_pairs_confirmed"),
        )
    else:
        reid_metrics = None

    # Frames anotados (bbox + track_id por frame) para auditoría
    if save_annotated_views:
        frame_to_boxes: Dict[int, List[Tuple[Tuple[int, int, int, int], str]]] = {}
        for track in tracks:
            for obs in track.observations:
                frame_to_boxes.setdefault(obs.frame_idx, []).append((obs.bbox, track.track_id))
        debug_ann_dir = run_dir / "debug_frames_annotated"
        debug_ann_dir.mkdir(parents=True, exist_ok=True)
        cap3 = cv2.VideoCapture(video_path)
        if cap3.isOpened():
            try:
                for frame_idx in sorted(frame_to_boxes.keys()):
                    frame = read_frame_at(cap3, frame_idx)
                    if frame is None:
                        continue
                    frame_ann = frame.copy()
                    for (x1, y1, x2, y2), tid in frame_to_boxes[frame_idx]:
                        cv2.rectangle(frame_ann, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv2.putText(
                            frame_ann, str(tid), (x1, max(y1 - 5, 20)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 1, cv2.LINE_AA,
                        )
                    out_path = debug_ann_dir / f"frame_{frame_idx:06d}.jpg"
                    cv2.imwrite(str(out_path), frame_ann)
            finally:
                cap3.release()

    # 4. Selección de vistas por track + manifiesto de auditoría
    manifests_dir = run_dir / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    views_selected_total = 0
    track_results: List[Tuple[str, Optional[LLMPalletObservation]]] = []
    client = GeminiClient(
        api_key=settings.gemini_api_key,
        model_name=settings.gemini_model_name,
        max_retries=settings.gemini_max_retries,
        retry_delay=settings.gemini_retry_delay,
    )

    def _bbox_area(bbox: Tuple[int, int, int, int]) -> float:
        return float(max(0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])))

    if getattr(settings, "debug_view_selection", False):
        pipeline_debug["view_selection_debug"] = {}

    tracks_with_min_views = 0
    tracks_requests_sent = 0
    tracks_llm_ok = 0
    tracks_llm_failed = 0

    for track in tracks:
        view_selection_debug: Optional[Dict[str, Any]] = None
        views, view_selection_debug = select_views_per_track(
            track,
            min_views=settings.min_views,
            target_views=settings.target_views,
            max_views=settings.max_views,
            blur_percentile=settings.view_selection_blur_percentile,
            min_frame_gap_diversity=settings.view_selection_min_frame_gap_diversity,
            max_iou_suppress=settings.view_selection_max_iou_suppress,
            frame_width=getattr(metadata, "width", None),
            frame_height=getattr(metadata, "height", None),
            enable_diversity=getattr(settings, "view_selection_enable_diversity", True),
            phash_near_dup_thr=getattr(settings, "view_selection_phash_near_dup_thr", 4),
            centroid_near_dup_thr=getattr(settings, "view_selection_centroid_near_dup_thr", 0.03),
            anchor_window_frames=getattr(settings, "view_selection_anchor_window_frames", 15),
            diversity_weight=getattr(settings, "view_selection_diversity_weight", 0.35),
            return_debug=getattr(settings, "debug_view_selection", False),
        )
        if view_selection_debug is not None and pipeline_debug.get("view_selection_debug") is not None:
            pipeline_debug["view_selection_debug"][track.track_id] = view_selection_debug
        views_set = set(id(o) for o in views)
        all_observations = []
        selected_by_frame: Dict[int, Dict[str, Any]] = {}
        if view_selection_debug and "selected" in view_selection_debug:
            for s in view_selection_debug["selected"]:
                selected_by_frame[s["frame_idx"]] = s
        candidates_by_frame: Dict[int, Dict[str, Any]] = {}
        if view_selection_debug and "candidates" in view_selection_debug:
            for c in view_selection_debug["candidates"]:
                candidates_by_frame[c["frame_idx"]] = c
        for o in track.observations:
            selected = id(o) in views_set
            reason = "selected" if selected else "discarded"
            metrics: Optional[Dict[str, Any]] = None
            if view_selection_debug:
                if o.frame_idx in selected_by_frame:
                    s = selected_by_frame[o.frame_idx]
                    reason = s.get("reason", reason)
                    metrics = {k: v for k, v in s.items() if k in ("min_phash_dist_to_selected", "min_centroid_dist_to_selected", "min_frame_gap_to_selected")}
                elif o.frame_idx in candidates_by_frame:
                    c = candidates_by_frame[o.frame_idx]
                    reason = "discarded"
                    metrics = {"base_score": c.get("base_score"), "blur": c.get("blur"), "area": c.get("area"), "centroid": c.get("centroid"), "phash": c.get("phash")}
            ob_dict: Dict[str, Any] = {
                "frame_idx": o.frame_idx,
                "bbox": list(o.bbox),
                "roi_path": o.roi_path,
                "blur_score": o.blur_score,
                "area": _bbox_area(o.bbox),
                "selected": selected,
                "selection_reason": reason,
            }
            if metrics is not None:
                ob_dict["selection_metrics"] = metrics
            all_observations.append(ob_dict)
        roi_paths = [o.roi_path for o in views if o.roi_path]
        views_selected_total += len(roi_paths)

        track_invalid_reason: Optional[str] = None
        if len(roi_paths) < settings.min_views:
            track_invalid_reason = "insufficient_views"
        elif len(track.observations) < settings.min_views:
            track_invalid_reason = "insufficient_observations"
        else:
            areas = [_bbox_area(o.bbox) for o in track.observations]
            if areas and min(areas) < 500:
                track_invalid_reason = "bbox_area_too_small"
            else:
                for o in track.observations:
                    w, h = o.bbox[2] - o.bbox[0], o.bbox[3] - o.bbox[1]
                    if h <= 0:
                        continue
                    ar = w / h
                    if ar < 0.2 or ar > 5.0:
                        track_invalid_reason = "aspect_ratio_not_pallet_like"
                        break

        llm_request: Dict[str, Any] = {
            "profile": prompt_profile,
            "num_images": len(roi_paths),
            "image_paths": list(roi_paths),
        }
        llm_response: Dict[str, Any] = {"raw_json_path": None, "parsed_summary": None, "confidence": None}

        if track_invalid_reason:
            logger.info(
                "Track %s: invalid_reason=%s #obs=%d #selected=%d → no request",
                track.track_id, track_invalid_reason, len(track.observations), len(roi_paths),
            )
            track_results.append((track.track_id, None))
            manifest = {
                "track_id": track.track_id,
                "all_observations": all_observations,
                "selected_views": roi_paths,
                "llm_request": llm_request,
                "llm_response": llm_response,
                "track_invalid_reason": track_invalid_reason,
            }
        else:
            tracks_with_min_views += 1
            logger.info(
                "Track %s: #obs=%d #selected=%d roi_paths=%s request_sent=1",
                track.track_id, len(track.observations), len(roi_paths), roi_paths,
            )
            tracks_requests_sent += 1
            obs = client.analyze_track(track.track_id, roi_paths, prompt_profile=prompt_profile)
            if obs is not None:
                tracks_llm_ok += 1
                products_summary = [{"product": p.product, "estimated_boxes": p.estimated_boxes} for p in obs.products]
                confs = [p.confidence for p in obs.products]
                llm_response["parsed_summary"] = products_summary
                llm_response["confidence"] = sum(confs) / len(confs) if confs else None
            else:
                tracks_llm_failed += 1
            track_results.append((track.track_id, obs))
            manifest = {
                "track_id": track.track_id,
                "all_observations": all_observations,
                "selected_views": roi_paths,
                "llm_request": llm_request,
                "llm_response": llm_response,
            }

        manifest_path = manifests_dir / f"track_{track.track_id}.json"
        try:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.debug("No se pudo escribir manifiesto %s: %s", manifest_path, e)

    pipeline_debug["tracks_with_min_views"] = tracks_with_min_views
    pipeline_debug["tracks_requests_sent"] = tracks_requests_sent
    pipeline_debug["tracks_llm_ok"] = tracks_llm_ok
    pipeline_debug["tracks_llm_failed"] = tracks_llm_failed
    summary_kw: Dict[str, Any] = {
        "pipeline_debug": pipeline_debug,
        "tracks_with_observations": len(tracks),
        "tracks_with_min_views": tracks_with_min_views,
        "tracks_requests_sent": tracks_requests_sent,
        "tracks_llm_ok": tracks_llm_ok,
        "tracks_llm_failed": tracks_llm_failed,
    }
    if reid_metrics is not None:
        summary_kw["tracks_before_reid"] = reid_metrics.get("tracks_before_reid")
        summary_kw["tracks_after_reid"] = reid_metrics.get("tracks_after_reid")
        summary_kw["tracks_merged_count"] = reid_metrics.get("tracks_merged_count")
        summary_kw["reid_candidates_generated"] = reid_metrics.get("reid_candidates_generated")
        summary_kw["reid_pairs_after_phash"] = reid_metrics.get("reid_pairs_after_phash")
        summary_kw["reid_pairs_confirmed"] = reid_metrics.get("reid_pairs_confirmed")
        summary_kw["clip_verifications_run"] = reid_metrics.get("clip_verifications_run")
    summary = _make_summary(
        len(frame_refs),
        tracks_detected,
        len(tracks),
        views_selected_total,
        tracks_llm_ok,
        start_time,
        requests_sent=tracks_requests_sent,
        **summary_kw,
    )
    return track_results, summary


def _make_summary(
    frames_extracted: int,
    tracks_detected: int,
    tracks_analyzed: int,
    views_selected_total: int,
    tracks_ok: int,
    start_time: float,
    *,
    requests_sent: Optional[int] = None,
    **extra: Any,
) -> Dict[str, Any]:
    elapsed = time.time() - start_time
    sent = requests_sent if requests_sent is not None else tracks_analyzed
    # Tiempos de ejecución (para auditoría y métricas)
    start_dt = datetime.fromtimestamp(start_time)
    end_dt = datetime.fromtimestamp(start_time + elapsed)
    return {
        "frames_extracted": frames_extracted,
        "tracks_detected": tracks_detected,
        "tracks_analyzed": tracks_analyzed,
        "views_selected_total": views_selected_total,
        "tracks_ok": tracks_ok,
        "requests_sent": sent,
        "latency_total_seconds": elapsed,
        "start_datetime": start_dt.isoformat(),
        "end_datetime": end_dt.isoformat(),
        **extra,
    }
