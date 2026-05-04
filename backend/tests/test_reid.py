"""
Tests para Re-ID (Sprint 6B).

US-6B.1: run_reid_passthrough, stubs.
US-6B.2: build_track_signatures con pHash, selección determinista, tests de phash.
"""

import tempfile
from pathlib import Path

from PIL import Image

from src.config import load_settings
from src.models.schemas import PalletObservation, PalletTrack
from src.reid import run_reid_passthrough, run_reid_pipeline
from src.reid.clip_embedder import cosine_similarity, verify_with_clip
from src.reid.gating import generate_candidates
from src.reid.merge import merge_tracks_dsu
from src.reid.phash import filter_with_phash
from src.reid.signature import (
    TrackSignature,
    build_track_signatures,
    compute_phash,
)


def _make_track(track_id: str, n_obs: int = 3) -> PalletTrack:
    obs = [
        PalletObservation(
            frame_idx=i * 10,
            timestamp_seconds=i * 10 / 30.0,
            bbox=(10 + i * 5, 10, 50 + i * 5, 50),
            det_conf=0.9,
            track_id=track_id,
            blur_score=0.8 - i * 0.1,
            roi_path=f"/fake/{track_id}_frame{i * 10}.jpg",
        )
        for i in range(n_obs)
    ]
    return PalletTrack(
        track_id=track_id, observations=obs, start_frame=0, end_frame=(n_obs - 1) * 10
    )


def _minimal_obs(
    frame_idx: int,
    track_id: str = "x",
    bbox: tuple[int, int, int, int] = (0, 0, 10, 10),
) -> PalletObservation:
    """Observación mínima para tests de merge."""
    return PalletObservation(
        frame_idx=frame_idx,
        timestamp_seconds=frame_idx / 30.0,
        bbox=bbox,
        det_conf=0.9,
        track_id=track_id,
    )


def test_reid_passthrough_returns_same_tracks():
    """Con Re-ID passthrough, se devuelven los mismos tracks y métricas coherentes."""
    settings = load_settings()
    tracks = [_make_track("0"), _make_track("1")]
    out_tracks, metrics = run_reid_passthrough(tracks, settings)

    assert len(out_tracks) == len(tracks)
    assert out_tracks[0].track_id == tracks[0].track_id
    assert out_tracks[1].track_id == tracks[1].track_id
    assert metrics["tracks_before_reid"] == 2
    assert metrics["tracks_after_reid"] == 2
    assert metrics["tracks_merged_count"] == 0
    assert metrics["reid_candidates_generated"] == 0
    assert metrics["clip_verifications_run"] == 0
    assert "reid_signatures" in metrics
    assert len(metrics["reid_signatures"]) == 2
    assert metrics.get("tracks_with_signatures") == 0  # paths fake, no phash computed
    assert "reid_candidates" in metrics
    assert metrics["reid_candidates"] == []  # sin video dimensions, sin centroids => no candidatos


def test_reid_passthrough_empty_tracks():
    """Passthrough con lista vacía de tracks."""
    settings = load_settings()
    out_tracks, metrics = run_reid_passthrough([], settings)
    assert out_tracks == []
    assert metrics["tracks_before_reid"] == 0
    assert metrics["tracks_after_reid"] == 0
    assert metrics.get("reid_signatures") == {}
    assert metrics.get("reid_candidates") == []


def test_build_track_signatures_returns_one_per_track():
    """build_track_signatures devuelve un TrackSignature por track (roi_phashes vacío si no hay archivos)."""
    tracks = [_make_track("0")]  # roi_paths apuntan a /fake/... que no existen
    sigs = build_track_signatures(tracks, signature_k=2)
    assert list(sigs.keys()) == ["0"]
    assert sigs["0"].track_id == "0"
    assert sigs["0"].signature_k == 2
    assert sigs["0"].roi_phashes == []
    assert sigs["0"].roi_paths == []


def test_generate_candidates_empty_signatures_returns_empty():
    """generate_candidates con dict vacío devuelve lista vacía."""
    out = generate_candidates({}, max_gap_frames=240, dx_max=0.2, dy_max=0.25)
    assert out == []


