"""
 Copyright (c) 2026. DENODO Technologies.
 http://www.denodo.com
 All rights reserved.
"""

"""Qdrant adapter for UniformVectorStore.

Two things differ from the other backends and are handled here:
  - Qdrant point ids must be UUIDs or integers, while the SDK uses strings such
    as "42_0" and "last_update". Ids are mapped deterministically with uuid5.

  - Filters arrive in the Chroma-style dict format that UniformVectorStore builds
    for Chroma, PGVector and Oracle ($and, $or, $eq, $in). They are translated
    to a Qdrant Filter.
"""

import logging
import os
import uuid

# Stable namespace for deriving Qdrant point ids from the SDK's string ids.
# Never change it: doing so orphans every previously written point.
SDK_ID_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")

VECTOR_NAME = "dense"

# Metadata fields the SDK filters on with a fixed name. Tags use one dynamic key
# per tag (tag_<name>), so they cannot be covered by a static payload index.
INDEXED_PAYLOAD_FIELDS = (
    "metadata.view_id",
    "metadata.view_name",
    "metadata.database_name",
)


def point_id(sdk_id):
    """Map an SDK document id to a Qdrant point id, deterministically.

    Deterministic so that re-syncing a view overwrites its point instead of
    duplicating it, and deletes can address a point without a lookup.
    """
    return str(uuid.uuid5(SDK_ID_NAMESPACE, str(sdk_id)))


def is_local():
    """True for the in-memory and embedded on-disk modes, which have no server."""
    return bool(os.getenv("QDRANT_LOCATION", "").strip() or os.getenv("QDRANT_PATH", "").strip())


def build_client():
    """Connect to Qdrant: in-memory, embedded on-disk, or a server."""
    from qdrant_client import QdrantClient

    location = os.getenv("QDRANT_LOCATION", "").strip()
    path = os.getenv("QDRANT_PATH", "").strip()
    url = os.getenv("QDRANT_URL", "").strip()
    api_key = os.getenv("QDRANT_API_KEY", "").strip() or None
    timeout = int(os.getenv("QDRANT_TIMEOUT", "60"))

    if location:
        return QdrantClient(location=location, timeout=timeout)

    if path:
        return QdrantClient(path=path, timeout=timeout)

    url = url or "http://localhost:6333"

    return QdrantClient(
        url=url,
        api_key=api_key,
        timeout=timeout,
        prefer_grpc=os.getenv("QDRANT_PREFER_GRPC", "0") == "1",
        https=os.getenv("QDRANT_HTTPS", "0") == "1" or url.startswith("https://"),
    )


def ensure_collection(client, collection_name, dimensions):
    """Create the collection (cosine distance) and its payload indexes if absent."""
    from qdrant_client import models

    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config={
                VECTOR_NAME: models.VectorParams(size=dimensions, distance=models.Distance.COSINE)
            },
        )
        logging.info(f"Created Qdrant collection '{collection_name}' (dim={dimensions})")

    # The local modes ignore payload indexes (and warn about it).
    if is_local():
        return

    for field in INDEXED_PAYLOAD_FIELDS:
        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
                wait=True,
            )
        except Exception:
            # Already present. A missing index only costs speed, never correctness.
            pass


def translate_filter(sdk_filter):
    """Translate a Chroma-style filter dict into a Qdrant Filter (None if empty)."""
    from qdrant_client import models

    if not sdk_filter:
        return None

    def to_condition(node):
        if "$and" in node:
            return models.Filter(must=[to_condition(child) for child in node["$and"]])

        if "$or" in node:
            return models.Filter(should=[to_condition(child) for child in node["$or"]])

        (field, operation), = node.items()
        key = f"metadata.{field}"

        if "$eq" in operation:
            return models.FieldCondition(key=key, match=models.MatchValue(value=operation["$eq"]))
        
        if "$in" in operation:
            return models.FieldCondition(key=key, match=models.MatchAny(any=list(operation["$in"])))

        raise ValueError(f"Unsupported filter operation for Qdrant: {operation}")

    condition = to_condition(sdk_filter)
    return condition if isinstance(condition, models.Filter) else models.Filter(must=[condition])


class QdrantStore:
    def __init__(self, collection_name, embeddings, dimensions):
        self.collection_name = collection_name
        self.embeddings = embeddings
        self.client = build_client()
        ensure_collection(self.client, collection_name, dimensions)

    def add_documents(self, documents, ids=None, **kwargs):
        from qdrant_client import models

        ids = ids or [document.id for document in documents]
        vectors = self.embeddings.embed_documents([document.page_content for document in documents])

        points = [
            models.PointStruct(
                id=point_id(sdk_id),
                vector={VECTOR_NAME: vector},
                payload={
                    "page_content": document.page_content,
                    "metadata": document.metadata,
                    
                    # Kept so a result can be traced back to the id the SDK uses.
                    "sdk_id": str(sdk_id),
                },
            )
            for document, sdk_id, vector in zip(documents, ids, vectors)
        ]

        self.client.upsert(collection_name=self.collection_name, points=points, wait=True)
        
        return list(ids)

    def delete(self, ids=None, **kwargs):
        from qdrant_client import models

        if not ids:
            return

        self.client.delete(
            collection_name=self.collection_name,
            points_selector=models.PointIdsList(points=[point_id(sdk_id) for sdk_id in ids]),
            wait=True,
        )

    def _query(self, vector, k, sdk_filter, with_scores):
        from langchain_core.documents import Document

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=vector,
            using=VECTOR_NAME,
            limit=k,
            query_filter=translate_filter(sdk_filter),
            with_payload=True,
        )

        results = []
        for point in response.points:
            payload = point.payload or {}

            document = Document(
                id=payload.get("sdk_id"),
                page_content=payload.get("page_content", ""),
                metadata=payload.get("metadata") or {},
            )

            # Qdrant returns cosine similarity (higher is better). The other
            # providers return a distance (lower is better), and the SDK merges
            # batched results assuming that, so report `1 - similarity`.
            results.append((document, 1.0 - point.score) if with_scores else document)

        return results

    def similarity_search_by_vector(self, embedding, k=4, filter=None, **kwargs):
        return self._query(embedding, k, filter, with_scores=False)

    def similarity_search_with_score_by_vector(self, embedding, k=4, filter=None, **kwargs):
        return self._query(embedding, k, filter, with_scores=True)

    def similarity_search(self, query, k=4, filter=None, **kwargs):
        return self._query(self.embeddings.embed_query(query), k, filter, with_scores=False)

    def similarity_search_with_score(self, query, k=4, filter=None, **kwargs):
        return self._query(self.embeddings.embed_query(query), k, filter, with_scores=True)
