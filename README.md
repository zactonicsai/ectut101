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