def test_filter_with_phash_stub_returns_empty():
    """filter_with_phash con candidatos vacíos devuelve lista vacía."""
    out = filter_with_phash([], {}, max_dist=10)
    assert out == []


def test_phash_filter_passes_when_distance_small():
    """Distancia Hamming 1 entre hashes → pasa si max_dist >= 1."""
    h1_hex = "ffffffffffffffff"
    h2_hex = "fffffffffffffffe"  # 1 bit de diferencia
    sigs = {
        "a": TrackSignature(
            track_id="a",
            roi_phashes=[h1_hex],
            roi_paths=[],
            signature_k=1,
            start_frame=0,
            end_frame=10,
            start_centroid=None,
            end_centroid=None,
        ),
        "b": TrackSignature(
            track_id="b",
            roi_phashes=[h2_hex],
            roi_paths=[],
            signature_k=1,
            start_frame=20,
            end_frame=30,
            start_centroid=None,
            end_centroid=None,
        ),
    }
    out = filter_with_phash([("a", "b")], sigs, max_dist=1)
    assert out == [("a", "b")]
    out_strict = filter_with_phash([("a", "b")], sigs, max_dist=0)
    assert out_strict == []


def test_phash_filter_blocks_when_distance_large():
    """Hashes muy distintos (distancia alta) → no pasa."""
    h_all_0 = "0" * 16
    h_all_f = "f" * 16
    sigs = {
        "x": TrackSignature(
            track_id="x",
            roi_phashes=[h_all_0],
            roi_paths=[],
            signature_k=1,
            start_frame=0,
            end_frame=10,
            start_centroid=None,
            end_centroid=None,
        ),
        "y": TrackSignature(
            track_id="y",
            roi_phashes=[h_all_f],
            roi_paths=[],
            signature_k=1,
            start_frame=20,
            end_frame=30,
            start_centroid=None,
            end_centroid=None,
        ),
    }
    out = filter_with_phash([("x", "y")], sigs, max_dist=10)
    assert out == []


def test_phash_filter_ignores_tracks_without_hashes():
    """Si algún track tiene roi_phashes vacío → par descartado."""
    sigs = {
        "a": TrackSignature(
            track_id="a",
            roi_phashes=["ffffffffffffffff"],
            roi_paths=[],
            signature_k=1,
            start_frame=0,
            end_frame=10,
            start_centroid=None,
            end_centroid=None,
        ),
        "b": TrackSignature(
            track_id="b",
            roi_phashes=[],
            roi_paths=[],
            signature_k=1,
            start_frame=20,
            end_frame=30,
            start_centroid=None,
            end_centroid=None,
        ),
    }
    out = filter_with_phash([("a", "b")], sigs, max_dist=10)
    assert out == []


def test_phash_filter_multiple_rois_uses_min_distance():
    """A tiene dos hashes; uno muy distinto y uno muy similar a B. Debe pasar (min distancia)."""
    h_similar = "ffffffffffffffff"
    h_diff = "0000000000000000"
    sigs = {
        "a": TrackSignature(
            track_id="a",
            roi_phashes=[h_diff, h_similar],
            roi_paths=[],
            signature_k=2,
            start_frame=0,
            end_frame=10,
            start_centroid=None,
            end_centroid=None,
        ),
        "b": TrackSignature(
            track_id="b",
            roi_phashes=[h_similar],
            roi_paths=[],
            signature_k=1,
            start_frame=20,
            end_frame=30,
            start_centroid=None,
            end_centroid=None,
        ),
    }
    out = filter_with_phash([("a", "b")], sigs, max_dist=0)
    assert out == [("a", "b")]


