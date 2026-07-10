FROM python:3.12-slim

RUN pip install flask prometheus-flask-exporter

COPY app.py /app/app.py
WORKDIR /app

RUN useradd -m appuser && chown -R appuser /app
USER appuser

ENV FLASK_APP=app.py
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c 'import urllib.request; urllib.request.urlopen("http://localhost:8080/healthz")' || exit 1

CMD ["flask", "run", "--host=0.0.0.0", "--port=8080"]
