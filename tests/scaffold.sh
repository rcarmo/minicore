#!/bin/sh
set -eu
for path in compose router-image mcp-service inventory configs scenarios tests docs; do
  test -d "$path" || { echo "missing directory: $path" >&2; exit 1; }
done
for node in p1 p2 pe1 pe2 ce1 ce2 host1 host2; do
  test -d "configs/$node" || { echo "missing node config directory: $node" >&2; exit 1; }
done
grep -q 'Scaffold only' README.md
test -s SPEC.md
echo "Scaffold test passed."
