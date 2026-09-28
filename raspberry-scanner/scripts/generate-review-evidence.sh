#!/usr/bin/env bash
set -euo pipefail

# Generates review artifacts without changing the repository's real Git index.
MODULE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPO_DIR=$(cd "$MODULE_DIR/.." && pwd)
OUT_DIR=${1:-"$MODULE_DIR/.review-evidence"}
EMPTY_DIR=$(mktemp -d)
trap 'rm -rf "$EMPTY_DIR"' EXIT

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"

(cd "$MODULE_DIR" && python3 -m unittest discover -s tests -v) >"$OUT_DIR/tests.txt" 2>&1
python3 -m py_compile "$MODULE_DIR/app.py" "$MODULE_DIR/scanner_service.py" >"$OUT_DIR/py-compile.txt" 2>&1
bash -n "$MODULE_DIR/scripts/configure-hotspot-networkmanager.sh" >"$OUT_DIR/bash-n.txt" 2>&1

# A recursive diff against an empty directory is the portable equivalent of a
# Git diff for a fully untracked module. It does not write Git objects/indexes.
set +e
diff -ruN -x .review-evidence -x __pycache__ -x .DS_Store "$EMPTY_DIR" "$MODULE_DIR" >"$OUT_DIR/effective-diff.patch"
DIFF_STATUS=$?
set -e
if [[ $DIFF_STATUS -ne 0 && $DIFF_STATUS -ne 1 ]]; then
  exit "$DIFF_STATUS"
fi

find "$MODULE_DIR" -type f \
  -not -path '*/.review-evidence/*' \
  -not -path '*/__pycache__/*' \
  -not -name .DS_Store -print | sort | while read -r file; do
  git diff --no-index --stat /dev/null "$file" || [[ $? -eq 1 ]]
done >"$OUT_DIR/effective-diff-stat.txt"
git diff --check >"$OUT_DIR/diff-check.txt" 2>&1
git -C "$REPO_DIR" status --short >"$OUT_DIR/git-status-short.txt"
