"""Bounded off-loop filesystem calls. Cancelling an await never frees a live worker."""

import asyncio
import contextvars
from concurrent.futures import ThreadPoolExecutor
from functools import partial


class FileIO:
    def __init__(self, *, workers=4, capacity=32):
        if not 1 <= workers <= capacity <= 64:
            raise ValueError("invalid_file_io_limits")
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="minicore-file")
        self.capacity = capacity
        self.pending = set()
        self.closed = False

    async def run(self, function, *args, **kwargs):
        if self.closed or len(self.pending) >= self.capacity:
            raise OSError("file_io_busy")
        loop = asyncio.get_running_loop()
        context = contextvars.copy_context()
        future = loop.run_in_executor(
            self.executor, context.run, partial(function, *args, **kwargs)
        )
        self.pending.add(future)
        cancelled = False
        try:
            while not future.done():
                try:
                    await asyncio.shield(future)
                except asyncio.CancelledError:
                    cancelled = True
                except Exception:
                    break
            if cancelled:
                # Retrieve any exception; cancellation wins only after the worker stops.
                try:
                    future.result()
                except Exception:
                    pass
                raise asyncio.CancelledError()
            return future.result()
        finally:
            self.pending.discard(future)

    async def close(self):
        self.closed = True
        if self.pending:
            await asyncio.gather(
                *[asyncio.shield(f) for f in list(self.pending)], return_exceptions=True
            )
        self.executor.shutdown(wait=False, cancel_futures=True)
