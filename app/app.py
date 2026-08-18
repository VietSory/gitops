import logging
import math
import os
import random

from flask import Flask, jsonify
from prometheus_flask_exporter import PrometheusMetrics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_error_rate(raw_value: str) -> float:
    """Parse ERROR_RATE and reject values that would invalidate canary tests."""
    try:
        error_rate = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("ERROR_RATE must be a number between 0 and 1") from exc

    if not math.isfinite(error_rate) or not 0.0 <= error_rate <= 1.0:
        raise ValueError("ERROR_RATE must be a finite number between 0 and 1")

    return error_rate


ERR = parse_error_rate(os.getenv("ERROR_RATE", "0"))
VER = os.getenv("VERSION", "v1")

app = Flask(__name__)
PrometheusMetrics(app)  # automatically exposes /metrics

logger.info("Starting API with VERSION=%s ERROR_RATE=%s", VER, ERR)


@app.get("/")
def index():
    if random.random() < ERR:
        logger.warning("Injecting configured failure for VERSION=%s", VER)
        return jsonify(error="injected", version=VER), 500
    return jsonify(ok=True, version=VER)


@app.get("/healthz")
def healthz():
    return jsonify(status="ok"), 200
