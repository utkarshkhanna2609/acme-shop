"""payments: a stand-in card processor. Slow sometimes, failing at PAYMENTS_FAIL_RATE."""
import json
import os
import random
import sys
import time
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from opentelemetry import trace

FAIL_RATE = float(os.environ.get("PAYMENTS_FAIL_RATE", "0.03"))
EXTRA_LATENCY_MS = int(os.environ.get("PAYMENTS_EXTRA_LATENCY_MS", "0"))

app = Flask(__name__)


def log(level, message, **fields):
    ctx = trace.get_current_span().get_span_context()
    doc = {
        "@timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "service": "payments",
        "message": message,
        **fields,
    }
    if ctx.is_valid:
        doc["trace_id"] = format(ctx.trace_id, "032x")
        doc["span_id"] = format(ctx.span_id, "016x")
    sys.stdout.write(json.dumps(doc) + "\n")
    sys.stdout.flush()


@app.get("/healthz")
def healthz():
    return "ok"


@app.post("/charge")
def charge():
    body = request.get_json(silent=True) or {}
    time.sleep(random.uniform(0.02, 0.2) + EXTRA_LATENCY_MS / 1000)
    if random.random() < FAIL_RATE:
        log("error", "card processor timeout", order_id=body.get("order_id"), processor="stripe-mock")
        return jsonify(error="card processor timeout"), 502
    log("info", "charge captured", order_id=body.get("order_id"), amount_cents=body.get("amount_cents"))
    return jsonify(status="captured")
