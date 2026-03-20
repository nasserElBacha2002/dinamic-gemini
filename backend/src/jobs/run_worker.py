from pathlib import Path
import logging
from src.config import load_settings
from src.jobs.worker import worker_loop

logger = logging.getLogger(__name__)


def main() -> None:
    base_path = Path(load_settings().output_dir)
    base_path.mkdir(parents=True, exist_ok=True)
    logger.info("Worker process starting (output_dir=%s)", str(base_path))
    worker_loop(base_path)

if __name__ == "__main__":
    main()
