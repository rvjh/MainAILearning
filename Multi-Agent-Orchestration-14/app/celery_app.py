import os
import threading
from celery import Celery
from celery.signals import worker_ready, worker_shutdown

app = Celery(
    'july_sunday',
    broker=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
    backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1'),
)
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
)

_stop = threading.Event()


@app.task(name='workflow.handle_event', acks_late=True, reject_on_worker_lost=True)
def handle_event(event):
    from . import core
    from .db import DomainError, log
    try:
        result = core.consume(event)
        log('consumed', event_id=event['id'], disposition=result)
        return result
    except (DomainError, ValueError, KeyError) as exc:
        log('dead_letter', reason=str(exc))
        return {'disposition': 'rejected'}


def _tick_loop():
    from . import core
    from .db import log
    while not _stop.wait(0.25):
        try:
            core.recovery_tick()
            core.execute_one()
        except Exception as exc:
            log('runtime_retry', mode='worker', error=type(exc).__name__, detail=str(exc)[:250])


@worker_ready.connect
def _start_ticks(**kwargs):
    _stop.clear()
    threading.Thread(target=_tick_loop, name='refund-tick', daemon=True).start()


@worker_shutdown.connect
def _stop_ticks(**kwargs):
    _stop.set()
