"""
Concrete EmbeddingProvider implementation using FastEmbed (ONNX runtime).

FastEmbed is maintained by Qdrant and runs the same HuggingFace models as
sentence-transformers but uses the ONNX runtime instead of PyTorch, giving
us a significantly smaller Docker image and lower memory footprint.

Model Reference
---------------
- ``BAAI/bge-small-en-v1.5``:  384-dim, ~130 MB, strong English quality.
  Best choice for V1: small, fast, great accuracy for English workspaces.
- ``sentence-transformers/all-MiniLM-L6-v2``: 384-dim, ~80 MB, slightly
  less accurate but even lighter. Good alternative if memory is tight.

To switch models, change the DEFAULT_MODEL constant and update the
VECTOR_SIZE constant to match.
"""
from typing import List

from fastembed import TextEmbedding

from embeddings.base import EmbeddingProvider
from utils.logger import logger

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
VECTOR_SIZE = 384


class FastEmbedProvider(EmbeddingProvider):
    """
    EmbeddingProvider that uses FastEmbed (ONNX) for local inference.

    The model is loaded lazily on first use and cached for the lifetime of
    the process. In the Celery worker this means it is loaded once per
    worker process and reused across tasks.

    Args:
        model_name: The HuggingFace model identifier to use.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self._model_name = model_name
        self._model: TextEmbedding | None = None

    def _load_model(self) -> TextEmbedding:
        """Lazy-load the model on first call."""
        if self._model is None:
            logger.info(f"FastEmbedProvider: loading model '{self._model_name}'")
            self._model = TextEmbedding(model_name=self._model_name)
            logger.info(f"FastEmbedProvider: model '{self._model_name}' ready")
        return self._model

    @property
    def vector_size(self) -> int:
        return VECTOR_SIZE

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a batch of texts using the ONNX model.

        FastEmbed's ``embed()`` returns a generator of numpy arrays.
        We convert each array to a plain Python list of floats so that
        the result is JSON-serialisable and Qdrant-compatible.
        """
        model = self._load_model()
        # fastembed.embed() is a generator — consume it fully with list()
        embeddings = list(model.embed(texts))
        return [emb.tolist() for emb in embeddings]
