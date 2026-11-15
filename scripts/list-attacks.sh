#!/usr/bin/env sh
set -eu

control_plane_url="${CONTROL_PLANE_URL:-http://127.0.0.1:8000}"
attack_id="${1:-}"

if [ -n "$attack_id" ]; then
  curl --fail --silent --show-error \
    "${control_plane_url}/api/v1/attacks/${attack_id}"
else
  curl --fail --silent --show-error \
    "${control_plane_url}/api/v1/attacks"
fi
printf '\n'

