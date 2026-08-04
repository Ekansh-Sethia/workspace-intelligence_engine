"""
embeddings package

Exports the EmbeddingProvider ABC and the default FastEmbedProvider so that
the rest of the codebase can import from a single location.

Usage
-----
    from embeddings import EmbeddingProvider, FastEmbedProvider
    from embeddings.service import EmbeddingService
"""
from embeddings.base import EmbeddingProvider
from embeddings.fastembed_provider import FastEmbedProvider

__all__ = ["EmbeddingProvider", "FastEmbedProvider"]
