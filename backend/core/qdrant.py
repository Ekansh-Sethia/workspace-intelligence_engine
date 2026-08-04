"""
Qdrant client initialisation and collection management.

Centralising the client here ensures a single connection is reused
across the application rather than opening a new HTTP connection per request.

Collection schema
-----------------
- Name:       ``workspace_chunks``
- Vector size: 384  (matches BAAI/bge-small-en-v1.5 and MiniLM-L6-v2)
- Distance:    Cosine  (standard for semantic similarity)

Indexed payload fields
-----------------------
The following payload fields are indexed so that Qdrant can execute
filtered searches efficiently (important for per-workspace retrieval):
- ``workspace_id`` (integer)
- ``file_id``      (integer)
"""
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PayloadSchemaType,
)

from utils.config import settings
from utils.logger import logger

COLLECTION_NAME = "workspace_chunks"
VECTOR_SIZE = 384  # Matches BAAI/bge-small-en-v1.5

_client: QdrantClient | None = None


def get_qdrant_client() -> QdrantClient:
    """Return the singleton QdrantClient, creating it on first call."""
    global _client
    if _client is None:
        _client = QdrantClient(url=settings.QDRANT_URL)
    return _client


def init_qdrant() -> None:
    """
    Ensure the ``workspace_chunks`` collection and its payload indexes exist.

    Safe to call multiple times — uses ``recreate=False`` semantics so that
    existing data is never dropped on restart.
    """
    client = get_qdrant_client()

    # Check if collection already exists
    existing = {col.name for col in client.get_collections().collections}
    if COLLECTION_NAME not in existing:
        logger.info(f"Qdrant: creating collection '{COLLECTION_NAME}'")
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        logger.info(f"Qdrant: collection '{COLLECTION_NAME}' created")
    else:
        logger.info(f"Qdrant: collection '{COLLECTION_NAME}' already exists — skipping creation")

    # Create payload indexes for efficient filtered search
    _ensure_payload_index(client, "workspace_id", PayloadSchemaType.INTEGER)
    _ensure_payload_index(client, "file_id", PayloadSchemaType.INTEGER)

    logger.info("Qdrant: initialisation complete")


def _ensure_payload_index(client: QdrantClient, field: str, schema_type: PayloadSchemaType) -> None:
    """Create a payload index if it does not already exist (idempotent)."""
    try:
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name=field,
            field_schema=schema_type,
        )
        logger.info(f"Qdrant: payload index on '{field}' ensured")
    except Exception as exc:
        # Qdrant raises if the index already exists; we treat that as a no-op
        logger.debug(f"Qdrant: payload index on '{field}' already exists ({exc})")
