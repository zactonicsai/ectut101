# Elasticsearch Learning Lab

A self-contained teaching environment for Elasticsearch concepts:
**indexing, sharding, replication, field vs keyword search, and failover.**

Everything runs in Docker — no install except Docker Desktop.

---

## What's inside

```
.
├── docker-compose.yml       two ES nodes + Kibana + API + UI + Go watchdog
├── api/                     FastAPI backend (Python)
│   ├── main.py              all endpoints the UI uses
│   ├── requirements.txt
│   └── Dockerfile
├── ui/
│   └── index.html           single-page Tailwind UI
├── go-watchdog/             Go program that logs failover events
│   ├── main.go
│   ├── go.mod
│   └── Dockerfile
├── load_and_search.py       standalone Python script (no API, talks to ES directly)
└── sample-data/
    ├── shards-intro.txt
    └── failover-notes.txt
```

---

## Quick start

```bash
# 1. Linux only — raise mmap limit so ES will start
sudo sysctl -w vm.max_map_count=262144

# 2. Bring the whole stack up
docker compose up -d --build

# 3. Watch nodes come up (wait ~60s for 'green')
docker compose ps

# 4. Open the UI
open http://localhost:8080
```

| Service          | URL                     | Purpose                         |
| ---------------- | ----------------------- | ------------------------------- |
| UI               | http://localhost:8080   | Tailwind teaching console       |
| FastAPI docs     | http://localhost:8000/docs | Swagger for the backend     |
| Kibana           | http://localhost:5601   | Visual cluster inspector        |
| Elasticsearch #1 | http://localhost:9200   | Direct node access              |
| Elasticsearch #2 | http://localhost:9201   | Direct node access (secondary)  |
| Go watchdog      | `docker logs -f watchdog` | Failover event log            |

---

## The 5-step teaching flow

The UI has five tabs — walk through them in order.

### ① Build Index
Choose shard and replica counts. Declare which fields are `text` (full-text
search) and which are `keyword` (exact match / metadata). Click **Preview
mapping JSON** to see the raw mapping that will be sent to ES.

### ② Load Data
Two ways to index:
- **Upload a text file** — contents go into `content`, with author + tags as keyword metadata
- **Index a JSON document** — type in title, content, and a metadata dict

Try uploading the files in `sample-data/`.

### ③ Search
Three modes, combinable:
- **Free text** — `machine learning` → searches everywhere, fuzzy, scored
- **Field-restricted** — query `indexing` in field `title`
- **Keyword filter** — `author:alice` → exact match on the keyword field

Click the "try" chips to see each in action.

### ④ Cluster & Shards
Live view of where each shard lives. Every shard shows:
- PRIMARY or replica
- Which node hosts it
- Number of documents
- State: STARTED / UNASSIGNED / INITIALIZING

The grid auto-refreshes every 3 seconds.

### ⑤ Simulate Failover
Step-by-step drill:
```bash
# in a separate terminal
docker stop es02              # cluster goes yellow
docker logs -f watchdog       # see the transitions logged

docker start es02             # cluster recovers to green
```
The search UI keeps working the whole time — the Python client in the API
container automatically uses the healthy node.

---

## Teaching scripts

### Standalone Python (no API)
Runs on your host, shows low-level ES usage:
```bash
pip install elasticsearch==8.13.2
python load_and_search.py
```
Creates an index, bulk-loads 5 docs, runs three kinds of search, and prints
the shard layout. Good for teaching the client library itself.

### Java equivalent
Use the Elasticsearch Java API client:
```xml
<dependency>
  <groupId>co.elastic.clients</groupId>
  <artifactId>elasticsearch-java</artifactId>
  <version>8.13.4</version>
</dependency>
```
The same Bulk / Search / Indices methods exist with a typed builder API.

---

## The Go watchdog

Why a separate program? It demonstrates that failover detection is a
cross-cutting concern — **not** part of the main application. In real
systems this kind of watchdog would:
- page on-call via PagerDuty
- trigger an auto-recovery script
- update a service registry so clients know which node is live

Read it in `go-watchdog/main.go`. Under 150 lines, uses only the Go stdlib.

