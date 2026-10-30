# acme-shop

A small online shop: three services, a database, and the usual telemetry
around them.

| Service | Stack | Does |
|---|---|---|
| `storefront` | Node 20, Express | Public API: `GET /api/products`, `POST /api/checkout` (port 8080) |
| `orders` | Python, FastAPI, Postgres | Catalogue and orders; charges through payments |
| `payments` | Python, Flask | Card processor stand-in: slow sometimes, fails at `PAYMENTS_FAIL_RATE` |
| `loadgen` | Python | Steady traffic against storefront |
| `postgres` | Postgres 16 | `products`, `orders` |

## Telemetry

**Traces and metrics → OpenTelemetry Collector.** Every service is
auto-instrumented (Node `auto-instrumentations-node`, Python
`opentelemetry-instrument`) and exports OTLP/HTTP to `otel-collector:4318`. The
collector also scrapes the host (`hostmetrics`) and Postgres (`postgresql`,
user `otel_monitor`). Its only exporter is `debug`; add your vendor's in
[`observability/otel-collector.yaml`](observability/otel-collector.yaml).

**Logs → ELK.** Services write JSON lines to stdout with `trace_id` and
`span_id`. Filebeat picks up containers labelled `co.elastic.logs/enabled=true`,
ships to Logstash, and Logstash writes `logs-acme-YYYY.MM.DD` in
Elasticsearch. Kibana is on `127.0.0.1:5601`. Outputs live in
[`observability/logstash/logstash.conf`](observability/logstash/logstash.conf).

## Run

```bash
./scripts/bootstrap-ubuntu.sh      # once: Docker, Compose, vm.max_map_count
docker compose up -d --build
docker compose ps
```

Check:

```bash
curl -s localhost:8080/api/products
docker logs otel-collector --tail 5          # "Traces ... spans: N"
curl -s 'localhost:9200/logs-acme-*/_count'  # from inside the host: docker exec elasticsearch curl ...
```

Kibana from your laptop, over SSM:

```bash
aws ssm start-session --target <instance-id> \
  --document-name AWS-StartPortForwardingSession \
  --parameters portNumber=5601,localPortNumber=5601
```

## Making trouble

Copy `.env.example` to `.env`, change a value, `docker compose up -d`:

| Variable | Default | Effect |
|---|---|---|
| `PAYMENTS_FAIL_RATE` | `0.03` | Share of checkouts failing with "card processor timeout" (502) |
| `PAYMENTS_EXTRA_LATENCY_MS` | `0` | Latency added to every charge |
| `ORDERS_SLOW_RATE` | `0.02` | Share of orders stalling 1.5 s in the database |
| `LOADGEN_RPS` | `4` | Traffic |
