"""Celery queue depth helpers."""

import redis

from app.config import settings

METRIC_NAMESPACE_SUFFIX = "/Celery"
METRIC_NAME = "QueueDepth"
DEFAULT_QUEUE_NAME = "celery"


def get_queue_depth(queue_name: str = DEFAULT_QUEUE_NAME) -> int:
    client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=3, socket_timeout=3)
    return int(client.llen(queue_name))


def metric_namespace() -> str:
    project = settings.SERVICE_NAME
    for suffix in ("-api", "-worker"):
        if project.endswith(suffix):
            project = project[: -len(suffix)]
            break
    return f"{project}{METRIC_NAMESPACE_SUFFIX}"
