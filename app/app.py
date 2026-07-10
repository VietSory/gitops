import os
import random
import logging
from flask import Flask, jsonify
from prometheus_flask_exporter import PrometheusMetrics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
PrometheusMetrics(app)  # auto add /metrics

try:
    ERR = float(os.getenv("ERROR_RATE", "0"))
except ValueError:
    ERR = 0.0
VER = os.getenv("VERSION", "v1")


@app.get("/")
def index():
    logger.info(f"Processing request, ERROR_RATE configured at {ERR}")
    if random.random() < ERR:
        return jsonify(error="injected", version=VER), 500
    return jsonify(ok=True, version=VER)


@app.get("/healthz")
def healthz():
    return jsonify(status="ok"), 200
