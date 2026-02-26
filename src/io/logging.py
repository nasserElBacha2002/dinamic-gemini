"""
Módulo de logging estructurado.

Proporciona configuración de logging para el sistema, incluyendo
logging de métricas, tiempos, y errores.
"""

import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logger(
    output_dir: str,
    video_id: str,
    run_id: str,
    log_level: int = logging.INFO,
    console: bool = True,
) -> logging.Logger:
    """Configura un logger estructurado para el sistema.
    
    Crea un logger que escribe tanto a archivo como a consola (opcional).
    Los logs se guardan en `output_dir/<video_id>/<run_id>/processing.log`
    (mismo directorio de run que result.json). Bloque 4 / US-4.1.
    
    Args:
        output_dir: Directorio base donde guardar los logs.
        video_id: ID del video (segmento de path).
        run_id: ID único de la ejecución.
        log_level: Nivel de logging (default: INFO).
        console: Si True, también escribe a consola (default: True).
    
    Returns:
        Logger configurado.
    
    Examples:
        >>> logger = setup_logger("output", "VID_001", "20240225_120000_abc123")
        >>> logger.info("Procesando video...")
    """
    logger = logging.getLogger(f"dinamic_gemini_{run_id}")
    logger.setLevel(log_level)
    
    # Evitar duplicar handlers si el logger ya existe
    if logger.handlers:
        return logger
    
    # Formato de log
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    # Handler para archivo: mismo directorio de run que result.json
    log_dir = Path(output_dir) / video_id / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "processing.log"
    
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Handler para consola (opcional)
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger


def log_metrics(
    logger: logging.Logger,
    stage: str,
    metrics: dict,
) -> None:
    """Registra métricas de una etapa del procesamiento.
    
    Args:
        logger: Logger a usar.
        stage: Nombre de la etapa (ej: "frame_extraction", "gemini_analysis").
        metrics: Diccionario con métricas a registrar.
    
    Examples:
        >>> logger = setup_logger("output", "VID", "run_001")
        >>> log_metrics(logger, "frame_extraction", {
        ...     "frames_extracted": 10,
        ...     "duration_seconds": 2.5
        ... })
    """
    metrics_str = ", ".join([f"{k}={v}" for k, v in metrics.items()])
    logger.info(f"[{stage}] {metrics_str}")
