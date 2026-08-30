FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN addgroup --system agentapp && adduser --system --ingroup agentapp agentapp
COPY --chown=agentapp:agentapp app ./app
COPY --chown=agentapp:agentapp scripts ./scripts
COPY --chown=agentapp:agentapp sql ./sql
ENV PYTHONPATH=/app
USER agentapp
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