def test_verify_with_clip_stub_returns_empty():
    """Con embedder None (stub), verify_with_clip devuelve [] aunque haya candidatos."""
    sigs = {
        "a": TrackSignature(
            track_id="a",
            roi_phashes=[],
            roi_paths=["/fake/a.jpg"],
            signature_k=1,
            start_frame=0,
            end_frame=10,
            start_centroid=None,
            end_centroid=None,
        ),
        "b": TrackSignature(
            track_id="b",
            roi_phashes=[],
            roi_paths=["/fake/b.jpg"],
            signature_k=1,
            start_frame=20,
            end_frame=30,
            start_centroid=None,
            end_centroid=None,
        ),
    }
    out = verify_with_clip([("a", "b")], sigs, min_sim=0.92)
    assert out == []


def test_verify_with_clip_confirms_when_similarity_high():
    """Con embedder mock que devuelve el mismo vector, sim=1.0 -> confirma el par."""
    sigs = {
        "a": TrackSignature(
            track_id="a",
            roi_phashes=[],
            roi_paths=["/path/a.jpg"],
            signature_k=1,
            start_frame=0,
            end_frame=10,
            start_centroid=None,
            end_centroid=None,
        ),
        "b": TrackSignature(
            track_id="b",
            roi_phashes=[],
            roi_paths=["/path/b.jpg"],
            signature_k=1,
            start_frame=20,
            end_frame=30,
            start_centroid=None,
            end_centroid=None,
        ),
    }
    def embedder(path):
        return [1.0, 0.0, 0.0]
    out = verify_with_clip([("a", "b")], sigs, min_sim=0.9, embedder=embedder)
    assert out == [("a", "b")]


def test_verify_with_clip_confirms_with_dict_signatures():
    """verify_with_clip acepta firmas como dict con roi_paths."""
    sigs = {
        "x": {"roi_paths": ["/img/x.jpg"], "roi_phashes": []},
        "y": {"roi_paths": ["/img/y.jpg"], "roi_phashes": []},
    }
    def embedder(path):
        return [1.0, 0.0, 0.0]
    out = verify_with_clip([("x", "y")], sigs, min_sim=0.92, embedder=embedder)
    assert out == [("x", "y")]


def test_verify_with_clip_rejects_when_similarity_low():
    """Vectores ortogonales -> sim=0 -> no confirma."""
    sigs = {
        "p": TrackSignature(
            track_id="p",
            roi_phashes=[],
            roi_paths=["/p.jpg"],
            signature_k=1,
            start_frame=0,
            end_frame=10,
            start_centroid=None,
            end_centroid=None,
        ),
        "q": TrackSignature(
            track_id="q",
            roi_phashes=[],
            roi_paths=["/q.jpg"],
            signature_k=1,
            start_frame=20,
            end_frame=30,
            start_centroid=None,
            end_centroid=None,
        ),
    }

    def embedder(path):
        if "p.jpg" in path:
            return [1.0, 0.0, 0.0]
        return [0.0, 1.0, 0.0]

    assert cosine_similarity([1, 0, 0], [0, 1, 0]) == 0.0
    out = verify_with_clip([("p", "q")], sigs, min_sim=0.9, embedder=embedder)
    assert out == []


def test_verify_with_clip_skips_when_missing_roi_paths():
    """Uno de los tracks con roi_paths vacío -> par no confirmado, sin crash."""
    sigs = {
        "a": TrackSignature(
            track_id="a",
            roi_phashes=[],
            roi_paths=["/a.jpg"],
            signature_k=1,
            start_frame=0,
            end_frame=10,
            start_centroid=None,
            end_centroid=None,
        ),
        "b": TrackSignature(
            track_id="b",
            roi_phashes=[],
            roi_paths=[],
            signature_k=1,
            start_frame=20,
            end_frame=30,
            start_centroid=None,
            end_centroid=None,
        ),
    }
    def embedder(path):
        return [1.0, 0.0, 0.0]
    out = verify_with_clip([("a", "b")], sigs, min_sim=0.9, embedder=embedder)
    assert out == []


