FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml README.md /app/
COPY pakem /app/pakem

RUN pip install --no-cache-dir .

ENTRYPOINT ["pakem"]
CMD ["--help"]
