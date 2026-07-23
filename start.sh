#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd "$(dirname "$0")" && pwd)
cd "$PROJECT_ROOT"

if ! command -v uv >/dev/null 2>&1; then
    echo "uv was not found. Install it from https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi

exec uv run --no-project --python 3.12 python scripts/start.py "$@"