Sample output during a failover drill:
```
watchdog starting — polling 2 nodes every 3s
🎯 ACTIVE node is http://es01:9200
🌡  cluster status: unknown -> green   (2 nodes, 10 active / 0 unassigned shards)
❌ FAILED     http://es02:9200  (context deadline exceeded)
🌡  cluster status: green -> yellow   (1 nodes, 5 active / 5 unassigned shards)
✅ RECOVERED  http://es02:9200 (es02)
🌡  cluster status: yellow -> green   (2 nodes, 10 active / 0 unassigned shards)
```

---

## Tearing down

```bash
docker compose down       # keep volumes, data persists on next up
docker compose down -v    # also wipe ES data volumes
```

---

## Gotchas

- **Memory.** Two ES nodes + Kibana + API + UI uses ~3 GB. Bump Docker
  Desktop's memory limit if you see OOM kills.
- **`vm.max_map_count`.** Required on Linux hosts. If `es01` keeps
  restarting, check `docker logs es01` for the bootstrap check failure.
- **Port clashes.** If ports 9200/9201/5601/8000/8080 are taken, change
  the `ports:` mappings in `docker-compose.yml`.
- **Security is disabled.** This is a learning lab. Never expose port
  9200 from a real server without enabling `xpack.security.enabled=true`.
# ectut101

# Elasticsearch Learning Lab

> A hands-on, two-node Elasticsearch cluster with FastAPI, a Tailwind UI, and a Go failover watchdog — all running in Docker Compose. Designed to teach the *shape* of a real search cluster: discovery, shards, replication, client failover, mappings, and monitoring.

---

## Table of contents

