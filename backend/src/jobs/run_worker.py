from pathlib import Path
from src.config import load_settings
from src.jobs.worker import worker_loop

def main() -> None:
    base_path = Path(load_settings().output_dir)
    base_path.mkdir(parents=True, exist_ok=True)
    worker_loop(base_path)

if __name__ == "__main__":
    main()
