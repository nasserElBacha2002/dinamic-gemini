"""Benchmark repeated ArtifactStore reads for one source asset.

Usage (from repo root):

    python scripts/benchmark_asset_storage.py --asset-id <uuid> --runs 10

Measures wall duration of the existing ``get_object`` path only (no extra HEAD).

Caveats (not pure GCS network latency):
  - May include SDK connection reuse / TLS session reuse after run 1
  - May include OS page cache if bytes land on local disk adapters
  - Does NOT claim to isolate GCS edge latency from worker CPU/network
  - Does NOT use application-level asset caching (none is introduced here)

Only SELECT for asset metadata + storage downloads. No credentials printed.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path
from uuid import UUID

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_ROOT = _REPO_ROOT / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def _validate_uuid(value: str) -> str:
    text = value.strip()
    UUID(text)
    return text


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def _try_host_snapshot() -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        load1, load5, load15 = time.getloadavg()  # type: ignore[attr-defined]
        out["loadavg"] = f"{load1:.2f}/{load5:.2f}/{load15:.2f}"
    except (AttributeError, OSError):
        pass
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        out["ru_maxrss_kb"] = str(getattr(usage, "ru_maxrss", "?"))
    except Exception:
        pass
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark ArtifactStore get_object for one asset")
    parser.add_argument("--asset-id", required=True, type=_validate_uuid)
    parser.add_argument("--runs", type=int, default=10)
    args = parser.parse_args(argv)
    runs = max(1, int(args.runs))

    from src.config import load_settings
    from src.database.sqlserver import SqlServerClient
    from src.runtime.container.storage_builders import build_artifact_storage

    settings = load_settings()
    client = SqlServerClient(settings.require_sqlserver_connection_string())

    with client.cursor() as cur:
        cur.execute(
            """
            SELECT id, aisle_id, storage_key, storage_provider, storage_bucket, file_size_bytes
            FROM source_assets
            WHERE id = ?
            """,
            (args.asset_id,),
        )
        row = cur.fetchone()
        if row is None:
            print(f"Asset not found: {args.asset_id}", file=sys.stderr)
            return 1
        cols = [c[0] for c in cur.description]
        asset = dict(zip(cols, row))

    key = (asset.get("storage_key") or "").strip()
    if not key:
        print(f"Asset {args.asset_id} has empty storage_key", file=sys.stderr)
        return 1

    store = build_artifact_storage(settings)
    backend = getattr(store, "storage_provider", type(store).__name__)
    bucket = getattr(store, "bucket", asset.get("storage_bucket")) or "-"

    print(f"Asset: {args.asset_id}")
    print(f"Backend: {backend}")
    print(f"Bucket: {bucket}")
    print(f"Object key: {key}")
    print(f"DB file_size_bytes: {asset.get('file_size_bytes')}")
    host = _try_host_snapshot()
    if host:
        print(f"Host snapshot: {host}")
    print()
    print(
        "Note: timings include full get_object path (download + any existing "
        "metadata reload). Not guaranteed to isolate pure GCS RTT."
    )
    print()

    durations: list[float] = []
    byte_length: int | None = None
    for i in range(1, runs + 1):
        t0 = time.monotonic()
        downloaded = store.get_object(key)
        elapsed = time.monotonic() - t0
        durations.append(elapsed)
        byte_length = len(downloaded.content or b"")
        print(f"Run {i:>2}: {elapsed:6.3f} s  ({byte_length} bytes)")

    if byte_length is not None:
        print(f"\nBytes: {byte_length / (1024 * 1024):.2f} MB")
    ordered = sorted(durations)
    print(f"min: {min(durations):.3f} s")
    print(f"p50: {_percentile(ordered, 50):.3f} s")
    print(f"p95: {_percentile(ordered, 95):.3f} s")
    print(f"max: {max(durations):.3f} s")
    if len(durations) >= 2:
        print(f"stdev: {statistics.stdev(durations):.3f} s")
    host_after = _try_host_snapshot()
    if host_after:
        print(f"Host after: {host_after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
