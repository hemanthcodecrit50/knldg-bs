FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN python -m venv /app/.venv \
	&& /app/.venv/bin/pip install -r /app/requirements.txt
COPY backend /app/backend
COPY knowledge /app/knowledge
ENV VIRTUAL_ENV=/app/.venv
ENV PATH=/app/.venv/bin:$PATH
ENV PYTHONPATH=/app
ENV KNOWLEDGE_DIR=/app/knowledge
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
