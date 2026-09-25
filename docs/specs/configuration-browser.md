# Node configuration browser

The Configuration tab serves generated declared baseline files for each inventoried node.

```text
configs/
  p1/     frr.conf, daemons
  p2/     frr.conf, daemons
  pe1/    frr.conf, daemons
  pe2/    frr.conf, daemons
  ce1/    frr.conf, daemons
  ce2/    frr.conf, daemons
  host1/  network.json
  host2/  network.json
```

`make generate` builds this tree from `inventory/topology.json`. `make check` rejects drift. The shared `configs/daemons` template remains generation input only; containers mount per-node copies. Endpoint `network.json` mirrors the generated default gateway, interface and address used by the Compose startup command.

Flow: select a node, open *Configuration*, then choose a file. The response is plain text plus a SHA-256 revision of the returned redacted content. The source is always declared baseline configuration. It is not collected running configuration, and it does not prove that a daemon accepted or loaded the file.

Routes:

- `GET /api/v1/nodes/{id}/config` returns the known file list for that node.
- `GET /api/v1/nodes/{id}/config/{filename}` returns one allowed file and its metadata.

The surface uses the same access policy as topology. It does not permit arbitrary paths, queries or edits. Unknown node, file or path returns 404. Unsupported query returns 400. Writes return 405. Missing or symlinked files return 503. Files larger than 32 KiB, or encoded responses larger than 64 KiB, return 413. Sensitive FRR lines and recognised secret formats are redacted. Binary or invalid UTF-8 content is unavailable. The browser cancels superseded requests and renders text only.

This is a bounded declared-configuration reader. It is not a filesystem browser, `show running-config` surface or host file viewer. Credentials, authorised keys, deployment secrets, controller state and arbitrary host or container files are not exposed.
