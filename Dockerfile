FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    COORDINATOR_DATA=/data \
    COORDINATOR_REQUIRE_AUTH=1

WORKDIR /app
COPY . /app
RUN mkdir -p /data

EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8765')+'/health',timeout=3)"

CMD ["sh","-c","python -X utf8 app.py --host 0.0.0.0 --port ${PORT:-8765}"]
