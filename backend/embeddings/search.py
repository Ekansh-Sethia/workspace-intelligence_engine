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
"""
from typing import List

from qdrant_client.models import Filter, FieldCondition, MatchValue

from core.qdrant import get_qdrant_client, COLLECTION_NAME
from embeddings.base import EmbeddingProvider
from workspaces.search_schemas import SearchResult
from utils.logger import logger


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

        # 3. Run the similarity search in Qdrant
        #    client.search() was removed in qdrant-client >= 1.10.
        #    The new unified API is client.query_points().
        client = get_qdrant_client()
        result = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            query_filter=workspace_filter,
            limit=limit,
            with_payload=True,
        )

        # 4. Unpack Qdrant ScoredPoints into our Pydantic response schema
        #    query_points() returns a QueryResponse; the hits are in .points
        #
        #    Minimum confidence threshold: 0.30 (30%)
        #    Results below this score are discarded. We previously set this to 51%
        #    but found it aggressively filtered out valid chunks for short queries.
        #    The LLM in the Chat Layer is a better judge of relevance than a hard
        #    cosine similarity cutoff, so we supply the chunks and let the LLM filter.
        MIN_SCORE_THRESHOLD = 0.30

        results = [
            SearchResult(
                score=round(hit.score, 4),
                text=hit.payload.get("text", ""),
                file_id=hit.payload.get("file_id", 0),
                chunk_id=hit.payload.get("chunk_id", 0),
                chunk_index=hit.payload.get("chunk_index", 0),
                page_number=hit.payload.get("page_number"),
            )
            for hit in result.points
            if hit.score >= MIN_SCORE_THRESHOLD
        ]

        logger.info(
            f"SearchService: returned {len(results)} results for workspace {workspace_id}"
        )
        return results
