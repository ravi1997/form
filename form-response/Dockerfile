FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app.py config.py ./
COPY models ./models
COPY repositories ./repositories
COPY routes ./routes
COPY services ./services
COPY validators ./validators

RUN pip install --no-cache-dir -e .

EXPOSE 5000

CMD ["flask", "--app", "app", "run", "--host", "0.0.0.0", "--port", "5000"]

