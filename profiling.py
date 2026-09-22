"""
Opt-in profiling events.

When the CADFIT_PROFILE environment variable names a file, `log_event` appends
one JSON line per event to it (safe across the pipeline's subprocesses and
pool workers, which all inherit the variable). When it is unset this is a no-op.
"""
import json
import os
import time
from contextlib import contextmanager


def log_event(kind: str, **fields):
    path = os.environ.get("CADFIT_PROFILE")
    if not path:
        return
    rec = {"kind": kind, "t": time.time(), "pid": os.getpid()}
    rec.update(fields)
    try:
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass


@contextmanager
def timed(kind: str, **fields):
    start = time.time()
    try:
        yield
    finally:
        log_event(kind, duration=time.time() - start, **fields)
