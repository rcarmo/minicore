"""Ephemeral bounded request activity, never a diagnostic history or result stream."""

import asyncio
import time
from uuid import uuid4


class Activity:
    def __init__(self):
        self.epoch = str(uuid4())
        self.generation = None
        self.revision = 0
        self.records = {}
        self.changed = asyncio.Event()

    def notify(self):
        self.revision += 1
        self.changed.set()
        self.changed = asyncio.Event()

    def snapshot(self, generation):
        if self.generation is not None and self.generation != generation:
            self.records.clear()
            self.notify()
        self.generation = generation
        now = time.time()
        expired = [key for key, value in self.records.items() if value["expires_at"] < now]
        for key in expired:
            self.records.pop(key, None)
        if expired:
            self.notify()
        records = list(self.records.values())
        return {
            "epoch": self.epoch,
            "generation": generation,
            "revision": self.revision,
            "active": [dict(r) for r in records if r["state"] == "active"],
            "recent": [dict(r) for r in records if r["state"] == "finished"],
        }

    def start(self, node, generation):
        self.snapshot(generation)
        if len(self.records) >= 128:
            # Drop oldest display state only; cannot block node operations.
            self.records.pop(next(iter(self.records)))
        key = str(uuid4())
        now = time.time()
        self.records[key] = {
            "request_id": key,
            "node_id": node,
            "state": "active",
            "started_at": now,
            "expires_at": now + 20,
        }
        self.notify()
        return key

    def finish(self, key):
        r = self.records.get(key)
        if r:
            r.update(state="finished", expires_at=time.time() + 0.9)
            self.notify()
