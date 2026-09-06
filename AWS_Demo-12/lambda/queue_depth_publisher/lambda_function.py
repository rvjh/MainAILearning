"""Publish Celery QueueDepth to CloudWatch."""

import os

import boto3
import redis

cloudwatch = boto3.client("cloudwatch")


def handler(_event, _context):
    redis_url = os.environ["REDIS_URL"]
    namespace = os.environ["METRIC_NAMESPACE"]
    queue_name = os.environ.get("CELERY_QUEUE_NAME", "celery")

    client = redis.from_url(redis_url, socket_connect_timeout=5, socket_timeout=5)
    depth = int(client.llen(queue_name))

    cloudwatch.put_metric_data(
        Namespace=namespace,
        MetricData=[{"MetricName": "QueueDepth", "Value": depth, "Unit": "Count"}],
    )
    return {"queue_depth": depth, "namespace": namespace}
