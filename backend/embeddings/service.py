"""
EmbeddingService: orchestrates chunk retrieval, embedding, and Qdrant upsert.

This service sits between the Celery pipeline and the vector store. It is
completely provider-agnostic: it delegates vector generation to whatever
EmbeddingProvider is injected at construction time.

Design decisions
----------------
- **Batch processing**: Chunks are processed in configurable batches to
  prevent memory spikes when workspaces have thousands of files.
- **Idempotent upserts**: Qdrant upsert semantics mean re-indexing a workspace
  simply overwrites the previous vectors for those point IDs.
- **Point IDs**: We use the Postgres ``Chunk.id`` (integer) directly as the
  Qdrant point ID. This creates a stable, 1:1 mapping between the relational
  and vector stores, making lookups and deletions trivial.
"""
from typing import List

from qdrant_client.models import PointStruct
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.qdrant import get_qdrant_client, COLLECTION_NAME
from embeddings.base import EmbeddingProvider
from workspaces.models import Chunk, File
from utils.logger import logger

DEFAULT_BATCH_SIZE = 32


class EmbeddingService:
    """
    Generates embeddings for all chunks in a workspace and upserts them
    into the Qdrant vector store.

    Args:
        provider:   An EmbeddingProvider instance (e.g. FastEmbedProvider).
        batch_size: Number of chunks to embed in a single forward pass.
    """

    def __init__(self, provider: EmbeddingProvider, batch_size: int = DEFAULT_BATCH_SIZE):
        self._provider = provider
        self._batch_size = batch_size

    async def embed_and_store_workspace(self, workspace_id: int, db: AsyncSession) -> int:
        """
        Fetch chunks in bounded batches for a workspace, generate embeddings,
        and upsert them into Qdrant without holding all chunks in RAM.

        Args:
            workspace_id: The workspace whose chunks should be vectorised.
            db:           An open AsyncSession used to fetch chunk records.

        Returns:
            The total number of vectors upserted.
        """
        import gc

        # 1. Fetch only chunk IDs to avoid loading thousands of ORM text objects at once
        result = await db.execute(
            select(Chunk.id)
            .join(File, Chunk.file_id == File.id)
            .where(File.workspace_id == workspace_id)
            .order_by(Chunk.id)
        )
        chunk_ids: List[int] = result.scalars().all()

        if not chunk_ids:
            logger.warning(f"EmbeddingService: no chunks found for workspace {workspace_id}")
            return 0

        logger.info(
            f"EmbeddingService: embedding {len(chunk_ids)} chunks for workspace {workspace_id} "
            f"using '{self._provider.model_name}' (batch size {self._batch_size})"
        )

        client = get_qdrant_client()
        total_upserted = 0

        # 2. Process in bounded batches, fetching full records only for the current batch
        for batch_start in range(0, len(chunk_ids), self._batch_size):
            batch_ids = chunk_ids[batch_start: batch_start + self._batch_size]
            batch_res = await db.execute(
                select(Chunk).where(Chunk.id.in_(batch_ids)).order_by(Chunk.id)
            )
            batch = batch_res.scalars().all()
            texts = [chunk.text for chunk in batch]

            # 3. Generate vectors via the injected provider
            vectors = self._provider.embed_batch(texts)

            # 4. Build Qdrant PointStructs
            points = [
                PointStruct(
                    id=chunk.id,
                    vector=vector,
                    payload={
                        "workspace_id": workspace_id,
                        "file_id": chunk.file_id,
                        "chunk_id": chunk.id,
                        "chunk_index": chunk.chunk_index,
                        "page_number": chunk.page_number,
                        "text": chunk.text,
                        "chunk_type": getattr(chunk, "chunk_type", "text"),
                    },
                )
                for chunk, vector in zip(batch, vectors)
            ]

            # 5. Upsert into Qdrant (idempotent)
            client.upsert(collection_name=COLLECTION_NAME, points=points)
            total_upserted += len(points)

            # Explicitly free batch memory
            del points, vectors, texts, batch
            gc.collect()

            logger.info(
                f"EmbeddingService: upserted batch {batch_start // self._batch_size + 1} "
                f"({len(batch_ids)} vectors) for workspace {workspace_id}"
            )

        logger.info(
            f"EmbeddingService: workspace {workspace_id} fully indexed "
            f"({total_upserted} vectors total)"
        )
        return total_upserted

    def delete_workspace_vectors(self, workspace_id: int) -> None:
        """
        Remove all Qdrant vectors whose payload ``workspace_id`` matches.

        Called when a workspace is deleted so that the vector store does
        not accumulate orphaned points.
        """
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        client = get_qdrant_client()
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="workspace_id",
                        match=MatchValue(value=workspace_id),
                    )
                ]
            ),
        )
        logger.info(f"EmbeddingService: deleted vectors for workspace {workspace_id}")
