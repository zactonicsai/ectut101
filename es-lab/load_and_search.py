"""
load_and_search.py — standalone teaching script.

Demonstrates, outside the API, how to talk to Elasticsearch directly:
  1. connect to the cluster with automatic failover across nodes
  2. create an index with explicit mappings and a chosen shard count
  3. bulk-index a handful of documents
  4. run three kinds of searches: full-text, field-scoped, exact-keyword

Run from the host (after `docker compose up -d`):

    pip install elasticsearch==8.13.2
    python load_and_search.py
"""
from datetime import datetime, timezone

from elasticsearch import Elasticsearch, helpers

# ---------------------------------------------------------------------------
# 1. connect — pass both nodes so the client can transparently fail over
# ---------------------------------------------------------------------------
es = Elasticsearch(
    ["http://localhost:9200", "http://localhost:9201"],
    request_timeout=10,
    max_retries=3,
    retry_on_timeout=True,
)

print("cluster info:", es.info()["cluster_name"])
print("health:     ", es.cluster.health()["status"])

INDEX = "articles"

# ---------------------------------------------------------------------------
# 2. create index with explicit mappings
# ---------------------------------------------------------------------------
mapping = {
    "settings": {
        "number_of_shards": 2,       # split data across 2 primaries
        "number_of_replicas": 1,     # one replica of each -> total 4 shards
        "refresh_interval": "1s",
    },
    "mappings": {
        "properties": {
            "title":       {"type": "text"},                      # analyzed
            "content":     {"type": "text"},                      # analyzed
            "author":      {"type": "keyword"},                   # exact match
            "tags":        {"type": "keyword"},                   # exact match, array-friendly
            "published":   {"type": "date"},
            "views":       {"type": "integer"},
        }
    },
}

if es.indices.exists(index=INDEX):
    es.indices.delete(index=INDEX)
es.indices.create(index=INDEX, body=mapping)
print(f"index '{INDEX}' created with 2 primary shards + 1 replica each")

# ---------------------------------------------------------------------------
# 3. bulk-load sample docs
# ---------------------------------------------------------------------------
sample_docs = [
    {
        "title": "Getting started with Elasticsearch",
        "content": "Elasticsearch is a distributed search and analytics engine built on Lucene.",
        "author": "alice",
        "tags": ["intro", "search"],
        "published": "2025-01-10",
        "views": 420,
    },
    {
        "title": "Understanding shards and replicas",
        "content": "A shard is the unit of parallelism. Replicas give you redundancy and read throughput.",
        "author": "bob",
        "tags": ["shards", "advanced"],
        "published": "2025-02-14",
        "views": 315,
    },
    {
        "title": "Index mapping patterns",
        "content": "Use 'keyword' for exact matches and 'text' for analyzed full-text search.",
        "author": "alice",
        "tags": ["mapping", "schema"],
        "published": "2025-03-02",
        "views": 812,
    },
    {
        "title": "Cluster failover in practice",
        "content": "When a data node drops, the cluster promotes replicas to primaries automatically.",
        "author": "carol",
        "tags": ["failover", "operations"],
        "published": "2025-03-20",
        "views": 199,
    },
    {
        "title": "Bulk indexing best practices",
        "content": "Use the _bulk API with batches of 1000-5000 docs for maximum throughput.",
        "author": "bob",
        "tags": ["performance", "bulk"],
        "published": "2025-04-01",
        "views": 675,
    },
]

# `helpers.bulk` handles batching and connection reuse for you
actions = [{"_index": INDEX, "_source": d} for d in sample_docs]
success, _ = helpers.bulk(es, actions, refresh="wait_for")
print(f"indexed {success} documents")


# ---------------------------------------------------------------------------
# 4. three kinds of search — pick the right tool for the question
# ---------------------------------------------------------------------------
def show(label: str, result) -> None:
    print(f"\n── {label} ── (took {result['took']}ms, {result['hits']['total']['value']} hits)")
    for h in result["hits"]["hits"]:
        print(f"  [{h['_score']:.2f}]  {h['_source']['title']}  (by {h['_source']['author']})")


# (a) full-text across all fields — fuzzy, stemmed, scored
r = es.search(
    index=INDEX,
    query={"multi_match": {"query": "shards failover", "fields": ["title", "content"]}},
)
show("full-text: 'shards failover'", r)

# (b) exact keyword filter — by author
r = es.search(
    index=INDEX,
    query={"term": {"author": "alice"}},
)
show("keyword filter: author = alice", r)

# (c) combined: bool query with must + filter + sort
r = es.search(
    index=INDEX,
    query={
        "bool": {
            "must":   [{"match": {"content": "indexing"}}],
            "filter": [{"term": {"tags": "performance"}}],
        }
    },
    sort=[{"views": "desc"}],
)
show("full-text 'indexing' AND tag=performance, sorted by views", r)

# ---------------------------------------------------------------------------
# 5. show the shard layout — how ES spread the data across our 2 nodes
# ---------------------------------------------------------------------------
print("\n── shard layout ──")
shards = es.cat.shards(index=INDEX, format="json", h="shard,prirep,state,docs,node")
for s in shards:
    print(f"  shard {s['shard']} {s['prirep']} -> {s['node']:<12} ({s['docs']} docs, {s['state']})")

print("\nnext: try  docker stop es02  and re-run this script to watch the cluster reshape.")
