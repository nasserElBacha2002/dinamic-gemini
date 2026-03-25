"""Run: ``cd backend && python -m src.database.migrations validate``"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
