"""orders: owns the catalogue and orders tables, charges through payments."""
import json
import logging
import os
import random
import sys
import threading
import time
from datetime import datetime, timezone

import httpx
import psycopg
from fastapi import FastAPI, HTTPException
from opentelemetry import trace
from pydantic import BaseModel

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://acme:acme@postgres:5432/acme")
PAYMENTS_URL = os.environ.get("PAYMENTS_URL", "http://payments:8080")
# Share of orders that hit the slow path (a lock-wait style stall in the DB).
SLOW_RATE = float(os.environ.get("ORDERS_SLOW_RATE", "0.02"))
PAYMENT_TIMEOUT = float(os.environ.get("PAYMENT_TIMEOUT_SECONDS", "1.0"))
PAYMENT_MAX_ATTEMPTS = int(os.environ.get("PAYMENT_MAX_ATTEMPTS", "3"))
PAYMENT_BACKOFF_SECONDS = float(os.environ.get("PAYMENT_BACKOFF_SECONDS", "0.1"))
PAYMENT_FAILURE_THRESHOLD = int(os.environ.get("PAYMENT_FAILURE_THRESHOLD", "5"))
PAYMENT_CIRCUIT_RESET_SECONDS = float(os.environ.get("PAYMENT_CIRCUIT_RESET_SECONDS", "30"))


class JsonFormatter(logging.Formatter):
    def format(self, record):
        ctx = trace.get_current_span().get_span_context()
        doc = {
            "@timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "service": "orders",
            "message": record.getMessage(),
            **getattr(record, "fields", {}),
        }
        if ctx.is_valid:
            doc["trace_id"] = format(ctx.trace_id, "032x")
            doc["span_id"] = format(ctx.span_id, "016x")
        return json.dumps(doc)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
log = logging.getLogger("orders")
log.handlers = [handler]
log.setLevel(logging.INFO)
log.propagate = False

app = FastAPI()
http = httpx.Client(timeout=PAYMENT_TIMEOUT)
payment_circuit_lock = threading.Lock()
payment_failures = 0
payment_circuit_opened_at = None


class PaymentCircuitOpen(Exception):
    """Raised when payment-provider transient failures trip the circuit."""


def _payment_circuit_is_open():
    global payment_circuit_opened_at
    with payment_circuit_lock:
        if payment_circuit_opened_at is None:
            return False
        if time.monotonic() - payment_circuit_opened_at >= PAYMENT_CIRCUIT_RESET_SECONDS:
            payment_circuit_opened_at = None
            return False
        return True


def _record_payment_success():
    global payment_failures, payment_circuit_opened_at
    with payment_circuit_lock:
        payment_failures = 0
        payment_circuit_opened_at = None


def _record_payment_transient_failure():
    global payment_failures, payment_circuit_opened_at
    with payment_circuit_lock:
        payment_failures += 1
        if payment_failures >= PAYMENT_FAILURE_THRESHOLD:
            payment_circuit_opened_at = time.monotonic()


def _charge_payment(order_id, amount):
    """Charge once or retry only failures that are safe to retry."""
    if _payment_circuit_is_open():
        raise PaymentCircuitOpen

    for attempt in range(PAYMENT_MAX_ATTEMPTS):
        try:
            response = http.post(
                f"{PAYMENTS_URL}/charge",
                json={"order_id": order_id, "amount_cents": amount},
                headers={"Idempotency-Key": str(order_id)},
            )
            response.raise_for_status()
            _record_payment_success()
            return
        except httpx.TimeoutException as exc:
            error_kind = "timeout"
        except httpx.NetworkError as exc:
            error_kind = "network"
        except httpx.HTTPError:
            raise

        if attempt + 1 == PAYMENT_MAX_ATTEMPTS:
            _record_payment_transient_failure()
            log.error(
                "payment provider transient failure",
                extra={"fields": {"order_id": order_id, "kind": error_kind, "attempts": PAYMENT_MAX_ATTEMPTS}},
            )
            raise exc
        time.sleep(PAYMENT_BACKOFF_SECONDS * (2**attempt))


class OrderIn(BaseModel):
    sku: str
    qty: int = 1


@app.get("/healthz")
def healthz():
    return "ok"


@app.get("/products")
def products():
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute("select sku, name, price_cents from products order by sku").fetchall()
    return [{"sku": s, "name": n, "price_cents": p} for s, n, p in rows]


@app.post("/orders")
def create_order(order: OrderIn):
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute("select price_cents from products where sku = %s", (order.sku,)).fetchone()
        if not row:
            log.warning("unknown sku", extra={"fields": {"sku": order.sku}})
            raise HTTPException(404, "unknown sku")
        if random.random() < SLOW_RATE:
            conn.execute("select pg_sleep(1.5)")
            log.warning("slow order insert", extra={"fields": {"sku": order.sku, "stall_ms": 1500}})
        amount = row[0] * order.qty
        order_id = conn.execute(
            "insert into orders (sku, qty, amount_cents, status) values (%s, %s, %s, 'pending') returning id",
            (order.sku, order.qty, amount),
        ).fetchone()[0]

        try:
            _charge_payment(order_id, amount)
        except PaymentCircuitOpen:
            conn.execute("update orders set status = 'failed' where id = %s", (order_id,))
            log.error("payment circuit open", extra={"fields": {"order_id": order_id}})
            raise HTTPException(503, "payment provider unavailable")
        except httpx.HTTPError as exc:
            conn.execute("update orders set status = 'failed' where id = %s", (order_id,))
            log.error("payment failed", extra={"fields": {"order_id": order_id, "error": str(exc)}})
            raise HTTPException(502, "payment failed")

        conn.execute("update orders set status = 'paid' where id = %s", (order_id,))
    log.info("order paid", extra={"fields": {"order_id": order_id, "amount_cents": amount}})
    return {"id": order_id, "amount_cents": amount, "status": "paid"}
