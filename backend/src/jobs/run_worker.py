import logging
import sys
from pathlib import Path

from src.config import load_settings
from src.jobs.worker import worker_loop


logger = logging.getLogger(__name__)


def _configure_worker_logging() -> None:
    """Configure console logging for ECS/CloudWatch collection."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        stream=sys.stdout,
    )


def main() -> None:
    _configure_worker_logging()
    base_path = Path(load_settings().output_dir)
    base_path.mkdir(parents=True, exist_ok=True)
    logger.info("Worker process starting (output_dir=%s)", str(base_path))
    worker_loop(base_path)

if __name__ == "__main__":
    main()
