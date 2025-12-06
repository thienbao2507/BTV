# Python 3.12 slim
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl bash \
    && rm -rf /var/lib/apt/lists/*

# Workdir
WORKDIR /app

# Requirements
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

COPY . /app/

RUN python backend/manage.py collectstatic --noinput

# Default: keep container alive until we mount code & run command from compose
# CMD ["bash", "-lc", "sleep infinity"]
CMD ["bash", "-lc", "python backend/manage.py migrate --noinput && python backend/manage.py createsuperuser --noinput --username \"$DJANGO_SUPERUSER_USERNAME\" --email \"$DJANGO_SUPERUSER_EMAIL\" || true && gunicorn --chdir backend examsite.wsgi:application --bind 0.0.0.0:${PORT:-8000}"]