"""
Abstract base class for embedding providers.

This abstraction allows us to swap the underlying embedding backend
(FastEmbed, sentence-transformers, OpenAI API, etc.) without touching
the indexing pipeline.

Extension Guide
---------------
1. Create a new module (e.g., ``embeddings/openai_provider.py``).
2. Subclass ``EmbeddingProvider`` and implement ``embed_batch``.
3. Pass an instance of your new provider to ``EmbeddingService``.
"""
from abc import ABC, abstractmethod
from typing import List


class EmbeddingProvider(ABC):
    """
    Protocol for embedding providers.

    All providers must be able to accept a list of strings and return
    a corresponding list of float vectors. Batching is handled at this
    level so that the service layer stays provider-agnostic.
    """

    @property
    @abstractmethod
    def vector_size(self) -> int:
        """The dimensionality of the vectors produced by this provider."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """A human-readable identifier for the model being used."""
        ...

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts.

        Args:
            texts: A list of strings to embed.

        Returns:
            A list of float vectors, one per input string, in the same order.
        """
        ...
