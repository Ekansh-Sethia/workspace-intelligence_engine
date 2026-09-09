"""
SearchService: executes a filtered semantic similarity search against Qdrant.

Design notes
------------
- Multi-tenancy is enforced via a Qdrant payload filter on ``workspace_id``.
  This guarantees that a user searching Workspace A can never accidentally
  receive chunks from Workspace B, even if their query vectors are similar.

- The query text is embedded using the same EmbeddingProvider that was used
  during indexing. Consistency here is critical — mixing models would produce
  vectors in different latent spaces and return garbage results.

- Scores returned by Qdrant for Cosine distance are in the range [-1, 1].
  In practice, semantically relevant results score above ~0.5.

Score threshold note
---------------------
MIN_SCORE_THRESHOLD is set at 0.15 (was 0.30).
Rationale: individual Q&A chunks ("Q: What is a deadlock? A: ...") have low
cosine similarity to queries like "interview questions for goldman sachs"
because they don't repeat those keywords — they score ~0.15–0.25.
The 0.30 threshold was silently discarding all of them.
The LLM is a far better relevance judge than a hard cosine cutoff.
We retrieve more candidates and let the model decide what to use.
"""
from typing import List

from qdrant_client.models import Filter, FieldCondition, MatchValue

from core.qdrant import get_qdrant_client, COLLECTION_NAME
from embeddings.base import EmbeddingProvider
from workspaces.search_schemas import SearchResult
from utils.logger import logger


MIN_SCORE_THRESHOLD = 0.30  # Intentionally conservative — the LLM is a better relevance judge,
                             # but we use 0.30 to avoid pulling noise from tangentially-related
                             # files. Full-file expansion (Layer 1.5) handles deep retrieval
                             # once the correct file is identified by its title/header chunk.


class SearchService:
    """
    Performs workspace-scoped semantic search by:
    1. Embedding the query via the injected EmbeddingProvider.
    2. Running a filtered nearest-neighbour search in Qdrant.
    3. Unpacking the vector payload into SearchResult objects.

    Args:
        provider: The same EmbeddingProvider used during indexing.
    """

    def __init__(self, provider: EmbeddingProvider):
        self._provider = provider

    def search(self, workspace_id: int, query: str, limit: int = 5) -> List[SearchResult]:
        """
        Search for chunks semantically similar to ``query`` within a workspace.

        Args:
            workspace_id: Restricts search to this workspace's chunks only.
            query:        Natural language query string.
            limit:        Maximum number of results to return (default 5).

        Returns:
            A list of SearchResult objects ordered by descending similarity score.
        """
        logger.info(
            f"SearchService: searching workspace {workspace_id} "
            f"for '{query[:60]}...' (limit={limit})"
        )

        # 1. Embed the query (single-text batch)
        query_vector = self._provider.embed_batch([query])[0]

        # 2. Build a workspace-scoped filter
        workspace_filter = Filter(
            must=[
                FieldCondition(
                    key="workspace_id",
                    match=MatchValue(value=workspace_id),
                )
            ]
        )

        # 3. Run the similarity search in Qdrant.
        #    We request limit*3 candidates so that after threshold filtering we
        #    still have enough results. Qdrant HNSW retrieval cost is O(log N)
        #    regardless of candidate count — this is essentially free.
        client = get_qdrant_client()
        result = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            query_filter=workspace_filter,
            limit=limit * 3,
            with_payload=True,
        )

        # 4. Unpack Qdrant ScoredPoints into our Pydantic response schema.
        #    Threshold at 0.15 — low enough to catch topically-relevant chunks
        #    that don't repeat the query keywords (e.g. individual Q&A pairs).
        results = [
            SearchResult(
                score=round(hit.score, 4),
                text=hit.payload.get("text", ""),
                file_id=hit.payload.get("file_id", 0),
                chunk_id=hit.payload.get("chunk_id", 0),
                chunk_index=hit.payload.get("chunk_index", 0),
                page_number=hit.payload.get("page_number"),
                chunk_type=hit.payload.get("chunk_type", "text"),
            )
            for hit in result.points
            if hit.score >= MIN_SCORE_THRESHOLD
        ][:limit]  # Re-cap to the requested limit after threshold filtering

        logger.info(
            f"SearchService: returned {len(results)} results for workspace {workspace_id} "
            f"(threshold={MIN_SCORE_THRESHOLD}, candidates_fetched={limit * 3})"
        )
        return results
