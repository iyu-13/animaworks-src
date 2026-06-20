#!/usr/bin/env bash
set -euo pipefail

ANIMA_NAME="${1:?usage: animaworks-repair-rag-runner.sh <anima>}"
ANIMAWORKS_ROOT="${ANIMAWORKS_ROOT:-/home/deploy/animaworks}"
ANIMAWORKS_DATA_DIR="${ANIMAWORKS_DATA_DIR:-/home/deploy/.animaworks}"
ANIMAWORKS_PYTHON="${ANIMAWORKS_PYTHON:-$ANIMAWORKS_ROOT/.venv/bin/python}"

if [[ ! -x "$ANIMAWORKS_PYTHON" ]]; then
  ANIMAWORKS_PYTHON="${PYTHON:-python3}"
fi

STATE_PATH="$ANIMAWORKS_DATA_DIR/animas/$ANIMA_NAME/state/rag_repair.json"
mapfile -t REPAIR_META < <("$ANIMAWORKS_PYTHON" - "$STATE_PATH" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

state_path = Path(sys.argv[1])
reason = "systemd_repair_rag"
include_shared = True
try:
    state = json.loads(state_path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    state = {}
if isinstance(state, dict):
    raw_reason = state.get("reason")
    if isinstance(raw_reason, str) and raw_reason:
        reason = raw_reason
    include_shared = bool(state.get("include_shared", True))
print(reason)
print("1" if include_shared else "0")
PY
)

REASON="${REPAIR_META[0]:-systemd_repair_rag}"
INCLUDE_SHARED="${REPAIR_META[1]:-1}"

cmd=("$ANIMAWORKS_PYTHON" -m cli repair-rag --anima "$ANIMA_NAME" --full --reason "$REASON")
if [[ "$INCLUDE_SHARED" == "1" ]]; then
  cmd+=(--shared)
fi

cd "$ANIMAWORKS_ROOT"
exec env TOKENIZERS_PARALLELISM="${TOKENIZERS_PARALLELISM:-false}" "${cmd[@]}"