def test_verify_with_clip_maintains_order():
    """Múltiples pares confirmados se devuelven en el mismo orden que candidates."""
    sigs = {
        "A": TrackSignature(
            track_id="A",
            roi_phashes=[],
            roi_paths=["/A.jpg"],
            signature_k=1,
            start_frame=0,
            end_frame=10,
            start_centroid=None,
            end_centroid=None,
        ),
        "B": TrackSignature(
            track_id="B",
            roi_phashes=[],
            roi_paths=["/B.jpg"],
            signature_k=1,
            start_frame=20,
            end_frame=30,
            start_centroid=None,
            end_centroid=None,
        ),
        "C": TrackSignature(
            track_id="C",
            roi_phashes=[],
            roi_paths=["/C.jpg"],
            signature_k=1,
            start_frame=40,
            end_frame=50,
            start_centroid=None,
            end_centroid=None,
        ),
        "D": TrackSignature(
            track_id="D",
            roi_phashes=[],
            roi_paths=["/D.jpg"],
            signature_k=1,
            start_frame=60,
            end_frame=70,
            start_centroid=None,
            end_centroid=None,
        ),
    }
    def embedder(path):
        return [1.0, 0.0, 0.0]
    candidates = [("A", "B"), ("C", "D")]
    out = verify_with_clip(candidates, sigs, min_sim=0.9, embedder=embedder)
    assert out == [("A", "B"), ("C", "D")]


def test_merge_tracks_dsu_no_pairs_returns_same():
    """Sin pares confirmados se devuelven los mismos tracks (orden determinista)."""
    tracks = [_make_track("A"), _make_track("B"), _make_track("C")]
    out = merge_tracks_dsu(tracks, [])
    assert len(out) == 3
    assert {t.track_id for t in out} == {"A", "B", "C"}


def test_merge_tracks_dsu_merges_two_tracks():
    """Dos tracks con observaciones distintas y par (A,B) -> un solo track con union de obs."""
    obs_a = [_minimal_obs(10, "A"), _minimal_obs(20, "A")]
    obs_b = [_minimal_obs(30, "B"), _minimal_obs(40, "B")]
    track_a = PalletTrack(track_id="A", observations=obs_a, start_frame=10, end_frame=20)
    track_b = PalletTrack(track_id="B", observations=obs_b, start_frame=30, end_frame=40)
    out = merge_tracks_dsu([track_a, track_b], [("A", "B")])
    assert len(out) == 1
    assert out[0].track_id == "A"  # min(A,B)
    assert len(out[0].observations) == 4
    assert out[0].start_frame == 10
    assert out[0].end_frame == 40
    # Orden por frame_idx
    assert [o.frame_idx for o in out[0].observations] == [10, 20, 30, 40]


def test_merge_tracks_dsu_transitive_merge():
    """Pares (A,B) y (B,C) -> un solo componente, track_id = min(A,B,C)."""
    track_a = PalletTrack(
        track_id="A",
        observations=[_minimal_obs(0, "A")],
        start_frame=0,
        end_frame=0,
    )
    track_b = PalletTrack(
        track_id="B",
        observations=[_minimal_obs(10, "B")],
        start_frame=10,
        end_frame=10,
    )
    track_c = PalletTrack(
        track_id="C",
        observations=[_minimal_obs(20, "C")],
        start_frame=20,
        end_frame=20,
    )
    out = merge_tracks_dsu(
        [track_a, track_b, track_c],
        [("A", "B"), ("B", "C")],
    )
    assert len(out) == 1
    assert out[0].track_id == "A"
    assert out[0].start_frame == 0
    assert out[0].end_frame == 20
    assert len(out[0].observations) == 3


def test_merge_tracks_dsu_ignores_unknown_track_ids():
    """Pares que incluyen un track_id inexistente no rompen; solo se aplican merges válidos."""
    track_a = PalletTrack(
        track_id="A",
        observations=[_minimal_obs(0, "A")],
        start_frame=0,
        end_frame=0,
    )
    track_b = PalletTrack(
        track_id="B",
        observations=[_minimal_obs(10, "B")],
        start_frame=10,
        end_frame=10,
    )
    # (A,X) con X inexistente -> se ignora; (A,B) no está, así que no hay merge
    out = merge_tracks_dsu([track_a, track_b], [("A", "X"), ("X", "Y")])
    assert len(out) == 2
    assert {t.track_id for t in out} == {"A", "B"}


