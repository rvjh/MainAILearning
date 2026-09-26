import os
import sys
import time
from . import core
from .db import *
from .celery_app import handle_event

def envelope(row):
    return {k: str(row[k]) if k in ('id', 'tenant_id', 'workflow_id') else row[k]
            for k in ('id', 'tenant_id', 'workflow_id', 'aggregate_version', 'event_type', 'schema_version', 'payload')}

def publish_one():
    # DB commit first, then Celery. Same outbox as the earlier async lab.
    with tx() as c:
        row = one(c, 'SELECT * FROM outbox_events WHERE published_at IS NULL ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1')
        if not row:
            return False
        handle_event.delay(envelope(row))
        c.execute('UPDATE outbox_events SET published_at=clock_timestamp(),attempts=attempts+1 WHERE id=%s', (row['id'],))
        log('published', event_id=row['id'], type=row['event_type'])
    return True

def main(mode):
    if mode == 'worker':
        os.execvp('celery', ['celery', '-A', 'app.celery_app.app', 'worker', '--loglevel=INFO', '--concurrency=1'])
    while True:
        try:
            if mode == 'scheduler':
                core.schedule_tick()
                time.sleep(.5)
                continue
            if not publish_one():
                time.sleep(.25)
        except Exception as exc:
            log('runtime_retry', mode=mode, error=type(exc).__name__, detail=str(exc)[:250])
            time.sleep(1)

if __name__ == '__main__':
    main(sys.argv[1])
