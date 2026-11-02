#!/usr/bin/env bash
set -euo pipefail
MODE="${1:-smoke}"
ACTION="${2:-prepare-only}"
if [[ "$MODE" != smoke && "$MODE" != formal ]] || [[ "$ACTION" != run && "$ACTION" != prepare-only ]]; then
  echo 'Usage: bash run_cockpit_baseline.sh smoke|formal prepare-only|run' >&2
  exit 2
fi
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SHARED="$(dirname -- "$SCRIPT_DIR")"
REPO=/home/member2/TUA-Bench
export PATH="/home/member2/.local/bin:$PATH"
export PYTHONPATH="$SHARED/adapters${PYTHONPATH:+:$PYTHONPATH}"
export UV_CACHE_DIR=/home/member2/.cache/uv
export TMPDIR=/home/member2/.cache/tmp
export PYTHONUNBUFFERED=1
mkdir -p "$TMPDIR" "$SHARED/logs"
cd "$REPO"
CONFIG="${RUN_CONFIG:-}"
if [[ -z "$CONFIG" ]]; then
  CONFIG="$($REPO/.venv/bin/python "$SCRIPT_DIR/prepare_baseline_run.py" "$MODE" --provider cockpit-local --repeats "${REPEATS:-3}" --concurrency "${CONCURRENCY:-2}")"
fi
echo "Prepared Cockpit configuration: $CONFIG"
if [[ "$ACTION" == prepare-only ]]; then
  echo 'Preparation only: no model calls or task execution.'
  exit 0
fi
KEY_FILE="$SHARED/config/cockpit-local.env"
"$REPO/.venv/bin/python" - "$KEY_FILE" <<'PY'
import sys
from dotenv import dotenv_values
key = dotenv_values(sys.argv[1]).get('OPENAI_API_KEY', '')
if not key.startswith('agt_codex_'):
    raise SystemExit('Local Cockpit key is missing; do not paste credentials into chat.')
print('Local key file validated without displaying it.')
PY
docker info --format '{{.ServerVersion}}'
LOG_NAME="$(basename -- "$CONFIG" .json)"
"$REPO/.venv/bin/python" "$SCRIPT_DIR/cockpit_wsl_bridge.py" --command \
  "$REPO/.venv/bin/python" "$SCRIPT_DIR/guard_formal_run.py" --config "$CONFIG" \
  uv run --frozen harbor run --config "$CONFIG" --env-file "$KEY_FILE" --yes \
  2>&1 | tee -a "$SHARED/logs/${LOG_NAME}_console.log"
