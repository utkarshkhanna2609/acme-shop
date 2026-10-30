"""Steady traffic against storefront: browse a lot, buy sometimes."""
import json
import os
import random
import time
import urllib.error
import urllib.request

BASE = os.environ.get("STOREFRONT_URL", "http://storefront:8080")
RPS = float(os.environ.get("LOADGEN_RPS", "4"))
SKUS = ["sku-1", "sku-2", "sku-3", "sku-4", "sku-404"]


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


while True:
    if random.random() < 0.35:
        # sku-404 is rare and does not exist: a steady trickle of 404s.
        sku = random.choices(SKUS, weights=[30, 30, 20, 19, 1])[0]
        call("POST", "/api/checkout", {"sku": sku, "qty": random.randint(1, 3)})
    else:
        call("GET", "/api/products")
    time.sleep(random.expovariate(RPS))
