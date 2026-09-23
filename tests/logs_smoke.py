"""Read-only live smoke. Run a collector and generate a real node event separately."""

import http.client
import json
import os
import time
from urllib.parse import urlsplit

url = urlsplit(os.environ.get("MINICORE_URL", "http://127.0.0.1:19000"))
node = "p1"
conn = http.client.HTTPConnection(url.hostname, url.port, timeout=15)
conn.request("GET", f"/api/v1/nodes/{node}/logs/events")
stream = conn.getresponse()
assert stream.status == 200
seen = set()
deadline = time.monotonic() + 25
while time.monotonic() < deadline:
    line = stream.readline()
    if not line:
        break
    if line.startswith(b"event: "):
        seen.add(line.strip().split(b": ", 1)[1])
    if b"logs.changed" in seen:
        break
stream.close()
conn.close()
assert seen >= {b"logs.snapshot", b"logs.changed"}, seen
conn = http.client.HTTPConnection(url.hostname, url.port, timeout=5)
conn.request("GET", f"/api/v1/nodes/{node}/logs?limit=2")
response = conn.getresponse()
assert response.status == 200
page = json.loads(response.read())
conn.close()
assert len(page["data"]["entries"]) == 2
assert page["data"]["next_cursor"]
assert page["collected_at"] and page["error_code"] is None
print("PASS: real node logs.snapshot then logs.changed, bounded fresh HTTP page and older cursor")
