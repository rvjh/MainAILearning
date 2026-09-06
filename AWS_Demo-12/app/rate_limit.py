"""In-memory per-IP rate limiter."""

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request

_lock = Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)


def check_rate_limit(request: Request, *, limit: int, window_seconds: int) -> None:
    if limit <= 0:
        return

    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    cutoff = now - window_seconds

    with _lock:
        bucket = _hits[client]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {limit} requests per {window_seconds}s",
            )
        bucket.append(now)
