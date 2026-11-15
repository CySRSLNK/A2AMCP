#!/usr/bin/env sh
set -eu

if command -v docker-compose >/dev/null 2>&1; then
  compose() { docker-compose "$@"; }
else
  compose() { docker compose "$@"; }
fi

control_plane_url="${CONTROL_PLANE_URL:-http://127.0.0.1:8000}"
web_url="${WEB_URL:-http://127.0.0.1:5173}"
python_bin="${PYTHON_BIN:-.venv/bin/python}"
cleanup() { compose down; }
trap cleanup EXIT INT TERM

compose up -d --build
for attempt in $(seq 1 60); do
  if curl --fail --silent "${control_plane_url}/healthz" >/dev/null \
    && curl --fail --silent "${web_url}/healthz" >/dev/null; then
    break
  fi
  [ "$attempt" -eq 60 ] && { echo "services did not become healthy" >&2; exit 1; }
  sleep 2
done

scenario_json=$(
  "$python_bin" - <<'PY'
import json
from pathlib import Path
import yaml
print(json.dumps(yaml.safe_load(Path("scenarios/recursive-a2a-mcp.yaml").read_text())))
PY
)
curl --fail --silent --show-error -X POST \
  -H 'content-type: application/json' \
  -d "$scenario_json" "${control_plane_url}/api/v1/scenarios" >/dev/null

run_json=$(curl --fail --silent --show-error -X POST \
  -H 'content-type: application/json' \
  -d '{"scenario_id":"recursive-a2a-mcp","root_agent_id":"root-agent","prompt":"inspect the fixture"}' \
  "${control_plane_url}/api/v1/runs")
run_id=$(printf '%s' "$run_json" | "$python_bin" -c 'import json,sys; print(json.load(sys.stdin)["id"])')

for attempt in $(seq 1 60); do
  run=$(curl --fail --silent "${control_plane_url}/api/v1/runs/${run_id}")
  status=$(printf '%s' "$run" | "$python_bin" -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  case "$status" in completed|failed|blocked) break;; esac
  sleep 1
done
events=$(curl --fail --silent "${control_plane_url}/api/v1/runs/${run_id}/events")
count=$(printf '%s' "$events" | "$python_bin" -c 'import json,sys; print(len(json.load(sys.stdin)))')
printf 'run_id=%s status=%s events=%s\n' "$run_id" "$status" "$count"
[ "$status" = completed ]
