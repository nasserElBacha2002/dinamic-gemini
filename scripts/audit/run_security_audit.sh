#!/usr/bin/env sh
# Phase 4 — reproducible secrets scan via pinned gitleaks container image.
# Scans tracked files at the working-tree state (git ls-files), excluding local
# untracked artifacts (output/, node_modules/, .venv/).
set -u

echo "== Quality Gate — Security audit (gitleaks) =="

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
RAW_DIR="$ROOT_DIR/audit/raw"
REPORT="$RAW_DIR/backend-gitleaks.json"
EXIT_SIDE="$REPORT.exitcode"
GITLEAKS_IMAGE="${GITLEAKS_IMAGE:-zricethezav/gitleaks@sha256:0e99e8821643ea5b235718642b93bb32486af9c8162c8b8731f7cbdc951a7f46}"

mkdir -p "$RAW_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "gitleaks no ejecutado: docker no disponible." >"$REPORT"
  echo "2" >"$EXIT_SIDE"
  echo "ERROR: docker required for gitleaks" >&2
  exit 2
fi

if ! command -v git >/dev/null 2>&1; then
  echo "gitleaks no ejecutado: git no disponible." >"$REPORT"
  echo "2" >"$EXIT_SIDE"
  exit 2
fi

SCAN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/gitleaks-wt.XXXXXX")"
cleanup() { rm -rf "$SCAN_DIR"; }
trap cleanup EXIT

# Materialize tracked paths from the working tree (includes unstaged edits to tracked files).
git -C "$ROOT_DIR" ls-files -z | while IFS= read -r -d '' rel; do
  src="$ROOT_DIR/$rel"
  [ -f "$src" ] || continue
  dest="$SCAN_DIR/$rel"
  mkdir -p "$(dirname "$dest")"
  cp "$src" "$dest"
done
cp "$ROOT_DIR/.gitleaks.toml" "$SCAN_DIR/.gitleaks.toml"

rm -f "$REPORT" "$EXIT_SIDE"
set +e
docker run --rm \
  -v "$SCAN_DIR:/repo:ro" \
  -v "$RAW_DIR:/out" \
  "$GITLEAKS_IMAGE" \
  detect \
  --source=/repo \
  --config=/repo/.gitleaks.toml \
  --redact \
  --no-git \
  --report-format=json \
  --report-path=/out/backend-gitleaks.json \
  --exit-code=1
RC=$?
set -e
echo "$RC" >"$EXIT_SIDE"

if [ ! -f "$REPORT" ]; then
  echo '[]' >"$REPORT"
fi

echo "Gitleaks exit=$RC image=$GITLEAKS_IMAGE report=$REPORT mode=git-ls-files-working-tree"
if [ "$RC" -eq 0 ] || [ "$RC" -eq 1 ]; then
  exit 0
fi
exit "$RC"
