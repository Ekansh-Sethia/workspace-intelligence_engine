from abc import ABC, abstractmethod


class Tokenizer(ABC):
    """
    Abstract base class for counting tokens.
    Abstracting this allows us to easily swap out tiktoken for HuggingFace tokenizers
    or provider-specific tokenizers in the future if needed.
    """

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        pass


class TiktokenTokenizer(Tokenizer):
    """
    Tokenizer implementation using OpenAI's tiktoken.
    Defaults to cl100k_base which is extremely fast and generally matches
    modern embedding model token sizes well enough for chunking.

    Memory optimisation: tiktoken is imported lazily inside __init__ so that
    the ~63 MB encoding table is only loaded when a tokenizer is first
    instantiated (i.e. when processing actually starts), not at server startup.
    """

    def __init__(self, encoding_name: str = "cl100k_base"):
        import tiktoken  # lazy import — avoids loading encoding maps at startup
        self.encoding = tiktoken.get_encoding(encoding_name)

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return len(self.encoding.encode(text))
