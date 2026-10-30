// storefront: the public API. Lists products and runs checkout through orders.
const express = require("express");
const { trace } = require("@opentelemetry/api");

const ORDERS_URL = process.env.ORDERS_URL || "http://orders:8080";
const PORT = Number(process.env.PORT || 8080);

function log(level, msg, fields = {}) {
  const ctx = trace.getActiveSpan()?.spanContext();
  process.stdout.write(
    JSON.stringify({
      "@timestamp": new Date().toISOString(),
      level,
      service: "storefront",
      message: msg,
      trace_id: ctx?.traceId,
      span_id: ctx?.spanId,
      ...fields,
    }) + "\n",
  );
}

const app = express();
app.use(express.json());

app.get("/healthz", (_req, res) => res.send("ok"));

app.get("/api/products", async (_req, res) => {
  try {
    const r = await fetch(`${ORDERS_URL}/products`);
    const products = await r.json();
    log("info", "listed products", { count: products.length });
    res.json(products);
  } catch (err) {
    log("error", "orders unreachable while listing products", { error: String(err) });
    res.status(503).json({ error: "catalog unavailable" });
  }
});

app.post("/api/checkout", async (req, res) => {
  const { sku = "sku-1", qty = 1 } = req.body || {};
  try {
    const r = await fetch(`${ORDERS_URL}/orders`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sku, qty }),
    });
    const body = await r.json();
    if (!r.ok) {
      log("error", "checkout failed", { sku, qty, status: r.status, reason: body.detail });
      return res.status(r.status).json(body);
    }
    log("info", "checkout complete", { sku, qty, order_id: body.id });
    res.json(body);
  } catch (err) {
    log("error", "orders unreachable during checkout", { sku, error: String(err) });
    res.status(503).json({ error: "checkout unavailable" });
  }
});

app.listen(PORT, () => log("info", `listening on ${PORT}`));
