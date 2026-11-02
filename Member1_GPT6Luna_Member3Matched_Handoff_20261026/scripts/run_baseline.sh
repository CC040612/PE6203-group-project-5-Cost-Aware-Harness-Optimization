#!/usr/bin/env bash
set -euo pipefail
MODE="${1:-formal}"
ACTION="${2:-prepare-only}"
if [[ "$MODE" != smoke && "$MODE" != formal ]] || [[ "$ACTION" != run && "$ACTION" != prepare-only ]]; then
  echo 'Usage: bash run_baseline.sh smoke|formal prepare-only|run' >&2
  exit 2
fi
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SHARED="$(dirname -- "$ROOT")/member2"
REPO=/home/member2/TUA-Bench
PY="$REPO/.venv/bin/python"
export PATH="/home/member2/.local/bin:$PATH"
export PYTHONPATH="$ROOT/adapters${PYTHONPATH:+:$PYTHONPATH}"
export LITELLM_LOCAL_MODEL_COST_MAP=True
export UV_CACHE_DIR=/home/member2/.cache/uv
export TMPDIR=/home/member2/.cache/tmp
export PYTHONUNBUFFERED=1
cd "$REPO"
CONFIG="${RUN_CONFIG:-}"
if [[ -z "$CONFIG" ]]; then
  CONFIG="$("$PY" "$ROOT/scripts/prepare_baseline.py" "$MODE")"
fi
echo "Prepared: $CONFIG"
if [[ "$ACTION" == prepare-only ]]; then
  echo 'Prepared only; no model requests or benchmark tasks were started.'
  exit 0
fi
# The existing local credential is read by Harbor; never copied into deliverables.
KEY_FILE="$SHARED/config/cockpit-local.env"
test -s "$KEY_FILE"
docker info --format '{{.ServerVersion}}'
mkdir -p "$TMPDIR" "$ROOT/logs"
LOG_NAME="$(basename -- "$CONFIG" .json)"
# Reuse only Member 2's raw local transport, not its model-specific run/guard scripts.
"$PY" "$SHARED/scripts/cockpit_wsl_bridge.py" --command \
  "$PY" "$ROOT/scripts/guard_run.py" --config "$CONFIG" \
  uv run --frozen harbor run --config "$CONFIG" --env-file "$KEY_FILE" --yes \
  2>&1 | tee -a "$ROOT/logs/${LOG_NAME}_console.log"
