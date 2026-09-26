FROM python:3.11.11-slim-bookworm@sha256:081075da77b2b55c23c088251026fb69a7b2bf92471e491ff5fd75c192fd38e5
WORKDIR /lab
COPY requirements.lock.txt requirements-llm.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt -r requirements-llm.txt
COPY . .
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
