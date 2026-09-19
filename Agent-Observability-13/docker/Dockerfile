FROM python:3.12-slim
WORKDIR /app

# Build context is the july-cohort repo root.
COPY async-execution/requirements.txt /tmp/requirements-async.txt
COPY Session-Observability/requirements.txt /tmp/requirements-obs.txt
RUN pip install --no-cache-dir -r /tmp/requirements-async.txt \
    && pip install --no-cache-dir python-dotenv \
    && pip install --no-cache-dir -r /tmp/requirements-obs.txt

RUN addgroup --system agentapp && adduser --system --ingroup agentapp agentapp

COPY --chown=agentapp:agentapp async-execution/app ./app
COPY --chown=agentapp:agentapp async-execution/scripts ./scripts
COPY --chown=agentapp:agentapp async-execution/sql ./sql
COPY --chown=agentapp:agentapp Session-Observability/src/obs_agent ./obs_agent

ENV PYTHONPATH=/app
USER agentapp
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