def test_merge_tracks_dsu_deduplicates_exact_same_obs():
    """A y B tienen una observación idéntica (frame_idx, bbox) -> en merged aparece una sola."""
    same_bbox = (5, 5, 15, 15)
    obs_a = [_minimal_obs(10, "A", bbox=same_bbox)]
    obs_b = [_minimal_obs(10, "B", bbox=same_bbox)]
    track_a = PalletTrack(track_id="A", observations=obs_a, start_frame=10, end_frame=10)
    track_b = PalletTrack(track_id="B", observations=obs_b, start_frame=10, end_frame=10)
    out = merge_tracks_dsu([track_a, track_b], [("A", "B")])
    assert len(out) == 1
    assert len(out[0].observations) == 1
    assert out[0].observations[0].frame_idx == 10
    assert out[0].observations[0].bbox == same_bbox


def test_merge_tracks_dsu_output_sorted_deterministic():
    """La salida está siempre ordenada por (start_frame, end_frame, track_id)."""
    track_c = PalletTrack(
        track_id="C",
        observations=[_minimal_obs(20, "C")],
        start_frame=20,
        end_frame=20,
    )
    track_a = PalletTrack(
        track_id="A",
        observations=[_minimal_obs(0, "A")],
        start_frame=0,
        end_frame=0,
    )
    track_b = PalletTrack(
        track_id="B",
        observations=[_minimal_obs(10, "B")],
        start_frame=10,
        end_frame=10,
    )
    # Entrada en orden C, A, B; par (A,B) -> merged. Salida: un merged (0,10) y C (20,20)
    out = merge_tracks_dsu([track_c, track_a, track_b], [("A", "B")])
    assert len(out) == 2
    assert out[0].track_id == "A"
    assert out[0].start_frame == 0
    assert out[0].end_frame == 10
    assert out[1].track_id == "C"
    assert out[1].start_frame == 20


