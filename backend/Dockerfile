FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt
COPY backend /app/backend
COPY knowledge /app/knowledge
ENV PYTHONPATH=/app
ENV KNOWLEDGE_DIR=/app/knowledge
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
