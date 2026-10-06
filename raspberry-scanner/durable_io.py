"""Shared durable write helpers."""

from __future__ import annotations

import errno
import os
from pathlib import Path


def fsync_directory(directory: Path) -> None:
    try:
        directory_fd = os.open(directory, os.O_RDONLY)
    except OSError as exc:
        if exc.errno in {errno.ENOTSUP, errno.EINVAL}:
            return
        raise
    try:
        os.fsync(directory_fd)
    except OSError as exc:
        if exc.errno in {errno.ENOTSUP, errno.EINVAL}:
            return
        raise
    finally:
        os.close(directory_fd)