def test_run_reid_pipeline_with_merge():
    """run_reid_pipeline con embedder mock que confirma un par -> 1 track fusionado y reid_merge_map."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Dos imágenes iguales para que phash pase (distancia 0)
        img_path = Path(tmpdir) / "roi.jpg"
        Image.new("RGB", (8, 8), color=(100, 100, 100)).save(img_path)
        path_str = str(img_path)
        # Track A: frames 0, 10; centroides ~(0.5, 0.5). Track B: frames 20, 30; centroides ~(0.52, 0.52)
        # bbox (25,25,75,75) -> center (50,50) -> (0.5, 0.5) con 100x100
        obs_a = [
            PalletObservation(
                frame_idx=0,
                timestamp_seconds=0.0,
                bbox=(25, 25, 75, 75),
                det_conf=0.9,
                track_id="A",
                blur_score=0.9,
                roi_path=path_str,
            ),
            PalletObservation(
                frame_idx=10,
                timestamp_seconds=10 / 30.0,
                bbox=(25, 25, 75, 75),
                det_conf=0.9,
                track_id="A",
                blur_score=0.8,
                roi_path=path_str,
            ),
        ]
        obs_b = [
            PalletObservation(
                frame_idx=20,
                timestamp_seconds=20 / 30.0,
                bbox=(26, 26, 76, 76),
                det_conf=0.9,
                track_id="B",
                blur_score=0.9,
                roi_path=path_str,
            ),
            PalletObservation(
                frame_idx=30,
                timestamp_seconds=30 / 30.0,
                bbox=(26, 26, 76, 76),
                det_conf=0.9,
                track_id="B",
                blur_score=0.8,
                roi_path=path_str,
            ),
        ]
        track_a = PalletTrack(track_id="A", observations=obs_a, start_frame=0, end_frame=10)
        track_b = PalletTrack(track_id="B", observations=obs_b, start_frame=20, end_frame=30)
        settings = load_settings()
        def embedder(path):
            return [1.0, 0.0, 0.0]

        merged, metrics = run_reid_pipeline(
            [track_a, track_b],
            settings,
            video_width=100,
            video_height=100,
            embedder=embedder,
        )

        assert len(merged) == 1
        assert merged[0].track_id == "A"
        assert metrics["tracks_before_reid"] == 2
        assert metrics["tracks_after_reid"] == 1
        assert metrics["tracks_merged_count"] == 1
        assert metrics["reid_pairs_confirmed"] == 1
        merge_map = metrics.get("reid_merge_map") or {}
        assert "A" in merge_map
        assert sorted(merge_map["A"]) == ["A", "B"]


def test_signatures_empty_when_no_rois():
    """Track con observaciones sin roi_path -> firma con roi_phashes y roi_paths vacíos."""
    obs = [
        PalletObservation(
            frame_idx=0,
            timestamp_seconds=0.0,
            bbox=(10, 10, 50, 50),
            det_conf=0.9,
            track_id="x",
            blur_score=0.8,
            roi_path=None,
        ),
    ]
    track = PalletTrack(track_id="x", observations=obs, start_frame=0, end_frame=0)
    sigs = build_track_signatures([track], signature_k=2)
    assert sigs["x"].track_id == "x"
    assert sigs["x"].roi_phashes == []
    assert sigs["x"].roi_paths == []


def test_signatures_k_selection_deterministic():
    """Con 3 obs y K=2, siempre se eligen las mismas 2 (blur desc, area desc, frame_idx asc)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        p1 = Path(tmpdir) / "a.jpg"
        p2 = Path(tmpdir) / "b.jpg"
        p3 = Path(tmpdir) / "c.jpg"
        for p in (p1, p2, p3):
            Image.new("RGB", (10, 10), color=(100, 100, 100)).save(p)
        obs = [
            PalletObservation(
                frame_idx=20,
                timestamp_seconds=20 / 30.0,
                bbox=(0, 0, 10, 10),
                det_conf=0.9,
                track_id="t",
                blur_score=0.7,
                roi_path=str(p1),
            ),
            PalletObservation(
                frame_idx=10,
                timestamp_seconds=10 / 30.0,
                bbox=(0, 0, 20, 20),
                det_conf=0.9,
                track_id="t",
                blur_score=0.9,
                roi_path=str(p2),
            ),
            PalletObservation(
                frame_idx=0,
                timestamp_seconds=0.0,
                bbox=(0, 0, 15, 15),
                det_conf=0.9,
                track_id="t",
                blur_score=0.8,
                roi_path=str(p3),
            ),
        ]
        track = PalletTrack(track_id="t", observations=obs, start_frame=0, end_frame=20)
        sigs1 = build_track_signatures([track], signature_k=2)
        sigs2 = build_track_signatures([track], signature_k=2)
        assert len(sigs1["t"].roi_paths) == 2
        assert len(sigs2["t"].roi_paths) == 2
        assert sigs1["t"].roi_paths == sigs2["t"].roi_paths
        assert sigs1["t"].roi_phashes == sigs2["t"].roi_phashes
        assert str(p2) in sigs1["t"].roi_paths
        assert str(p3) in sigs1["t"].roi_paths
        assert str(p1) not in sigs1["t"].roi_paths


