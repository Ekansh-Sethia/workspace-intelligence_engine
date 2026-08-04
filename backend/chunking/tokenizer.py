from abc import ABC, abstractmethod
import tiktoken

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
    """
    
    def __init__(self, encoding_name: str = "cl100k_base"):
        self.encoding = tiktoken.get_encoding(encoding_name)
        
    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return len(self.encoding.encode(text))