- [What this is](#what-this-is)
- [Who it's for](#who-its-for)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [Project layout](#project-layout)
- [Component reference](#component-reference)
  - [Elasticsearch nodes (es01, es02)](#elasticsearch-nodes-es01-es02)
  - [Kibana](#kibana)
  - [FastAPI backend](#fastapi-backend)
  - [Tailwind UI](#tailwind-ui)
  - [Go watchdog](#go-watchdog)
- [Using the UI — five tabs, in order](#using-the-ui--five-tabs-in-order)
- [API reference](#api-reference)
- [The failover drill](#the-failover-drill)
- [Understanding mappings: text vs keyword](#understanding-mappings-text-vs-keyword)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Moving to AWS](#moving-to-aws)
- [Production checklist](#production-checklist)
- [Further reading](#further-reading)

---

## What this is

A complete, self-contained learning environment for Elasticsearch. Spin up the stack with one command and you get:

- **Two-node Elasticsearch cluster** — real cluster formation, real shard allocation, real replication
- **Kibana** — the official visual debugger, wired to both nodes
- **FastAPI** — a Python backend that demonstrates every CRUD + search operation with clear, readable code
- **Tailwind UI** — a five-tab browser interface so you can poke at the cluster without `curl`
- **Go watchdog** — a 60-line program that teaches state-machine-based failure detection

Every piece is small enough to read end-to-end in an afternoon. Every piece mirrors a real production pattern.

## Who it's for

- Engineers who have used Elasticsearch through a hosted service and want to understand what's actually happening underneath
- Developers prepping for an interview or a new role that involves search infrastructure
- Anyone building a search feature who needs to understand shards, replicas, mappings, and failover before committing to a design
- Educators and bootcamps looking for a ready-to-teach ES/OpenSearch lab

**Not for production.** Security is disabled. Replication factor is minimal. Passwords are hardcoded. See the [Production checklist](#production-checklist).

---

## Architecture

```
                    ┌─────────────────────────────────────────────────┐
                    │               Docker network: eslab             │
                    │                                                 │
   Browser ────►    │   ┌──────────┐          ┌────────────────┐      │
   :8080            │   │    UI    │          │     es01       │      │
                    │   │  nginx   │          │  master + data │◄──┐  │
                    │   └──────────┘          │  shards: P0 R1 │   │  │
                    │                         └────────┬───────┘   │  │
   Browser ────►    │   ┌──────────┐                   │           │  │
   :8000/docs       │   │   API    │─────── search ────┤           │  │
                    │   │ FastAPI  │───────────────────┼──┐        │  │
                    │   └──────────┘                   │  │        │  │
                    │                                  ▼  │        │  │
   Browser ────►    │   ┌──────────┐          ┌────────────────┐   │  │
   :5601            │   │  Kibana  │──────────│     es02       │   │  │
                    │   └──────────┘          │  master + data │◄──┤  │
                    │                         │  shards: R0 P1 │   │  │
                    │   ┌──────────┐          └────────────────┘   │  │
                    │   │ watchdog │──────── poll /_cluster/health ─┘  │
                    │   │    Go    │────────────────────────────────── │
                    │   └──────────┘                                   │
                    │                                                  │
                    └──────────────────────────────────────────────────┘
                     volumes:  es01-data      es02-data
```

Two Elasticsearch nodes, both master-eligible and both data. Two primary shards (P0, P1) with one replica each (R0, R1). The replicas live on the *other* node — kill either one, you lose zero data.

---

## Prerequisites

| Tool              | Minimum version | Notes                                            |
| ----------------- | --------------- | ------------------------------------------------ |
| Docker            | 20.10+          | Docker Desktop or Docker Engine                  |
| Docker Compose    | 2.0+            | Ships with Docker Desktop; `docker compose` CLI  |
| RAM               | 4 GB free       | The JVM heaps alone eat 1 GB                     |
| Disk              | 2 GB free       | For images + ES data volumes                     |

**Linux only:** you must raise `vm.max_map_count` before Elasticsearch will start. See [Quick start](#quick-start).

**macOS / Windows:** Docker Desktop handles the kernel setting automatically. Just make sure Docker has at least 4 GB of RAM allocated in Preferences → Resources.

---

## Quick start

```bash
# 1. Unzip and enter the project
unzip es-lab.zip
cd es-lab

# 2. Linux only: raise the virtual-memory map count
#    (macOS/Windows can skip this — Docker Desktop handles it)
sudo sysctl -w vm.max_map_count=262144

# 3. Bring up the stack (first build ~3-5 minutes)
docker compose up -d --build

# 4. Wait for healthy state (about 45-60 seconds on first boot)
docker compose ps
# Every service should show "healthy" or "running"

# 5. Open the UI
open http://localhost:8080        # or just visit in your browser
```

That's it. The UI is at **[http://localhost:8080](http://localhost:8080)**.

| URL                              | What it is                                      |
| -------------------------------- | ----------------------------------------------- |
| http://localhost:8080            | Tailwind teaching UI (five tabs)                |
| http://localhost:8000/docs       | FastAPI auto-generated Swagger                  |
| http://localhost:5601            | Kibana (Dev Tools, Discover, Stack Management)  |
| http://localhost:9200            | Elasticsearch node `es01` — REST endpoint       |
| http://localhost:9201            | Elasticsearch node `es02` — REST endpoint       |

To stop:

```bash
docker compose down          # keep data in volumes
docker compose down -v       # also delete all indexed data
```

---

## Project layout

```
es-lab/
├── docker-compose.yml           # Orchestrates 6 containers
├── README.md                    # This file
│
├── api/                         # FastAPI backend
│   ├── Dockerfile
│   ├── requirements.txt
│   └── main.py                  # All ES interaction logic
│
├── ui/                          # Static Tailwind UI
│   └── index.html               # One file, no build step
│
├── go-watchdog/                 # Failover detector
│   ├── Dockerfile
│   ├── go.mod
│   └── main.go                  # ~100 lines, stdlib-only
│
├── sample-data/
│   ├── shards-intro.txt
│   └── failover-notes.txt
│
└── load_and_search.py           # Standalone Python teaching script (no API)
```

---

## Component reference

### Elasticsearch nodes (es01, es02)

Both nodes run `elasticsearch:8.13.4` (pinned — never use `:latest` in a lab you want repeatable). Key settings:

| Setting                         | Value          | Why                                           |
| ------------------------------- | -------------- | --------------------------------------------- |
| `cluster.name`                  | `lab-cluster`  | Groups the two nodes into one cluster         |
| `discovery.seed_hosts`          | Peer's name    | How a node finds its partner at boot          |
| `cluster.initial_master_nodes`  | `es01,es02`    | Bootstrap vote — required on first boot only  |
| `bootstrap.memory_lock`         | `true`         | Locks JVM heap in RAM; prevents swap death    |
| `xpack.security.enabled`        | `false`        | Lab only — production always `true`           |
| `ES_JAVA_OPTS`                  | `-Xms512m -Xmx512m` | Fixed heap size, laptop-friendly         |

**Ports published:** es01 → host `9200`, es02 → host `9201`. Both listen on `9200` internally.

**Volumes:** `es01-data` and `es02-data` are named Docker volumes. They survive `docker compose down` but are removed by `docker compose down -v`.

### Kibana

Runs `kibana:8.13.4`, wired to both ES nodes as a list:

```yaml
ELASTICSEARCH_HOSTS=["http://es01:9200","http://es02:9200"]
```

Kibana round-robins and transparently fails over. If you listed only one node and that node died, Kibana would show a blank page even though half the cluster is fine.

**Useful Kibana views:**

- **Dev Tools** (left sidebar, wrench icon) — run raw ES queries
- **Stack Management → Index Management** — see every index, shard count, storage
- **Discover** — explore documents with field filters
- **Stack Monitoring** — cluster health, JVM metrics, shard allocation

### FastAPI backend

Located in `api/main.py`. Exposes the following on port `8000`:

- `GET /health` — cluster health + node list
- `POST /indices` — create an index with custom mapping (shards, replicas, text/keyword fields)
- `GET /indices` — list all indices with doc count and storage
- `DELETE /indices/{name}` — delete an index
- `PUT /indices/{name}/settings` — update settings (e.g., change replica count at runtime)
- `POST /documents/{index}` — index a JSON document
- `POST /documents/upload` — upload a text file with metadata
- `GET /documents/{index}/{id}` — fetch by ID
- `DELETE /documents/{index}/{id}` — delete by ID
- `GET /search` — search with optional `q`, `field`, `keyword` parameters
- `GET /cluster/shards` — raw shard allocation table

See the auto-generated Swagger at [http://localhost:8000/docs](http://localhost:8000/docs).

**Client configuration — the key line:**

```python
ES_NODES = os.environ.get("ES_NODES", "http://localhost:9200").split(",")
es = Elasticsearch(ES_NODES, request_timeout=10, max_retries=3, retry_on_timeout=True)
```

The client takes a **list** of nodes. It maintains a connection pool, detects dead nodes, and routes requests around them. This is client-side failover — no proxy needed.

### Tailwind UI

A single static `ui/index.html` served by nginx. No build step — Tailwind is loaded from a CDN at runtime. Binds to the API on `:8000` via CORS.

Five tabs, each targeting one teaching concept:

1. **Build Index** — configure shards/replicas/field types, preview mapping JSON, create
2. **Load Data** — upload text files with author/tags metadata, or post raw JSON
3. **Search** — three combinable modes: free-text, field-scoped, exact keyword filter
4. **Cluster & Shards** — live grid of shard allocation, auto-refreshing every 3 seconds
5. **Simulate Failover** — guided drill with `docker stop` commands and expected behavior

### Go watchdog

A 60-line program in `go-watchdog/main.go`. Polls both ES nodes every 3 seconds, tracks per-node state, and logs **only on transitions**:

```
🎯 ACTIVE node is http://es01:9200
🌡  cluster status: unknown → green  (2 nodes, 4 active / 0 unassigned)
❌ FAILED     http://es02:9200  (context deadline exceeded)
🌡  cluster status: green → yellow  (1 nodes, 2 active / 2 unassigned)
✅ RECOVERED  http://es02:9200
🌡  cluster status: yellow → green  (2 nodes, 4 active / 0 unassigned)
```

The state machine has four transitions per node: `down→up`, `up→down`, `up→up`, `down→down`. Only the first two are logged. This is **edge-triggered monitoring** — the pattern behind every real alerting system.

View the live log with:

```bash
docker logs -f watchdog
```

---

## Using the UI — five tabs, in order

### Tab 1: Build Index

1. Enter an index name (e.g., `articles`)
2. Choose shards (default 2) and replicas (default 1)
3. Mark fields as `text` (full-text searchable, tokenized) or `keyword` (exact-match, filterable)
4. Preview the generated mapping JSON
5. Click **Create index**

**What happens under the hood:** the UI POSTs to `/indices` with an `IndexSpec` body. The API builds the Elasticsearch mapping (with the `.keyword` sub-field trick for text fields — see [Understanding mappings](#understanding-mappings-text-vs-keyword)) and calls `es.indices.create()`.

### Tab 2: Load Data

Two flows:

- **Upload .txt file** with filename, author, tags → indexed as `{title, content, author, tags, ingested_at}`
- **Raw JSON** — paste any document, sent to `POST /documents/{index}`

Both use `refresh=wait_for` so the document is searchable immediately.

### Tab 3: Search

Three query parameters, all optional, all combinable:

| Parameter | Effect                                            | Example                   |
| --------- | ------------------------------------------------- | ------------------------- |
| `q`       | Free-text query across all fields with boosting   | `shards`                  |
| `field`   | Restrict `q` to one field                         | `field=title`             |
| `keyword` | Exact-match filter on `field:value`               | `keyword=author:alice`    |

Results include highlighted matches (via ES's `highlight` feature) and BM25 relevance scores.

### Tab 4: Cluster & Shards

Live grid showing every shard: which index, shard number, primary or replica, which node it's on, current state, doc count. Auto-refreshes every 3 seconds.

Also lets you **change replica count at runtime** — watch yellow→green as replicas get allocated, or green→yellow if you crank them up past what your node count can support.

### Tab 5: Simulate Failover

A guided walk of the failover drill. See [The failover drill](#the-failover-drill) below.

---

## API reference

| Method | Path                                  | Purpose                              |
| ------ | ------------------------------------- | ------------------------------------ |
| GET    | `/health`                             | Cluster health + node count          |
| POST   | `/indices`                            | Create index with mapping            |
| GET    | `/indices`                            | List all indices                     |
| DELETE | `/indices/{name}`                     | Delete index                         |
| PUT    | `/indices/{name}/settings`            | Update settings (e.g. replicas)      |
| POST   | `/documents/{index}`                  | Index JSON doc                       |
| POST   | `/documents/upload`                   | Upload text file with metadata       |
| GET    | `/documents/{index}/{id}`             | Fetch doc by ID                      |
| DELETE | `/documents/{index}/{id}`             | Delete doc by ID                     |
| GET    | `/search`                             | Search with `q`, `field`, `keyword`  |
| GET    | `/cluster/shards`                     | Raw shard allocation                 |

Full OpenAPI spec at [http://localhost:8000/docs](http://localhost:8000/docs) and [http://localhost:8000/redoc](http://localhost:8000/redoc).

### Example requests

```bash
# Health
curl http://localhost:8000/health

# Create index
curl -X POST http://localhost:8000/indices \
  -H 'Content-Type: application/json' \
  -d '{"name":"articles","shards":2,"replicas":1,
       "text_fields":["title","content"],
       "keyword_fields":["author","tags"]}'

# Index a document
curl -X POST http://localhost:8000/documents/articles \
  -H 'Content-Type: application/json' \
  -d '{"title":"Intro to shards","content":"...","author":"alice","tags":["elasticsearch"]}'

# Upload a text file
curl -X POST http://localhost:8000/documents/upload \
  -F 'file=@sample-data/shards-intro.txt' \
  -F 'author=alice' \
  -F 'tags=elasticsearch,tutorial'

# Search
curl "http://localhost:8000/search?q=shards&keyword=author:alice"
```

---

## The failover drill

The most important exercise in this lab. Takes about 90 seconds.

### Setup — three terminal windows

**Terminal 1** — watch the cluster state:

```bash
docker logs -f watchdog
```

**Terminal 2** — prove the API never goes down:

```bash
while true; do
  curl -s http://localhost:8000/search?q=shards | jq '.total'
  sleep 1
done
# The number should never drop to 0 or error, even during failover
```

**Terminal 3** — the trigger:

```bash
# Kill one node
docker stop es02

# Wait 15-30 seconds. Watch terminal 1.
# You'll see: ❌ FAILED and cluster status green → yellow

# Bring it back
docker start es02

# Wait 20-30 seconds. Watch terminal 1.
# You'll see: ✅ RECOVERED and cluster status yellow → green
```

### What just happened

| Time       | State change                                                           |
| ---------- | ---------------------------------------------------------------------- |
| `t=0`      | Everything green. 2 nodes, 4 shards (2 primary + 2 replica).           |
| `t=1s`     | `docker stop es02` fires. es02 sends no final goodbye (SIGKILL).       |
| `t≈10s`    | es01 fails peer heartbeats. Cluster state becomes YELLOW.              |
| `t≈10s`    | Replicas on es01 get promoted to primary. All 2 primaries now on es01. |
| `t≈10s`    | Watchdog logs `❌ FAILED`. User-facing searches continue uninterrupted. |
| `t+30s`    | `docker start es02`. Node rejoins cluster on boot.                     |
| `t+30-60s` | Shards replicate from es01 to es02. Cluster returns to GREEN.          |
| `t+60s`    | Watchdog logs `✅ RECOVERED`.                                          |

**Zero data loss. Zero downtime from the user's perspective.** This works because the Python ES client was constructed with *both* node URLs — when es02 stops responding, the client transparently routes every request to es01.

---

## Understanding mappings: text vs keyword

The single most important mapping decision in Elasticsearch.

### Input: the string `"Quick Brown Foxes"`

Mapped as **`text`**:

```
1. Tokenize (split)   → ["Quick", "Brown", "Foxes"]
2. Lowercase filter   → ["quick", "brown", "foxes"]
3. Store in inverted  → quick → [doc1]
   index                 brown → [doc1]
                         foxes → [doc1]

Match query matches:  "quick" ✓  "FOX" ✓  "foxes" ✓  "brown fox" ✓
```

Mapped as **`keyword`**:

```
1. Stored as-is        → "Quick Brown Foxes"
2. (no transformation) → "Quick Brown Foxes"
3. Stored as single    → "Quick Brown Foxes" → [doc1]
   term

Term query matches:   only exact "Quick Brown Foxes"
```

### Use `text` for

- Body content, article text, product descriptions
- Anywhere users type free-form queries
- Fields where fuzzy matching ("foxes" finds "fox") is desired

### Use `keyword` for

- IDs, SKUs, email addresses, hostnames
- Tags, categories, enum-like values
- Anything you'll **filter** on (`author:alice`)
- Anything you'll **aggregate** on (count by category)
- Anything you'll **sort** alphabetically

### The sub-field trick

The API maps text fields like this:

```json
{
  "title": {
    "type": "text",
    "fields": {
      "keyword": { "type": "keyword", "ignore_above": 256 }
    }
  }
}
```

Now you can query `title` for fuzzy full-text search **and** `title.keyword` for exact filtering. One field, two behaviors, no storage duplication you have to manage.

### The classic bug

You let ES dynamically map a field called `status`. Docs come in with `"PENDING"`, `"COMPLETE"`. ES infers `text`, applies the lowercase filter. Now `{"term": {"status": "PENDING"}}` returns zero hits — because the tokens stored are `pending`, not `PENDING`. Always declare mappings explicitly in production.

---

## Configuration

All configuration is environment variables in `docker-compose.yml`. Override for your environment by creating `.env`:

```bash
# .env
ES_IMAGE_TAG=8.13.4
ES_HEAP=-Xms1g -Xmx1g
API_PORT=8000
UI_PORT=8080
```

Reference common adjustments in the compose file with `${VAR:-default}`:

```yaml
environment:
  - ES_JAVA_OPTS=${ES_HEAP:--Xms512m -Xmx512m}
```

### Scaling down for low-memory machines

On a laptop with <8 GB RAM, drop heap to 256m:

```yaml
- "ES_JAVA_OPTS=-Xms256m -Xmx256m"
```

Also reduce Kibana memory if needed by removing it from the compose file entirely — the API and UI don't depend on it.

---

## Troubleshooting

### `vm.max_map_count` error on Linux

```
bootstrap check failure: max virtual memory areas vm.max_map_count [65530]
is too low, increase to at least [262144]
```

Fix:

```bash
sudo sysctl -w vm.max_map_count=262144
# Make it persist across reboots:
echo 'vm.max_map_count=262144' | sudo tee -a /etc/sysctl.conf
```

### One ES node won't start

Check the logs:

```bash
docker compose logs es01
docker compose logs es02
```

Common causes:
- Not enough memory allocated to Docker (need 4 GB minimum)
- Stale volume from a previous run with different settings → `docker compose down -v` and try again
- Port collision — something else is on 9200/9201 → change the host ports

### Cluster stays yellow forever

Yellow means "primaries OK, replicas not assigned." If you have replicas=1 but only one node is up, this is expected and correct. It's only a problem if both nodes are up and the state is still yellow after 60 seconds.

Check shard allocation:

```bash
curl "http://localhost:9200/_cluster/allocation/explain?pretty"
```

### API returns 503 on startup

The API's `depends_on` includes `condition: service_healthy` for both ES nodes. If one ES healthcheck is failing, the API won't start. Check:

```bash
docker compose ps
# Look for "unhealthy" status on es01 or es02
```

### Watchdog logs `failed to connect` repeatedly

The watchdog reads `ES_NODES` from its environment. If you changed the service names in compose, update that env var too.

---

## Moving to AWS

Every container in this lab has an AWS equivalent. The architectural shape is identical — storage, compute, network, monitoring — but the operational burden drops by ~80% because AWS runs most of it.

| This lab                | AWS (managed path)                          | AWS (self-managed path)          |
| ----------------------- | ------------------------------------------- | -------------------------------- |
| `es01`, `es02`          | **Amazon OpenSearch Service**               | EKS + opensearch-operator        |
| Docker volumes          | EBS gp3 (hidden)                            | EBS gp3 via EBS CSI driver       |
| Docker bridge network   | VPC with 3-AZ private subnets               | VPC with 3-AZ private subnets    |
| Host ports 9200/9201    | Internal Application Load Balancer          | Internal ALB                     |
| Kibana                  | OpenSearch Dashboards (bundled)             | Separate deployment              |
| FastAPI container       | ECS Fargate or EKS Deployment + ALB         | Same                             |
| nginx static UI         | **S3 bucket + CloudFront distribution**     | Same                             |
| Go watchdog             | **CloudWatch Alarm + SNS topic**            | Prometheus + Alertmanager        |
| (no backups)            | **S3 snapshot repository** (automatic)      | Manual SLM policy to S3          |
| Secrets in env vars     | **AWS Secrets Manager + IAM role**          | Same                             |

### The key difference

On AWS Managed OpenSearch, you stop owning the failure modes of the data plane. AWS runs the nodes, replaces failed hardware, applies security patches, handles master election, and snapshots to S3 without you lifting a finger. Your watchdog becomes a CloudWatch Alarm. Your volumes become opaque. You go from operating a cluster to consuming it.

**Trade-offs:**
- Can't install arbitrary plugins
- ~6–12 months behind the latest OpenSearch release
- ~20–30% cost premium over raw EC2

For ~90% of workloads, that's the right trade.

---

## Production checklist

What must change before this stack carries a single real user request:

1. **Enable security.** Set `xpack.security.enabled=true`, generate TLS certs, configure TLS on HTTP (`:9200`) and transport (`:9300`) layers. Put credentials in Secrets Manager, not env vars.
2. **Go from 2 nodes to 3 + 3.** Two master-eligible nodes can split-brain. Run at least 3 dedicated masters and 3+ dedicated data nodes.
3. **Put a load balancer in front.** Never publish ES ports to clients directly. Use an internal ALB with healthchecks against `/_cluster/health`.
4. **Scheduled snapshots to S3.** Register a repository, enable SLM with 14-day retention, run daily at off-peak.
5. **Test a restore quarterly.** An untested backup isn't a backup — it's a claim.
6. **JVM heap at 50% of RAM, cap 31 GB.** Above 32 GB, the JVM loses compressed object pointers.
7. **Alert on leading indicators.** Status not green for 5 min; disk >75%; JVM heap >85% sustained; any thread pool rejections.
8. **ILM / ISM policies for time-series indices.** Roll over and delete old data automatically.
9. **Harden the API Dockerfile.** Non-root `USER 1000`, pinned digest, `HEALTHCHECK`, remove `CORSMiddleware(allow_origins=["*"])`.
10. **Replace the watchdog with CloudWatch Alarms.** It's pedagogy — production uses native cloud monitoring with proper routing and escalation.

---

## Further reading

- [Elasticsearch Reference — Set up Elasticsearch](https://www.elastic.co/guide/en/elasticsearch/reference/current/setup.html)
- [Elasticsearch Reference — Mapping](https://www.elastic.co/guide/en/elasticsearch/reference/current/mapping.html)
- [Elasticsearch Reference — Query DSL](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl.html)
- [Amazon OpenSearch Service Developer Guide](https://docs.aws.amazon.com/opensearch-service/)
- [Discovery and cluster formation](https://www.elastic.co/guide/en/elasticsearch/reference/current/modules-discovery.html)
- [Sizing guidance — heap, shards, and nodes](https://www.elastic.co/guide/en/elasticsearch/reference/current/size-your-shards.html)

---

## License

Public domain — use it, modify it, teach with it, ship it.