#!/usr/bin/env sh
set -eu

run_id="${1:?usage: scripts/destroy-run.sh RUN_ID}"
control_plane_url="${CONTROL_PLANE_URL:-http://127.0.0.1:8000}"

curl --fail --silent --show-error \
  -X DELETE \
  "${control_plane_url}/api/v1/runs/${run_id}"
printf '\n'
