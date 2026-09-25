# God visibility and agent activity

The browser God checkbox and ordinary node-activity halo are separate surfaces.

## God view toggle

The header checkbox labelled *God mode* switches one browser tab between Agent view and God view.

- Agent view is the default.
- God view requires an already God-authorised browser session.
- Toggling view does not change MCP credentials, role mapping, faults or node configuration.
- Operator-only users see the checkbox disabled.

Agent view returns the Operator evidence projection. God view adds bounded controller ground truth where that source is available. Secrets and unrestricted host state remain unavailable in both views.

The server authorises every God-view HTTP and SSE request independently. A forged query flag cannot grant privilege. Switching back to Agent view clears privileged browser state, aborts privileged requests and ignores late God-view responses. View selection is local to one tab and does not affect another tab or MCP session.

## Activity cue

The ordinary node-activity halo is specified in [agent-activity.md](agent-activity.md). It marks authorised node-directed diagnostic requests only. God fault mutations do not produce that cue.

## Evidence projection rules

In both views the browser must continue to distinguish:

- declared baseline from measured runtime state;
- unavailable sources from a healthy empty result;
- controller absence from `no active fault`;
- ordinary diagnostic activity from fault mutation.

The browser can show more bounded context in God view, but it must not invent observations or bypass existing source limits.
