#!/bin/sh
set -eu
for path in inventory/topology.json compose/compose.json SPEC.md mcp-service/Dockerfile; do
  test -s "$path" || { echo "missing: $path" >&2; exit 1; }
done
printf '%s\n' 'Initial management artifact check passed.'
