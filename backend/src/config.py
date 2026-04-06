"""
Módulo de configuración del sistema.

Carga y valida la configuración desde variables de entorno,
con valores por defecto sensatos.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

# backend/src/config.py -> parents[1] == backend/, parents[2] == repo root
_CONFIG_FILE = Path(__file__).resolve()
_BACKEND_ROOT = _CONFIG_FILE.parents[1]
_REPO_ROOT = _BACKEND_ROOT.parent


def _load_dotenv_files(*, for_reload: bool = False) -> None:
    """Load `.env` from repo root and `backend/` so vars match `dev.sh` / root `.env` when cwd is `backend/`.

    Initial load: repo root does not override existing OS env (exported vars win). `backend/.env` can
    override keys from repo for local developer overrides. Cwd `.env` fills remaining gaps.

    Reload: file values override OS env so edits to `.env` take effect after `reload_settings()`.
    """
    override_repo = for_reload
    repo_env = _REPO_ROOT / ".env"
    if repo_env.is_file():
        load_dotenv(repo_env, override=override_repo)
    backend_env = _BACKEND_ROOT / ".env"
    if backend_env.is_file():
        load_dotenv(backend_env, override=True)
    load_dotenv(override=for_reload)


# Cargar variables de entorno desde .env (raíz del repo + backend + cwd)
_load_dotenv_files(for_reload=False)


def _parse_max_frames_to_send() -> Optional[int]:
    """None = sin límite (procesar todo el video). Solo límite si se define explícitamente."""
    raw = os.getenv("MAX_FRAMES_TO_SEND", "").strip()
    if raw in ("", "0"):
        return None
    try:
        n = int(raw)
        return n if 1 <= n <= 10000 else None
    except ValueError:
        return None


def _parse_hybrid_max_frames() -> Optional[int]:
    """None o vacío = sin límite en modo hybrid. Valor válido 1..10000."""
    raw = (os.getenv("HYBRID_MAX_FRAMES") or "").strip()
    if raw in ("", "0"):
        return None
    try:
        n = int(raw)
        return n if 1 <= n <= 10000 else None
    except ValueError:
        return None


def _parse_time_limit_sec() -> Optional[float]:
    raw = os.getenv("TIME_LIMIT_SEC", "").strip()
    if not raw:
        return None
    try:
        v = float(raw)
        return v if v > 0 else None
    except ValueError:
        return None


def _parse_heuristic_resize_max_side() -> Optional[int]:
    """0 o vacío → None; valor válido → int. Evita ValueError si env está vacío."""
    raw = os.getenv("HEURISTIC_RESIZE_MAX_SIDE", "0").strip()
    if not raw:
        return None
    try:
        v = int(raw)
        return v if v > 0 else None
    except ValueError:
        return None


def _parse_photos_max_single_bytes() -> Optional[int]:
    """Unset or empty → None; else int (e.g. 10*1024*1024)."""
    raw = (os.getenv("PHOTOS_MAX_SINGLE_BYTES") or "").strip()
    if not raw:
        return None
    try:
        v = int(raw)
        return v if v > 0 else None
    except ValueError:
        return None


_sqlserver_driver_cache: Optional[str] = None

# Prefer exact Microsoft ODBC names when installed (deterministic vs substring scan order).
_KNOWN_SQLSERVER_ODBC_DRIVERS: Tuple[str, ...] = (
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "ODBC Driver 13 for SQL Server",
)


def _get_available_sqlserver_driver() -> str:
    """Return first ODBC driver name that contains 'SQL Server', or '' if none (e.g. not installed on macOS). Cached per process."""
    global _sqlserver_driver_cache
    if _sqlserver_driver_cache is not None:
        return _sqlserver_driver_cache
    try:
        import pyodbc
        for name in pyodbc.drivers():
            if "SQL Server" in name:
                _sqlserver_driver_cache = name.strip()
                return _sqlserver_driver_cache
    except Exception:
        pass
    _sqlserver_driver_cache = ""
    return _sqlserver_driver_cache


def _pick_odbc_driver_for_split_config(env_driver: str) -> Tuple[str, str]:
    """Pick ODBC driver for split-var mode. Returns (driver_name, resolution_source_label)."""
    explicit = env_driver.strip()
    if explicit:
        return explicit, "SQLSERVER_DRIVER"
    try:
        import pyodbc
        installed_set = {x.strip() for x in pyodbc.drivers()}
        for cand in _KNOWN_SQLSERVER_ODBC_DRIVERS:
            if cand in installed_set:
                return cand, "installed_odbc_preference"
        for name in sorted(installed_set):
            if "SQL Server" in name:
                return name, "installed_odbc_substring"
    except Exception:
        pass
    return "", ""


@dataclass(frozen=True)
class SqlServerConnectionResolution:
    """Canonical outcome of resolving SQL Server env (no secrets)."""

    mode: str
    """``connection_string`` | ``split_env`` | ``unset`` | ``incomplete_split``."""

    connection_string: str
    missing_env_vars: Tuple[str, ...] = ()
    driver_resolution: Optional[str] = None
    """How the ODBC driver was chosen for split mode (e.g. ``SQLSERVER_DRIVER``, ``installed_odbc_preference``)."""

    hint: Optional[str] = None
    """Actionable message when ``connection_string`` is empty (safe for logs / JSON)."""


class SqlServerConfigurationError(ValueError):
    """Raised when SQL Server env is incomplete for building a connection string."""

    def __init__(
        self,
        message: str,
        missing_env_vars: Tuple[str, ...] = (),
        *,
        config_mode: str = "",
    ) -> None:
        super().__init__(message)
        self.missing_env_vars = missing_env_vars
        self.config_mode = config_mode


def resolve_sqlserver_connection_config() -> SqlServerConnectionResolution:
    """Single source of truth for SQL Server env → ODBC connection string (canonical resolver)."""
    raw = (os.getenv("SQLSERVER_CONNECTION_STRING") or "").strip()
    if raw:
        return SqlServerConnectionResolution(
            mode="connection_string",
            connection_string=raw,
            missing_env_vars=(),
            driver_resolution="SQLSERVER_CONNECTION_STRING",
            hint=None,
        )

    server = (os.getenv("SQLSERVER_SERVER") or "").strip()
    database = (os.getenv("SQLSERVER_DATABASE") or "").strip()
    uid = (os.getenv("SQLSERVER_UID") or "").strip()
    pwd = (os.getenv("SQLSERVER_PWD") or "").strip()
    env_driver = (os.getenv("SQLSERVER_DRIVER") or "").strip()

    core = {
        "SQLSERVER_SERVER": server,
        "SQLSERVER_DATABASE": database,
        "SQLSERVER_UID": uid,
        "SQLSERVER_PWD": pwd,
    }
    if not any(core.values()):
        return SqlServerConnectionResolution(
            mode="unset",
            connection_string="",
            missing_env_vars=(),
            driver_resolution=None,
            hint=(
                "No SQL Server settings found. Use SQLSERVER_CONNECTION_STRING or set "
                "SQLSERVER_SERVER, SQLSERVER_DATABASE, SQLSERVER_UID, SQLSERVER_PWD (and SQLSERVER_DRIVER "
                "or install Microsoft ODBC Driver for SQL Server). In CI, pass these as job env/secrets."
            ),
        )

    missing = tuple(name for name, val in core.items() if not val)
    if missing:
        return SqlServerConnectionResolution(
            mode="incomplete_split",
            connection_string="",
            missing_env_vars=missing,
            driver_resolution=None,
            hint=(
                "Split SQL Server config is incomplete. Set all of: SQLSERVER_SERVER, "
                "SQLSERVER_DATABASE, SQLSERVER_UID, SQLSERVER_PWD. "
                "Run `dinamic-db-migrate config-check` in CI before apply/validate."
            ),
        )

    driver, dsrc = _pick_odbc_driver_for_split_config(env_driver)
    if not driver:
        return SqlServerConnectionResolution(
            mode="incomplete_split",
            connection_string="",
            missing_env_vars=("SQLSERVER_DRIVER",),
            driver_resolution=None,
            hint=(
                "No ODBC driver could be resolved. Set SQLSERVER_DRIVER (e.g. 'ODBC Driver 18 for SQL Server') "
                "or install Microsoft ODBC Driver for SQL Server on the runner so pyodbc lists it."
            ),
        )

    cs = (
        f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};UID={uid};PWD={pwd};"
        "TrustServerCertificate=yes"
    )
    return SqlServerConnectionResolution(
        mode="split_env",
        connection_string=cs,
        missing_env_vars=(),
        driver_resolution=dsrc,
        hint=None,
    )


def resolve_sqlserver_effective_connection_string() -> Tuple[str, Tuple[str, ...]]:
    """Backward-compatible: ``(connection_string, missing_env_var_names)`` from :func:`resolve_sqlserver_connection_config`."""
    r = resolve_sqlserver_connection_config()
    return r.connection_string, r.missing_env_vars


def sqlserver_configuration_error_message(resolution: SqlServerConnectionResolution) -> str:
    """Human-readable, actionable error (no secrets)."""
    if resolution.connection_string.strip():
        return ""
    if resolution.mode == "unset":
        return (
            "SQL Server connection not configured (config_mode=unset). "
            "Set SQLSERVER_CONNECTION_STRING, or set all split variables: "
            "SQLSERVER_SERVER, SQLSERVER_DATABASE, SQLSERVER_UID, SQLSERVER_PWD "
            "(and SQLSERVER_DRIVER if no supported ODBC driver is installed on this host). "
            "In GitHub Actions, pass secrets into the migrate job environment (see docs). "
            "Preflight: `dinamic-db-migrate config-check`."
        )
    if resolution.mode == "incomplete_split":
        if resolution.missing_env_vars:
            return (
                f"Incomplete split SQL Server config (config_mode=incomplete_split). "
                f"Missing or empty: {', '.join(resolution.missing_env_vars)}. "
                f"Alternatively set SQLSERVER_CONNECTION_STRING. "
                f"{resolution.hint or ''}"
            ).strip()
    return resolution.hint or "SQL Server configuration invalid."


def _default_sqlserver_connection_string() -> str:
    """``Settings.sqlserver_connection_string`` default — effective ODBC string or empty."""
    return resolve_sqlserver_connection_config().connection_string


class Settings(BaseModel):
    """Configuración del sistema de conteo de inventario por video.
    
    Todos los valores pueden ser configurados mediante variables de entorno
    o usando valores por defecto.
    """
    model_config = {"extra": "forbid"}

    # API Configuration
    gemini_api_key: str = Field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", ""),
        description="API key de Gemini. Requerida para usar el servicio.",
    )
    gemini_model_name: str = Field(
        default_factory=lambda: os.getenv(
            "GEMINI_MODEL_NAME", "gemini-2.0-flash-exp"
        ),
        description="Nombre del modelo de Gemini a usar.",
    )
    gemini_max_retries: int = Field(
        default_factory=lambda: int(os.getenv("GEMINI_MAX_RETRIES", "3")),
        ge=1,
        le=10,
        description="Número máximo de reintentos en llamadas a Gemini (1 a 10).",
    )
    gemini_retry_delay: float = Field(
        default_factory=lambda: float(os.getenv("GEMINI_RETRY_DELAY", "1.0")),
        ge=0.1,
        le=60.0,
        description="Espera inicial entre reintentos en segundos (0.1 a 60).",
    )
    # Stage 2.2.D — LLM provider strategy (gemini | openai | fake)
    llm_provider: str = Field(
        default_factory=lambda: (os.getenv("LLM_PROVIDER", "gemini") or "gemini").strip().lower(),
        description="LLM provider: gemini, openai, or fake. Env: LLM_PROVIDER.",
    )
    openai_api_key: str = Field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", ""),
        description="OpenAI API key (used when llm_provider=openai). Env: OPENAI_API_KEY.",
    )
    openai_model: str = Field(
        default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o"),
        description="OpenAI model name (used when llm_provider=openai). Env: OPENAI_MODEL.",
    )
    fake_llm_fixture_path: Optional[str] = Field(
        default_factory=lambda: (os.getenv("FAKE_LLM_FIXTURE_PATH") or "").strip() or None,
        description="Path to JSON fixture for fake provider (optional). Env: FAKE_LLM_FIXTURE_PATH.",
    )
    hybrid_prompt: str = Field(
        default_factory=lambda: (os.getenv("HYBRID_PROMPT", "global_v21") or "global_v21").strip(),
        description="Perfil de prompt para el pipeline híbrido (ej. global_v21). Env: HYBRID_PROMPT.",
    )
    # Comma-separated lists for POST /process model pickers (Phase 5 corrections)
    processing_gemini_models: str = Field(
        default_factory=lambda: (
            os.getenv(
                "PROCESSING_GEMINI_MODELS",
                "gemini-2.0-flash-exp,gemini-1.5-flash,gemini-1.5-pro",
            )
            or "gemini-2.0-flash-exp"
        ),
        description="Comma-separated Gemini model ids offered in processing-provider-options. Env: PROCESSING_GEMINI_MODELS.",
    )
    processing_openai_models: str = Field(
        default_factory=lambda: (
            os.getenv("PROCESSING_OPENAI_MODELS", "gpt-4o,gpt-4o-mini,gpt-4-turbo")
            or "gpt-4o"
        ),
        description="Comma-separated OpenAI model ids for processing UI (runtime still stubbed for openai). Env: PROCESSING_OPENAI_MODELS.",
    )

    # Frame Extraction Settings
    extract_fps: float = Field(
        default_factory=lambda: float(os.getenv("EXTRACT_FPS", "1.0")),
        ge=0.1,
        le=60.0,
        description="Frames por segundo a extraer del video (0.1 a 60).",
    )
    max_frames_to_send: Optional[int] = Field(
        default_factory=_parse_max_frames_to_send,
        description="Máximo de frames a enviar a Gemini (None = sin límite). Env: MAX_FRAMES_TO_SEND ('' o '0' = sin límite).",
    )
    frame_stride: int = Field(
        default_factory=lambda: int(os.getenv("FRAME_STRIDE", "1")),
        ge=1,
        le=1000,
        description="Cada cuántos frames tomar tras la selección (1 = todos). Acelera videos largos sin truncar por error.",
    )
    time_limit_sec: Optional[float] = Field(
        default_factory=_parse_time_limit_sec,
        description="Procesar solo frames con timestamp_seconds <= este valor. Env: TIME_LIMIT_SEC. None = sin límite.",
    )
    hybrid_max_frames: Optional[int] = Field(
        default_factory=_parse_hybrid_max_frames,
        description="Máximo de frames representativos en modo hybrid (None = sin límite). Env: HYBRID_MAX_FRAMES ('' o '0' = sin límite, 1..10000).",
    )

    # Image Preprocessing (Bloque 7)
    resize_max_side: int = Field(
        default_factory=lambda: int(os.getenv("RESIZE_MAX_SIDE", "1280")),
        ge=320,
        le=4096,
        description="Tamaño máximo del lado de la imagen al redimensionar (320 a 4096 píxeles).",
    )
    jpeg_quality: int = Field(
        default_factory=lambda: int(os.getenv("JPEG_QUALITY", "85")),
        ge=1,
        le=100,
        description="Calidad JPEG al guardar frames (1 a 100).",
    )
    similarity_sample_size: int = Field(
        default_factory=lambda: int(os.getenv("SIMILARITY_SAMPLE_SIZE", "100")),
        ge=16,
        le=512,
        description="Tamaño de muestra para comparación en filtro de similitud (16 a 512).",
    )

    # Sprint A: Detection, tracking, ROI, view selection
    detector_mode: str = Field(
        default_factory=lambda: os.getenv("DETECTOR_MODE", "stub").strip().lower(),
        description="Modo del detector: stub, heuristic, synthetic. Env: DETECTOR_MODE.",
    )
    use_synthetic_detection: bool = Field(
        default_factory=lambda: os.getenv("USE_SYNTHETIC_DETECTION", "").strip().lower() in ("1", "true", "yes"),
        description="Si True, el detector devuelve 2 bboxes fijos por frame (para probar pipeline sin modelo). Env: USE_SYNTHETIC_DETECTION.",
    )
    detection_conf_threshold: float = Field(
        default_factory=lambda: float(os.getenv("DETECTION_CONF_THRESHOLD", "0.5")),
        ge=0.0,
        le=1.0,
        description="Umbral de confianza para detección de pallets (0 a 1).",
    )
    # Heuristic detector (detector_mode=heuristic)
    heuristic_resize_max_side: Optional[int] = Field(
        default_factory=lambda: _parse_heuristic_resize_max_side(),
        description="Si > 0, redimensionar frame antes de detección heurística (lado mayor). 0 = no resize. Env: HEURISTIC_RESIZE_MAX_SIDE.",
    )
    heuristic_min_area_ratio: float = Field(
        default_factory=lambda: float(os.getenv("HEURISTIC_MIN_AREA_RATIO", "0.05")),
        ge=0.001,
        le=0.5,
        description="Área mínima del contorno como fracción del área del frame (heurística). Env: HEURISTIC_MIN_AREA_RATIO.",
    )
    heuristic_aspect_ratio_min: float = Field(
        default_factory=lambda: float(os.getenv("HEURISTIC_ASPECT_RATIO_MIN", "0.6")),
        ge=0.2,
        le=5.0,
        description="Aspect ratio mínimo (ancho/alto) para contornos. Env: HEURISTIC_ASPECT_RATIO_MIN.",
    )
    heuristic_aspect_ratio_max: float = Field(
        default_factory=lambda: float(os.getenv("HEURISTIC_ASPECT_RATIO_MAX", "2.5")),
        ge=0.2,
        le=5.0,
        description="Aspect ratio máximo (ancho/alto) para contornos. Env: HEURISTIC_ASPECT_RATIO_MAX.",
    )
    heuristic_max_detections_per_frame: int = Field(
        default_factory=lambda: int(os.getenv("HEURISTIC_MAX_DETECTIONS_PER_FRAME", "3")),
        ge=1,
        le=20,
        description="Máximo de bboxes por frame (heurística). Env: HEURISTIC_MAX_DETECTIONS_PER_FRAME.",
    )
    heuristic_iou_nms_threshold: float = Field(
        default_factory=lambda: float(os.getenv("HEURISTIC_IOU_NMS_THRESHOLD", "0.5")),
        ge=0.0,
        le=1.0,
        description="IoU umbral para NMS: suprimir detecciones con IoU mayor. Env: HEURISTIC_IOU_NMS_THRESHOLD.",
    )
    tracker_type: str = Field(
        default_factory=lambda: os.getenv("TRACKER_TYPE", "bytetrack"),
        description="Tipo de tracker: bytetrack o sort.",
    )
    tracker_min_hits: int = Field(
        default_factory=lambda: int(os.getenv("TRACKER_MIN_HITS", "3")),
        ge=1,
        le=20,
        description="Mínimo de hits para confirmar track.",
    )
    tracker_max_age: int = Field(
        default_factory=lambda: int(os.getenv("TRACKER_MAX_AGE", "30")),
        ge=1,
        le=100,
        description="Máximo de frames sin detección para mantener track.",
    )
    roi_padding_pct: float = Field(
        default_factory=lambda: float(os.getenv("ROI_PADDING_PCT", "0.12")),
        ge=0.0,
        le=0.5,
        description="Padding del ROI como fracción del lado mayor del bbox (0 a 0.5).",
    )
    roi_max_side: int = Field(
        default_factory=lambda: int(os.getenv("ROI_MAX_SIDE", "1280")),
        ge=320,
        le=2048,
        description="Lado máximo del ROI al redimensionar (320 a 2048).",
    )
    roi_jpeg_quality: int = Field(
        default_factory=lambda: int(os.getenv("ROI_JPEG_QUALITY", "85")),
        ge=1,
        le=100,
        description="Calidad JPEG del ROI (1 a 100).",
    )
    min_views: int = Field(
        default_factory=lambda: int(os.getenv("MIN_VIEWS", "3")),
        ge=1,
        le=10,
        description="Mínimo de vistas por track para enviar a Gemini.",
    )
    target_views: int = Field(
        default_factory=lambda: int(os.getenv("TARGET_VIEWS", "4")),
        ge=1,
        le=10,
        description="Vistas objetivo por track.",
    )
    max_views: int = Field(
        default_factory=lambda: int(os.getenv("MAX_VIEWS", "5")),
        ge=1,
        le=10,
        description="Máximo de vistas por track.",
    )
    view_selection_blur_percentile: float = Field(
        default_factory=lambda: float(os.getenv("VIEW_SELECTION_BLUR_PERCENTILE", "0.25")),
        ge=0.0,
        le=1.0,
        description="Percentil de blur por debajo del cual se descartan observaciones (0 a 1).",
    )
    view_selection_min_frame_gap_diversity: int = Field(
        default_factory=lambda: int(os.getenv("VIEW_SELECTION_MIN_FRAME_GAP_DIVERSITY", "3")),
        ge=0,
        le=30,
        description="Mínimo salto en frame_idx para considerar vista distinta (diversidad). Env: VIEW_SELECTION_MIN_FRAME_GAP_DIVERSITY.",
    )
    view_selection_max_iou_suppress: float = Field(
        default_factory=lambda: float(os.getenv("VIEW_SELECTION_MAX_IOU_SUPPRESS", "0.8")),
        ge=0.0,
        le=1.0,
        description="Si dos vistas están muy cerca en tiempo y sus bboxes tienen IoU > este valor, se descarta una. 0 = desactivado. Env: VIEW_SELECTION_MAX_IOU_SUPPRESS.",
    )
    view_selection_enable_diversity: bool = Field(
        default_factory=lambda: os.getenv("VIEW_SELECTION_ENABLE_DIVERSITY", "true").strip().lower() in ("1", "true", "yes"),
        description="Usar selección en 2 fases (anchors + greedy diversidad) con phash/centroid dedup. Env: VIEW_SELECTION_ENABLE_DIVERSITY.",
    )
    view_selection_phash_near_dup_thr: int = Field(
        default_factory=lambda: int(os.getenv("VIEW_SELECTION_PHASH_NEAR_DUP_THR", "4")),
        ge=0,
        le=64,
        description="Distancia Hamming pHash: si min dist a seleccionados <= este valor, se descarta candidato. Env: VIEW_SELECTION_PHASH_NEAR_DUP_THR.",
    )
    view_selection_centroid_near_dup_thr: float = Field(
        default_factory=lambda: float(os.getenv("VIEW_SELECTION_CENTROID_NEAR_DUP_THR", "0.03")),
        ge=0.0,
        le=1.0,
        description="Distancia euclídea entre centroides normalizados: si <= este valor, se descarta candidato. Env: VIEW_SELECTION_CENTROID_NEAR_DUP_THR.",
    )
    view_selection_anchor_window_frames: int = Field(
        default_factory=lambda: int(os.getenv("VIEW_SELECTION_ANCHOR_WINDOW_FRAMES", "15")),
        ge=0,
        le=100,
        description="Ventana en frames (±N) para elegir anchor en cada segmento temporal. Env: VIEW_SELECTION_ANCHOR_WINDOW_FRAMES.",
    )
    view_selection_diversity_weight: float = Field(
        default_factory=lambda: float(os.getenv("VIEW_SELECTION_DIVERSITY_WEIGHT", "0.35")),
        ge=0.0,
        le=1.0,
        description="Peso del bonus de diversidad en fase greedy (0.35 = 35%%). Env: VIEW_SELECTION_DIVERSITY_WEIGHT.",
    )
    debug_view_selection: bool = Field(
        default_factory=lambda: os.getenv("DEBUG_VIEW_SELECTION", "false").strip().lower() in ("1", "true", "yes"),
        description="Incluir view_selection_debug en pipeline_debug y reasons en manifest. Env: DEBUG_VIEW_SELECTION.",
    )

    # Sprint 6B: Re-ID (optional, default off)
    reid_enabled: bool = Field(
        default_factory=lambda: os.getenv("REID_ENABLED", "false").strip().lower() in ("1", "true", "yes"),
        description="Activar Re-ID (pHash/CLIP + DSU merge) después de tracking, antes de view selection. Env: REID_ENABLED.",
    )
    reid_signature_k: int = Field(
        default_factory=lambda: int(os.getenv("REID_SIGNATURE_K", "2")),
        ge=1,
        le=5,
        description="Número de ROIs por track para firma Re-ID (1 a 5). Env: REID_SIGNATURE_K.",
    )
    reid_max_gap_frames: int = Field(
        default_factory=lambda: int(os.getenv("REID_MAX_GAP_FRAMES", "240")),
        ge=0,
        le=10000,
        description="Gap máximo en frames entre tracks para candidatos Re-ID (~8s a 30fps). Env: REID_MAX_GAP_FRAMES.",
    )
    reid_dx_max: float = Field(
        default_factory=lambda: float(os.getenv("REID_DX_MAX", "0.20")),
        ge=0.0,
        le=1.0,
        description="Diferencia máxima en x normalizada (0..1) entre end_centroid de un track y start_centroid del otro. Env: REID_DX_MAX.",
    )
    reid_dy_max: float = Field(
        default_factory=lambda: float(os.getenv("REID_DY_MAX", "0.25")),
        ge=0.0,
        le=1.0,
        description="Diferencia máxima en y normalizada (0..1) para gating espacial Re-ID. Env: REID_DY_MAX.",
    )
    phash_max_dist: int = Field(
        default_factory=lambda: int(os.getenv("PHASH_MAX_DIST", "10")),
        ge=0,
        le=64,
        description="Distancia Hamming máxima entre pHash de ROIs para considerar par como candidato Re-ID. Env: PHASH_MAX_DIST.",
    )
    clip_min_sim: float = Field(
        default_factory=lambda: float(os.getenv("CLIP_MIN_SIM", "0.92")),
        ge=0.0,
        le=1.0,
        description="Similitud coseno mínima CLIP para confirmar merge de tracks (0 a 1). Env: CLIP_MIN_SIM.",
    )

    # Output Configuration
    output_dir: str = Field(
        default_factory=lambda: os.getenv("OUTPUT_DIR", "output"),
        description="Directorio donde se guardarán los resultados.",
    )

    # API Server (Stage 7)
    api_key: str = Field(
        default_factory=lambda: os.getenv("API_KEY", ""),
        description="API key for server auth (header X-API-Key). Empty = no auth (dev only).",
    )
    embedded_worker_enabled: bool = Field(
        default_factory=lambda: os.getenv("EMBEDDED_WORKER_ENABLED", "true").strip().lower()
        in ("1", "true", "yes"),
        description=(
            "Enable the embedded background worker thread inside API process. "
            "Default true for local/dev; disable in production when running dedicated worker service. "
            "Env: EMBEDDED_WORKER_ENABLED."
        ),
    )
    worker_stale_running_timeout_sec: int = Field(
        default_factory=lambda: int(os.getenv("WORKER_STALE_RUNNING_TIMEOUT_SEC", "900")),
        ge=0,
        le=86400,
        description=(
            "When > 0, worker may reclaim stale RUNNING jobs older than this timeout by resetting them to QUEUED "
            "before claim. Set 0 to disable reclaim. Env: WORKER_STALE_RUNNING_TIMEOUT_SEC."
        ),
    )
    cors_allow_origins: str = Field(
        default_factory=lambda: (os.getenv("CORS_ALLOW_ORIGINS", "") or "").strip(),
        description=(
            "Comma-separated list of allowed CORS origins for the FastAPI server. "
            "If empty, the server falls back to localhost origins. Env: CORS_ALLOW_ORIGINS."
        ),
    )
    forwarded_trusted_hosts: str = Field(
        default_factory=lambda: (os.getenv("FORWARDED_TRUSTED_HOSTS", "") or "").strip(),
        description=(
            "If non-empty, enables uvicorn ProxyHeadersMiddleware so X-Forwarded-Proto / -For "
            "from a trusted reverse proxy (e.g. AWS ALB) adjust request scheme and client. "
            "Use * when the app only receives traffic from the load balancer (typical in ECS). "
            "Comma-separated IPs/CIDRs are supported; empty disables. Env: FORWARDED_TRUSTED_HOSTS."
        ),
    )
    artifact_storage_provider: str = Field(
        default_factory=lambda: (os.getenv("ARTIFACT_STORAGE_PROVIDER", "local") or "local").strip().lower(),
        description="Artifact storage provider: local | s3. Env: ARTIFACT_STORAGE_PROVIDER.",
    )
    artifact_s3_bucket: str = Field(
        default_factory=lambda: (os.getenv("ARTIFACT_S3_BUCKET", "") or "").strip(),
        description="S3 bucket name for artifact storage when provider=s3. Env: ARTIFACT_S3_BUCKET.",
    )
    artifact_s3_region: str = Field(
        default_factory=lambda: (os.getenv("ARTIFACT_S3_REGION", "") or "").strip(),
        description="S3 region for artifact storage when provider=s3. Optional when AWS defaults are present.",
    )
    artifact_s3_prefix: str = Field(
        default_factory=lambda: (os.getenv("ARTIFACT_S3_PREFIX", "v3") or "v3").strip().strip("/"),
        description="S3 key prefix for artifact storage. Env: ARTIFACT_S3_PREFIX.",
    )
    artifact_s3_signed_url_ttl_sec: int = Field(
        default_factory=lambda: int(os.getenv("ARTIFACT_S3_SIGNED_URL_TTL_SEC", "900")),
        ge=30,
        le=86400,
        description="Signed URL TTL in seconds for S3 artifact URLs. Env: ARTIFACT_S3_SIGNED_URL_TTL_SEC.",
    )
    artifact_storage_legacy_local_read_enabled: bool = Field(
        default_factory=lambda: os.getenv("ARTIFACT_STORAGE_LEGACY_LOCAL_READ_ENABLED", "true").strip().lower()
        in ("1", "true", "yes"),
        description=(
            "During migration, allow legacy local-path reads for records without provider metadata. "
            "Env: ARTIFACT_STORAGE_LEGACY_LOCAL_READ_ENABLED."
        ),
    )
    artifact_store_max_in_memory_get_bytes: int = Field(
        default_factory=lambda: int(os.getenv("ARTIFACT_STORE_MAX_IN_MEMORY_GET_BYTES", str(8 * 1024 * 1024))),
        ge=64 * 1024,
        le=512 * 1024 * 1024,
        description=(
            "When loading artifact bytes in the API layer, objects larger than this use "
            "download-to-disk first instead of get_object buffering. Env: ARTIFACT_STORE_MAX_IN_MEMORY_GET_BYTES."
        ),
    )
    artifact_store_max_json_load_bytes: int = Field(
        default_factory=lambda: int(os.getenv("ARTIFACT_STORE_MAX_JSON_LOAD_BYTES", str(32 * 1024 * 1024))),
        ge=64 * 1024,
        le=512 * 1024 * 1024,
        description=(
            "Max JSON artifact size (e.g. hybrid_report) loaded from object storage into memory. "
            "Env: ARTIFACT_STORE_MAX_JSON_LOAD_BYTES."
        ),
    )
    v3_positions_aisle_raw_cap: int = Field(
        default_factory=lambda: int(os.getenv("V3_POSITIONS_AISLE_RAW_CAP", "2000")),
        ge=50,
        le=100_000,
        description=(
            "v3: max raw position rows loaded per aisle before SKU consolidation for GET .../positions. "
            "Pagination and sort apply after consolidation; totals are incomplete when this cap is hit "
            "(see raw_fetch_truncated on the list response). Env: V3_POSITIONS_AISLE_RAW_CAP."
        ),
    )
    max_upload_size_mb: int = Field(
        default_factory=lambda: int(os.getenv("MAX_UPLOAD_SIZE_MB", "500")),
        ge=1,
        le=2048,
        description="Max upload file size in MB (1 to 2048).",
    )
    db_schema_guard_enabled: bool = Field(
        default_factory=lambda: os.getenv("DB_SCHEMA_GUARD_ENABLED", "true").strip().lower()
        in ("1", "true", "yes"),
        description="Enable schema compatibility checks at startup/readiness. Env: DB_SCHEMA_GUARD_ENABLED.",
    )
    db_schema_guard_block_startup: bool = Field(
        default_factory=lambda: os.getenv("DB_SCHEMA_GUARD_BLOCK_STARTUP", "true").strip().lower()
        in ("1", "true", "yes"),
        description="Fail app startup when schema is incompatible. Env: DB_SCHEMA_GUARD_BLOCK_STARTUP.",
    )
    db_schema_service_name: str = Field(
        default_factory=lambda: (os.getenv("DB_SCHEMA_SERVICE_NAME", "inventory-api") or "inventory-api").strip(),
        description="Logical service key used in schema_migrations. Env: DB_SCHEMA_SERVICE_NAME.",
    )
    db_schema_required_version: Optional[str] = Field(
        default_factory=lambda: (os.getenv("DB_SCHEMA_REQUIRED_VERSION") or "").strip() or None,
        description="Optional required schema version override. If unset, latest local migration version is required.",
    )
    db_schema_migration_lock_timeout_sec: int = Field(
        default_factory=lambda: int(os.getenv("DB_SCHEMA_MIGRATION_LOCK_TIMEOUT_SEC", "60")),
        ge=1,
        le=3600,
        description="Lock timeout for migration execution in seconds. Env: DB_SCHEMA_MIGRATION_LOCK_TIMEOUT_SEC.",
    )
    deployment_id: Optional[str] = Field(
        default_factory=lambda: (os.getenv("DEPLOYMENT_ID") or "").strip() or None,
        description="Deployment identifier used to annotate migration history. Env: DEPLOYMENT_ID.",
    )
    # Stage 2.2.A — Photos input (create job with N photos instead of video)
    enable_photos_input: bool = Field(
        default_factory=lambda: os.getenv("ENABLE_PHOTOS_INPUT", "true").strip().lower() in ("1", "true", "yes"),
        description="If False, POST with input_type=photos returns 422. Env: ENABLE_PHOTOS_INPUT (default true).",
    )
    max_photos_per_job: int = Field(
        default_factory=lambda: int(os.getenv("MAX_PHOTOS_PER_JOB", "12")),
        ge=1,
        le=100,
        description="Max number of photos per create-job when input_type=photos. Env: MAX_PHOTOS_PER_JOB.",
    )
    photos_max_total_bytes: int = Field(
        default_factory=lambda: int(os.getenv("PHOTOS_MAX_TOTAL_BYTES", str(25 * 1024 * 1024))),
        ge=1024,
        le=200 * 1024 * 1024,
        description="Max total decoded bytes for all photos in one job (default 25 MB). Env: PHOTOS_MAX_TOTAL_BYTES.",
    )
    # Stage 2.2.C — Photo normalization (resize + JPEG re-encode before LLM/evidence)
    photo_resize_max_side: int = Field(
        default_factory=lambda: int(os.getenv("PHOTO_RESIZE_MAX_SIDE", "1280")),
        ge=320,
        le=4096,
        description="Max side (px) for photo normalization resize. Env: PHOTO_RESIZE_MAX_SIDE.",
    )
    photo_jpeg_quality: int = Field(
        default_factory=lambda: int(os.getenv("PHOTO_JPEG_QUALITY", "85")),
        ge=1,
        le=100,
        description="JPEG quality (1-100) for normalized photos. Env: PHOTO_JPEG_QUALITY.",
    )
    photos_keep_originals: bool = Field(
        default_factory=lambda: os.getenv("PHOTOS_KEEP_ORIGINALS", "false").strip().lower() in ("1", "true", "yes"),
        description="If true, keep originals in input_photos (normalized still written). Env: PHOTOS_KEEP_ORIGINALS.",
    )
    photos_min_side: int = Field(
        default_factory=lambda: int(os.getenv("PHOTOS_MIN_SIDE", "320")),
        ge=64,
        le=2048,
        description="Min side (px) for photos; smaller images fail. Env: PHOTOS_MIN_SIDE.",
    )
    photos_max_single_bytes: Optional[int] = Field(
        default_factory=lambda: _parse_photos_max_single_bytes(),
        description="Max bytes per single original photo (optional). Env: PHOTOS_MAX_SINGLE_BYTES. Unset = no limit.",
    )
    # Stage 8 — SQL Server persistence (optional). Credentials only from env.
    sqlserver_enabled: bool = Field(
        default_factory=lambda: os.getenv("SQLSERVER_ENABLED", "true").strip().lower() in ("1", "true", "yes"),
        description="Use SQL Server as source of truth for jobs, pallet_results, job_events. Default True; set to false to use only filesystem.",
    )
    sqlserver_connection_string: str = Field(
        default_factory=_default_sqlserver_connection_string,
        description=(
            "Effective ODBC connection string: SQLSERVER_CONNECTION_STRING if set, else built from "
            "SQLSERVER_SERVER, SQLSERVER_DATABASE, SQLSERVER_UID, SQLSERVER_PWD, and SQLSERVER_DRIVER "
            "(or auto-detected ODBC driver)."
        ),
    )
    engine_version: str = Field(
        default_factory=lambda: os.getenv("ENGINE_VERSION", "v2.0"),
        description="Engine version identifier for job records.",
    )
    debug_save_frames: bool = Field(
        default_factory=lambda: os.getenv("DEBUG_SAVE_FRAMES", "false").lower()
        in ("true", "1", "yes"),
        description="Si es True, guarda los frames procesados para debug.",
    )

    # Auth (v3.2.1 — minimal administrative authentication)
    admin_username: str = Field(
        default_factory=lambda: (os.getenv("ADMIN_USERNAME", "") or "").strip(),
        description="Single administrator username for v3.2.1 auth. Env: ADMIN_USERNAME.",
    )
    admin_password_hash: str = Field(
        default_factory=lambda: (os.getenv("ADMIN_PASSWORD_HASH", "") or "").strip(),
        description="Password hash for administrator (no plaintext). Env: ADMIN_PASSWORD_HASH.",
    )
    auth_token_secret: str = Field(
        default_factory=lambda: (os.getenv("AUTH_TOKEN_SECRET", "") or "").strip(),
        description="Secret key used to sign auth tokens. Env: AUTH_TOKEN_SECRET.",
    )
    auth_token_expires_minutes: int = Field(
        default_factory=lambda: int(os.getenv("AUTH_TOKEN_EXPIRES_MINUTES", "15")),
        ge=1,
        le=7 * 24 * 60,
        description="Access token lifetime in minutes for admin access (default 15). Env: AUTH_TOKEN_EXPIRES_MINUTES.",
    )
    auth_refresh_token_expires_minutes: int = Field(
        default_factory=lambda: int(os.getenv("AUTH_REFRESH_TOKEN_EXPIRES_MINUTES", str(30 * 24 * 60))),
        ge=1,
        le=60 * 24 * 365,
        description="Refresh token lifetime in minutes for admin sessions (default 30 days). Env: AUTH_REFRESH_TOKEN_EXPIRES_MINUTES.",
    )

    # Stage 2.1.D — Evidence pack
    evidence_k_overview: int = Field(
        default_factory=lambda: int(os.getenv("EVIDENCE_K_OVERVIEW", "3")),
        ge=1,
        le=20,
        description="Mejores frames de overview por entidad. Env: EVIDENCE_K_OVERVIEW.",
    )
    evidence_k_pos_candidates: int = Field(
        default_factory=lambda: int(os.getenv("EVIDENCE_K_POS_CANDIDATES", "5")),
        ge=1,
        le=20,
        description="Candidatos de crop de etiqueta de posición. Env: EVIDENCE_K_POS_CANDIDATES.",
    )
    evidence_k_prod_candidates: int = Field(
        default_factory=lambda: int(os.getenv("EVIDENCE_K_PROD_CANDIDATES", "5")),
        ge=1,
        le=20,
        description="Candidatos de crop de etiqueta de producto. Env: EVIDENCE_K_PROD_CANDIDATES.",
    )
    evidence_max_images_per_pallet: int = Field(
        default_factory=lambda: int(os.getenv("EVIDENCE_MAX_IMAGES_PER_PALLET", "25")),
        ge=1,
        le=100,
        description="Límite total de imágenes por entidad. Env: EVIDENCE_MAX_IMAGES_PER_PALLET.",
    )
    evidence_jpeg_quality: int = Field(
        default_factory=lambda: int(os.getenv("EVIDENCE_JPEG_QUALITY", "85")),
        ge=1,
        le=100,
        description="Calidad JPEG para evidencia. Env: EVIDENCE_JPEG_QUALITY.",
    )

    # Consolidation (Bloque 3)
    consolidation_mad_threshold: float = Field(
        default_factory=lambda: float(os.getenv("CONSOLIDATION_MAD_THRESHOLD", "3.0")),
        ge=0.5,
        le=10.0,
        description="Factor k para filtrado de outliers por MAD (0.5 a 10.0).",
    )
    consolidation_min_evidence_frames: int = Field(
        default_factory=lambda: int(os.getenv("CONSOLIDATION_MIN_EVIDENCE_FRAMES", "2")),
        ge=1,
        le=20,
        description="Mínimo de observaciones (inliers) para no descartar producto (1 a 20).",
    )
    consolidation_min_confidence: float = Field(
        default_factory=lambda: float(os.getenv("CONSOLIDATION_MIN_CONFIDENCE", "0.45")),
        ge=0.0,
        le=1.0,
        description="Mínima confianza final para no descartar producto fantasma (0 a 1).",
    )

    @property
    def sqlserver_effective_connection_string(self) -> str:
        """Canonical ODBC connection string (``SQLSERVER_CONNECTION_STRING`` or built from split vars)."""
        return (self.sqlserver_connection_string or "").strip()

    def require_sqlserver_connection_string(self) -> str:
        """Return a non-empty ODBC connection string or raise :class:`SqlServerConfigurationError`."""
        r = resolve_sqlserver_connection_config()
        if r.connection_string.strip():
            return r.connection_string.strip()
        msg = sqlserver_configuration_error_message(r)
        raise SqlServerConfigurationError(
            msg,
            missing_env_vars=r.missing_env_vars,
            config_mode=r.mode,
        )

    @field_validator("max_frames_to_send")
    @classmethod
    def validate_max_frames_to_send(cls, v: Optional[int]) -> Optional[int]:
        """None y 0 = sin límite. Si se define, debe estar en 1..10000."""
        if v is None or v == 0:
            return None
        if v < 1 or v > 10000:
            raise ValueError("max_frames_to_send debe ser None/0 (sin límite) o entre 1 y 10000")
        return v

    @field_validator("gemini_api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Valida que la API key no esté vacía (aunque puede ser configurada después)."""
        if not v:
            # No lanzamos error aquí, solo advertimos
            # El error se lanzará cuando se intente usar el cliente
            pass
        return v

    @field_validator("detector_mode")
    @classmethod
    def validate_detector_mode(cls, v: str) -> str:
        """Acepta solo stub, heuristic, synthetic."""
        v = (v or "stub").strip().lower()
        if v not in ("stub", "heuristic", "synthetic"):
            return "stub"
        return v

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, v: str) -> str:
        """Provider must be gemini, openai, or fake."""
        v = (v or "gemini").strip().lower()
        if v not in ("gemini", "openai", "fake"):
            raise ValueError("llm_provider must be one of: gemini, openai, fake")
        return v

    @field_validator("output_dir")
    @classmethod
    def validate_output_dir(cls, v: str) -> str:
        """Normalize output_dir: strip, remove trailing slashes, expanduser. Relative paths stay relative."""
        if not v or not isinstance(v, str):
            return "output"
        s = v.strip().rstrip("/\\")
        if not s:
            return "output"
        return str(Path(s).expanduser())

    @field_validator("artifact_storage_provider")
    @classmethod
    def validate_artifact_storage_provider(cls, v: str) -> str:
        p = (v or "local").strip().lower()
        if p not in ("local", "s3"):
            raise ValueError("artifact_storage_provider must be one of: local, s3")
        return p

    @field_validator("artifact_s3_bucket")
    @classmethod
    def validate_artifact_s3_bucket(cls, v: str, info):
        provider = (info.data.get("artifact_storage_provider") or "local").strip().lower()
        bucket = (v or "").strip()
        if provider == "s3" and not bucket:
            raise ValueError("artifact_s3_bucket is required when artifact_storage_provider=s3")
        return bucket

    def ensure_output_dir(self) -> Path:
        """Asegura que el directorio de salida existe y lo crea si es necesario.
        
        Returns:
            Path al directorio de salida.
        """
        output_path = Path(self.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        return output_path


# Instancia global de configuración (lazy loading)
_settings: Optional[Settings] = None


def load_settings() -> Settings:
    """Carga la configuración desde variables de entorno.
    
    La configuración se carga una vez y se cachea. Si necesitas
    recargar la configuración (por ejemplo, después de cambiar .env),
    usa reload_settings().
    
    Returns:
        Settings: Instancia de configuración.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Recarga la configuración desde variables de entorno.
    
    Útil cuando se cambia el archivo .env en tiempo de ejecución.
    
    Returns:
        Settings: Nueva instancia de configuración.
    """
    global _settings
    _load_dotenv_files(for_reload=True)
    _settings = Settings()
    return _settings


def get_settings() -> Settings:
    """Obtiene la configuración actual (alias de load_settings para claridad).
    
    Returns:
        Settings: Instancia de configuración.
    """
    return load_settings()
