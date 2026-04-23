"""
Elasticsearch Learning Lab — FastAPI backend.

Endpoints
---------
GET    /health               -- cluster + node health
GET    /indices              -- list all indices with stats
POST   /indices              -- create index with custom shards/replicas/mappings
DELETE /indices/{name}       -- delete an index
PUT    /indices/{name}/settings -- update replicas / refresh_interval live

POST   /documents            -- index a single JSON document
POST   /documents/upload     -- upload a .txt file as a document
GET    /search               -- search by field, keyword, or full-text
GET    /documents/{id}       -- fetch one document
DELETE /documents/{id}       -- delete one document

GET    /cluster/shards       -- show which shard is where (for failover demos)
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from elasticsearch import Elasticsearch, NotFoundError, ApiError
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------
ES_NODES = os.environ.get("ES_NODES", "http://localhost:9200").split(",")
INDEX_NAME = os.environ.get("INDEX_NAME", "documents")

# The elasticsearch client accepts a list of nodes.  If the first is down
# it automatically retries the next one — this is our client-side failover.
es = Elasticsearch(
    ES_NODES,
    request_timeout=10,
    max_retries=3,
    retry_on_timeout=True,
)

app = FastAPI(
    title="Elasticsearch Learning Lab API",
    description="Teaches: index creation, sharding, field search, and failover.",
    version="1.0.0",
)

# UI is served from a different origin (nginx on :8080), so allow CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------------------
# Pydantic models
# ----------------------------------------------------------------------------
class IndexSpec(BaseModel):
    """Create-an-index request. The UI submits this when the 'Build Index'
    button is clicked.

    keyword_fields: fields to map as 'keyword' (exact match, aggregatable)
    text_fields:    fields to map as 'text'    (analyzed, full-text search)
    """
    name: str = Field(..., description="Index name, e.g. 'articles'")
    shards: int = Field(2, ge=1, le=10, description="Primary shard count")
    replicas: int = Field(1, ge=0, le=5, description="Replicas per shard")
    keyword_fields: list[str] = Field(default_factory=list)
    text_fields: list[str] = Field(default_factory=lambda: ["content", "title"])


class DocumentIn(BaseModel):
    """A generic document.  `content` is the main searchable text,
    everything in `metadata` is a dict of keyword fields (tags, author, etc.)."""
    title: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class IndexSettingsUpdate(BaseModel):
    replicas: Optional[int] = None
    refresh_interval: Optional[str] = None  # e.g. "1s", "30s", "-1"


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def build_mapping(spec: IndexSpec) -> dict:
    """Turn the UI's field lists into a proper ES mapping.

    Teaching note:
      - 'keyword'  => stored as-is, good for filtering and aggregations
      - 'text'     => analyzed (tokenized, lowercased), good for search
    """
    props: dict[str, dict] = {
        # every doc gets an ingest timestamp — handy for sorting and ILM
        "ingested_at": {"type": "date"},
    }
    for f in spec.text_fields:
        # Common trick: map as text WITH a .keyword sub-field for aggregations
        props[f] = {"type": "text", "fields": {"keyword": {"type": "keyword", "ignore_above": 256}}}
    for f in spec.keyword_fields:
        props[f] = {"type": "keyword"}
    return {
        "settings": {
            "number_of_shards": spec.shards,
            "number_of_replicas": spec.replicas,
            "refresh_interval": "1s",
        },
        "mappings": {"properties": props},
    }


# ----------------------------------------------------------------------------
# Health
# ----------------------------------------------------------------------------
@app.get("/health")
def health():
    """Cluster + per-node status — the UI polls this every few seconds."""
    nodes_status = []
    for url in ES_NODES:
        try:
            single = Elasticsearch([url], request_timeout=2, max_retries=0)
            info = single.info()
            nodes_status.append({"url": url, "status": "up", "name": info["name"]})
        except Exception as exc:
            nodes_status.append({"url": url, "status": "down", "error": str(exc)[:120]})

    cluster = {}
    try:
        cluster = es.cluster.health().body
    except Exception as exc:
        cluster = {"status": "unreachable", "error": str(exc)[:120]}

    return {"nodes": nodes_status, "cluster": cluster}


# ----------------------------------------------------------------------------
# Index management
# ----------------------------------------------------------------------------
@app.get("/indices")
def list_indices():
    """List every index with doc count, size, and primary/replica layout."""
    # _cat endpoints return simple rows — great for teaching
    cats = es.cat.indices(format="json", h="index,health,status,pri,rep,docs.count,store.size").body
    return cats


@app.post("/indices", status_code=201)
def create_index(spec: IndexSpec):
    if es.indices.exists(index=spec.name):
        raise HTTPException(409, f"Index '{spec.name}' already exists")
    es.indices.create(index=spec.name, body=build_mapping(spec))
    return {"created": spec.name, "mapping": build_mapping(spec)}


@app.delete("/indices/{name}")
def delete_index(name: str):
    try:
        es.indices.delete(index=name)
        return {"deleted": name}
    except NotFoundError:
        raise HTTPException(404, f"Index '{name}' not found")


@app.put("/indices/{name}/settings")
def update_index_settings(name: str, body: IndexSettingsUpdate):
    """Live-update index settings.  Useful to demo:
       - raising replicas from 0 -> 1 after initial bulk load
       - setting refresh_interval=-1 during big imports, then back to 1s
    """
    payload: dict[str, Any] = {}
    if body.replicas is not None:
        payload["number_of_replicas"] = body.replicas
    if body.refresh_interval is not None:
        payload["refresh_interval"] = body.refresh_interval
    if not payload:
        raise HTTPException(400, "No settings provided")
    es.indices.put_settings(index=name, body={"index": payload})
    return {"updated": name, "settings": payload}


# ----------------------------------------------------------------------------
# Document CRUD
# ----------------------------------------------------------------------------
@app.post("/documents", status_code=201)
def index_document(doc: DocumentIn, index: str = INDEX_NAME):
    # auto-create the default index with sensible shards if missing
    if not es.indices.exists(index=index):
        es.indices.create(
            index=index,
            body=build_mapping(IndexSpec(name=index)),
        )
    body = {
        "title": doc.title,
        "content": doc.content,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        **doc.metadata,  # metadata keys become top-level fields
    }
    doc_id = str(uuid.uuid4())
    es.index(index=index, id=doc_id, document=body, refresh="wait_for")
    return {"id": doc_id, "index": index}


@app.post("/documents/upload", status_code=201)
async def upload_text_file(
    file: UploadFile = File(...),
    index: str = Form(INDEX_NAME),
    tags: str = Form(""),            # comma-separated, stored as keyword list
    author: str = Form("unknown"),
):
    """Upload a .txt file; its contents become the 'content' field."""
    raw = (await file.read()).decode("utf-8", errors="replace")
    if not es.indices.exists(index=index):
        es.indices.create(
            index=index,
            body=build_mapping(IndexSpec(
                name=index,
                keyword_fields=["author", "tags", "filename"],
            )),
        )
    body = {
        "title": file.filename,
        "filename": file.filename,
        "content": raw,
        "author": author,
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }
    doc_id = str(uuid.uuid4())
    es.index(index=index, id=doc_id, document=body, refresh="wait_for")
    return {"id": doc_id, "index": index, "size_bytes": len(raw)}


@app.get("/documents/{doc_id}")
def get_document(doc_id: str, index: str = INDEX_NAME):
    try:
        return es.get(index=index, id=doc_id).body
    except NotFoundError:
        raise HTTPException(404, "Document not found")


@app.delete("/documents/{doc_id}")
def delete_document(doc_id: str, index: str = INDEX_NAME):
    try:
        es.delete(index=index, id=doc_id, refresh="wait_for")
        return {"deleted": doc_id}
    except NotFoundError:
        raise HTTPException(404, "Document not found")


# ----------------------------------------------------------------------------
# Search
# ----------------------------------------------------------------------------
@app.get("/search")
def search(
    q: str = "",                                 # free-text query
    field: Optional[str] = None,                 # restrict to a field
    keyword: Optional[str] = None,               # exact keyword match (a.b=c style)
    index: str = INDEX_NAME,
    size: int = 10,
):
    """Three modes, combinable:

      /search?q=machine learning              -> full-text across all fields
      /search?q=pipeline&field=title          -> full-text inside 'title' only
      /search?keyword=author:alice            -> exact match on author='alice'
      /search?q=ml&keyword=tags:internal      -> mix of the two
    """
    must: list[dict] = []

    if q:
        if field:
            must.append({"match": {field: q}})
        else:
            must.append({
                "multi_match": {
                    "query": q,
                    "fields": ["title^3", "content", "*"],  # title weighted 3x
                    "fuzziness": "AUTO",
                }
            })

    if keyword and ":" in keyword:
        k, v = keyword.split(":", 1)
        must.append({"term": {k: v}})

    query = {"match_all": {}} if not must else {"bool": {"must": must}}

    try:
        result = es.search(
            index=index,
            query=query,
            size=size,
            highlight={"fields": {"content": {}, "title": {}}},
        )
    except ApiError as exc:
        raise HTTPException(400, f"Search error: {exc.info}")

    hits = [
        {
            "id": h["_id"],
            "score": h["_score"],
            "source": h["_source"],
            "highlight": h.get("highlight", {}),
        }
        for h in result["hits"]["hits"]
    ]
    return {
        "total": result["hits"]["total"]["value"],
        "took_ms": result["took"],
        "hits": hits,
    }


# ----------------------------------------------------------------------------
# Cluster / shard inspection — powers the failover demo
# ----------------------------------------------------------------------------
@app.get("/cluster/shards")
def shards(index: Optional[str] = None):
    """Show every shard: which index, primary or replica, and which node holds it.

    After you `docker stop es02`, refresh this to watch replicas get promoted
    to primaries and re-allocate.
    """
    kwargs = {"format": "json", "h": "index,shard,prirep,state,docs,store,node"}
    if index:
        kwargs["index"] = index
    return es.cat.shards(**kwargs).body
