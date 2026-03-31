from __future__ import annotations

import logging
import sys
from pathlib import Path

from watchfiles import run_process

logger = logging.getLogger(__name__)


def backend_root() -> Path:
    """Return the backend project root that should be watched in local dev."""
    return Path(__file__).resolve().parents[2]


def run_worker_once() -> None:
    """Execute one worker process using the standard production entrypoint."""
    from src.jobs.run_worker import main as run_worker_main

    run_worker_main()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        stream=sys.stdout,
    )
    watch_path = backend_root()
    logger.info("Worker dev reloader watching %s", watch_path)
    run_process(str(watch_path), target=run_worker_once, debounce=500)


if __name__ == "__main__":
    main()
