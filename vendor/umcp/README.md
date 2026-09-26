# Vendored uMCP

Source: [rcarmo/umcp](https://github.com/rcarmo/umcp) at `30cce7dfe08c6ee63de235f7d81754ba286dafbb`, package version 0.2.2. The upstream [MIT licence](LICENSE) is retained. The runtime uses `aioumcp.py` and `umcp_shared.py`; `upstream-sha256.json` records the original file hashes.

## Local changes

- Preserve the raw auxiliary request target, including query parameters. Minicore validates supported queries.
- Add an optional asynchronous byte iterator to `MCPHTTPResponse.stream` for auxiliary routes. Reject combined body/stream responses and route-supplied framing headers.
- Write streamed chunks asynchronously with connection-close framing, bounded chunks and a ten-second drain deadline. Close stream iterators on disconnect, including a failed header write before iteration starts.
- Return an empty result for protocol `ping`.
- Map `MCPAuthenticationBusy` from the Streamable HTTP authentication hook to `503 file_io_busy`, separately from invalid credentials and unexpected hook failures.
- Scope cancellation to authenticated principal and session; stateless calls are scoped to their connection. Reject active duplicate IDs and target request IDs rather than progress tokens.
- Require a session for HTTP cancellation; reject stateless cross-connection cancellation.
- Combine repeated list-valued `Accept` headers. Keep authorisation, protocol/session and message-framing fields as singletons.

Minicore's subclass implements role-filtered discovery, operation allow-lists and native error mapping. Independent wire and SDK suites cover framing, streaming, cancellation, roles and sessions. Run `make acceptance` and `make mcp-client` from the repository root; see the [testing methodology](../../docs/development/methodology.md).