def test_phash_stable_for_same_image():
    """Mismo archivo -> mismo phash."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        Image.new("RGB", (8, 8), color=(50, 50, 50)).save(f.name)
        path = f.name
    try:
        h1 = compute_phash(path)
        h2 = compute_phash(path)
        assert h1 is not None
        assert h1 == h2
    finally:
        Path(path).unlink(missing_ok=True)


def test_phash_diff_for_diff_images():
    """Dos imágenes distintas -> phash distinto."""
    with tempfile.TemporaryDirectory() as tmpdir:
        p1 = Path(tmpdir) / "1.png"
        p2 = Path(tmpdir) / "2.png"
        Image.new("RGB", (16, 16), color=(0, 0, 0)).save(p1)
        Image.new("RGB", (16, 16), color=(255, 255, 255)).save(p2)
        h1 = compute_phash(str(p1))
        h2 = compute_phash(str(p2))
        assert h1 is not None
        assert h2 is not None
        assert h1 != h2


def test_signatures_start_end_fallback_when_no_valid_roi():
    """Si ninguna ROI seleccionada existe (phash falla), start/end caen a track.start_frame/track.end_frame."""
    obs = [
        PalletObservation(
            frame_idx=5,
            timestamp_seconds=5 / 30.0,
            bbox=(10, 10, 50, 50),
            det_conf=0.9,
            track_id="t",
            blur_score=0.9,
            roi_path="/nonexistent/frame5.jpg",
        ),
        PalletObservation(
            frame_idx=15,
            timestamp_seconds=15 / 30.0,
            bbox=(12, 12, 52, 52),
            det_conf=0.9,
            track_id="t",
            blur_score=0.8,
            roi_path="/nonexistent/frame15.jpg",
        ),
    ]
    track = PalletTrack(track_id="t", observations=obs, start_frame=5, end_frame=15)
    sigs = build_track_signatures([track], signature_k=2)
    assert sigs["t"].roi_phashes == []
    assert sigs["t"].roi_paths == []
    assert sigs["t"].start_frame == 5
    assert sigs["t"].end_frame == 15


def test_signatures_start_end_only_from_valid_rois():
    """start/end se calculan solo con frames de ROIs que tuvieron phash válido."""
    with tempfile.TemporaryDirectory() as tmpdir:
        existent = Path(tmpdir) / "ok.jpg"
        Image.new("RGB", (8, 8), color=(100, 100, 100)).save(existent)
        obs = [
            PalletObservation(
                frame_idx=10,
                timestamp_seconds=10 / 30.0,
                bbox=(0, 0, 20, 20),
                det_conf=0.9,
                track_id="t",
                blur_score=0.9,
                roi_path=str(existent),
            ),
            PalletObservation(
                frame_idx=20,
                timestamp_seconds=20 / 30.0,
                bbox=(0, 0, 20, 20),
                det_conf=0.9,
                track_id="t",
                blur_score=0.8,
                roi_path="/nonexistent/frame20.jpg",
            ),
        ]
        track = PalletTrack(track_id="t", observations=obs, start_frame=10, end_frame=20)
        sigs = build_track_signatures([track], signature_k=2)
        assert len(sigs["t"].roi_phashes) == 1
        assert sigs["t"].start_frame == 10
        assert sigs["t"].end_frame == 10  # solo el frame con ROI válida


def _sig(
    track_id: str, start_frame: int, end_frame: int, start_centroid, end_centroid
) -> TrackSignature:
    """TrackSignature sintético para tests de gating."""
    return TrackSignature(
        track_id=track_id,
        roi_phashes=[],
        roi_paths=[],
        signature_k=2,
        start_frame=start_frame,
        end_frame=end_frame,
        start_centroid=start_centroid,
        end_centroid=end_centroid,
    )


def test_gating_empty_when_insufficient_meta():
    """Si faltan frames o centroides en firmas => devuelve []."""
    # Sin start_frame/end_frame
    s1 = TrackSignature(
        track_id="a",
        roi_phashes=[],
        roi_paths=[],
        signature_k=2,
        start_frame=None,
        end_frame=None,
        start_centroid=(0.5, 0.5),
        end_centroid=(0.5, 0.5),
    )
    s2 = TrackSignature(
        track_id="b",
        roi_phashes=[],
        roi_paths=[],
        signature_k=2,
        start_frame=100,
        end_frame=200,
        start_centroid=(0.5, 0.5),
        end_centroid=(0.5, 0.5),
    )
    out = generate_candidates(
        {"a": s1, "b": s2},
        max_gap_frames=240,
        dx_max=0.2,
        dy_max=0.25,
    )
    assert out == []

    # Sin centroides
    s3 = _sig("c", 0, 50, None, None)
    s4 = _sig("d", 60, 100, None, None)
    out2 = generate_candidates(
        {"c": s3, "d": s4},
        max_gap_frames=240,
        dx_max=0.2,
        dy_max=0.25,
    )
    assert out2 == []


def test_gating_temporal_within_gap():
    """Tracks con gap pequeño => candidato (y espacial dentro de umbral)."""
    # A termina en 100, B empieza en 110 => gap=10
    s1 = _sig("A", 0, 100, (0.5, 0.5), (0.5, 0.5))
    s2 = _sig("B", 110, 200, (0.52, 0.52), (0.52, 0.52))  # dx=0.02, dy=0.02
    out = generate_candidates(
        {"A": s1, "B": s2},
        max_gap_frames=50,
        dx_max=0.2,
        dy_max=0.25,
    )
    assert len(out) == 1
    assert out[0] == ("A", "B")


def test_gating_temporal_outside_gap():
    """Gap grande => no candidato."""
    s1 = _sig("A", 0, 100, (0.5, 0.5), (0.5, 0.5))
    s2 = _sig("B", 500, 600, (0.5, 0.5), (0.5, 0.5))  # gap=400
    out = generate_candidates(
        {"A": s1, "B": s2},
        max_gap_frames=50,
        dx_max=0.2,
        dy_max=0.25,
    )
    assert out == []


def test_gating_spatial_within_threshold():
    """dx/dy pequeños => candidato (temporal ya dentro)."""
    s1 = _sig("X", 0, 50, (0.5, 0.5), (0.5, 0.5))
    s2 = _sig("Y", 60, 110, (0.51, 0.52), (0.51, 0.52))  # diff 0.01, 0.02
    out = generate_candidates(
        {"X": s1, "Y": s2},
        max_gap_frames=240,
        dx_max=0.2,
        dy_max=0.25,
    )
    assert len(out) == 1
    assert out[0] == ("X", "Y")


def test_gating_spatial_outside_threshold():
    """dx o dy grande => no candidato."""
    s1 = _sig("P", 0, 50, (0.5, 0.5), (0.5, 0.5))
    s2 = _sig("Q", 60, 110, (0.9, 0.9), (0.9, 0.9))  # diff 0.4 > dx_max/dy_max
    out = generate_candidates(
        {"P": s1, "Q": s2},
        max_gap_frames=240,
        dx_max=0.2,
        dy_max=0.25,
    )
    assert out == []


def test_no_duplicate_pairs():
    """No repetir (A,B) y (B,A): orden canónico (min_id, max_id)."""
    s1 = _sig("B", 0, 50, (0.5, 0.5), (0.5, 0.5))
    s2 = _sig("A", 60, 110, (0.51, 0.51), (0.51, 0.51))
    out = generate_candidates(
        {"A": s2, "B": s1},
        max_gap_frames=240,
        dx_max=0.2,
        dy_max=0.25,
    )
    assert len(out) == 1
    assert out[0] == ("A", "B")


def test_gating_gap_zero_requires_both_directions():
    """Con gap=0 (solapamiento) se exige simetría: ambas direcciones espaciales deben pasar."""
    # A y B solapan; endA->startB pasa; endB->startA falla (muy lejos)
    s1 = _sig("A", 0, 100, (0.5, 0.5), (0.5, 0.5))
    s2 = _sig(
        "B", 50, 150, (0.52, 0.52), (0.9, 0.9)
    )  # start_B cerca de end_A; end_B lejos de start_A
    out = generate_candidates(
        {"A": s1, "B": s2},
        max_gap_frames=240,
        dx_max=0.2,
        dy_max=0.25,
    )
    assert out == []


def test_gating_gap_zero_both_directions_ok():
    """Con gap=0, si ambas direcciones pasan el umbral => candidato."""
    s1 = _sig("A", 0, 100, (0.5, 0.5), (0.52, 0.52))
    s2 = _sig("B", 50, 150, (0.51, 0.51), (0.53, 0.53))
    out = generate_candidates(
        {"A": s1, "B": s2},
        max_gap_frames=240,
        dx_max=0.2,
        dy_max=0.25,
    )
    assert len(out) == 1
    assert out[0] == ("A", "B")
