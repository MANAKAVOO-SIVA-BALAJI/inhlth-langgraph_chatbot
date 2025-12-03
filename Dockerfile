FROM python:3.11-slim

WORKDIR /app


COPY requirements.txt .


RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip check


ENV PYTHONPATH=/usr/local/lib/python3.10/site-packages
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1


COPY . .


RUN find /app -name '__pycache__' -exec rm -rf {} + && \
    find /app -name '*.pyc' -delete && \
    python -c "from pydantic_settings import BaseSettings; print('Import verification successful')"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
