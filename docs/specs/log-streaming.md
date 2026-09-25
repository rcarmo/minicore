# Node log streaming

The log surface reads bounded snapshots in `runtime/node-logs/` and serves them through HTTP pages plus SSE metadata to the browser Logs tab.

This surface serves container stdout and stderr for inventoried node services, including real FRR startup messages. It does not expose arbitrary files, journals, management logs or controller audit. Log transport success does not prove healthy routing.

## Run

```sh
make logs-once
make logs-follow
bun scripts/log-collector.ts --node p1 --duration 60
```

Accepted options are `--once`, `--node <inventory ID>` and `--duration <1..3600>`. The collector is explicit host work. `make watch-logs` starts an opt-in user-systemd watcher that renews bounded collection and updates presence. It is not auto-enabled at boot. `make stop-logs` stops its process group. A lock prevents concurrent collectors.

The topology graph is available without running nodes. Missing nodes report `node_unavailable`. Missing snapshots report `backend_not_configured`. Stopped containers can still have retained historical messages with truthful unavailable status.

## Limits

| Boundary | Bound |
|---|---|
| Collector cadence | 2-second delay between full passes; slow nodes lengthen a pass |
| Concurrent node commands | 2 |
| Each command | 5-second deadline; 256 KiB combined stdout and stderr |
| Docker request | Last 501 lines, last 15 minutes, timestamps, no colour or prefix, fixed service |
| Retained snapshot | Newest 500 entries or 60 KiB, whichever is smaller |
| Each message | 2 KiB, truncation flagged |
| API input snapshot | 64 KiB maximum |
| API page | 100 default, 1..500 allowed, encoded response under 64 KiB |
| Freshness | 15 seconds; stale collector is explicit |
| Browser polling | Every 5 seconds while following |
| SSE | 60-second lifetime, 2-second check, shared 16-stream cap, no replay |
| Browser memory | One bounded page |

The service rechecks redaction on read. Recognised credential assignments, `Authorization`, Bearer or Basic values, URL credentials, configured lab tokens and private-key blocks are removed. Terminal escapes are stripped. This is tested pattern-based redaction, not a guarantee for every secret format. The synthetic lab must not contain real operational secrets. Log text is rendered as text only.

Credential rotation revokes authentication immediately after reload while preserving known token values for redaction during the process lifetime. The redaction set is limited to 128 values and 64 KiB. Exceeding either bound disables log and configuration reads with `redaction_unavailable`; authentication and topology remain available. A rotation during a file read also withholds that response. SSE reports unavailable metadata without log content. Redaction memory does not survive restart; remove retired credentials from source evidence before restarting.

Entry IDs bind node, generation, container incarnation and message occurrence. Docker container IDs are not exposed. Re-reading a snapshot does not duplicate rows. Tail rotation can still produce identical timestamp and message pairs without a global exactly-once guarantee.

## HTTP and interaction contract

- `GET /api/v1/nodes/{id}/logs?limit=100&cursor=...` returns envelope fields, bounded rows, source metadata, timestamps, revision and optional older cursor.
- `GET /api/v1/nodes/{id}/logs/events` sends `logs.snapshot` on connect and `logs.changed` on revision, source-status or generation change. Payloads contain metadata, not log lines.
- Only `limit` and `cursor` are accepted page parameters. Unknown nodes return 404. Invalid query returns 400. Rotated or cross-node or cross-generation cursor returns 409. Unavailable or stale source returns 503 with a truthful envelope. Empty successful collection returns 200 with zero rows.
- Both routes use the same authenticated policy as topology. No extra MCP tools are added.
- Cursor binds revision, node and generation. If retention expires a cursor, the UI must return to the latest page explicitly.
- Follow replaces the current page on invalidation or poll. Pause cancels in-flight page fetches and preserves visible rows and scroll position.
