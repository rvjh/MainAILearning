"""Outbox-only entrypoint — does not import LangGraph."""

from app.celery_app import outbox_loop

if __name__ == "__main__":
    outbox_loop()
