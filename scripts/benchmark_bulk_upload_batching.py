#!/usr/bin/env python3
"""Local non-destructive bulk-upload batching simulator (no network, no secrets).

Usage (from repository root)::

    python scripts/benchmark_bulk_upload_batching.py --files 100 --size-mb 3

Does **not** run in CI by default. Prints planned batch counts and synthetic duration.
"""

from __future__ import annotations

import argparse
import time


def create_batches(
    sizes: list[int],
    *,
    max_files: int,
    max_bytes: int,
) -> list[list[int]]:
    batches: list[list[int]] = []
    current: list[int] = []
    current_bytes = 0
    for size in sizes:
        if current and (len(current) >= max_files or current_bytes + size > max_bytes):
            batches.append(current)
            current = []
            current_bytes = 0
        current.append(size)
        current_bytes += size
        if len(current) >= max_files or current_bytes >= max_bytes:
            batches.append(current)
            current = []
            current_bytes = 0
    if current:
        batches.append(current)
    return batches


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate bulk upload batching locally.")
    parser.add_argument("--files", type=int, default=100)
    parser.add_argument("--size-mb", type=float, default=3.0)
    parser.add_argument("--max-files", type=int, default=10)
    parser.add_argument("--max-request-mb", type=float, default=100.0)
    parser.add_argument("--concurrency", type=int, default=2)
    args = parser.parse_args()

    size = int(args.size_mb * 1024 * 1024)
    sizes = [size] * args.files
    max_bytes = int(args.max_request_mb * 1024 * 1024)
    t0 = time.perf_counter()
    batches = create_batches(sizes, max_files=args.max_files, max_bytes=max_bytes)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    total_bytes = sum(sizes)
    print(f"files={args.files} size_mb={args.size_mb} total_mb={total_bytes / 1e6:.1f}")
    print(f"batches={len(batches)} sizes={[len(b) for b in batches]}")
    print(f"max_files_per_batch={args.max_files} max_request_mb={args.max_request_mb}")
    print(f"concurrency={args.concurrency} plan_ms={elapsed_ms:.3f}")
    waves = (len(batches) + args.concurrency - 1) // args.concurrency
    # Synthetic: assume 200ms per wave network + 50ms/file server
    synthetic_s = waves * 0.2 + args.files * 0.05 / max(1, args.concurrency)
    print(f"synthetic_duration_s≈{synthetic_s:.1f} (not a real upload)")


if __name__ == "__main__":
    main()
