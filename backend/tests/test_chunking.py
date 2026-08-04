import pytest
from chunking.tokenizer import TiktokenTokenizer
from chunking.splitter import DocumentChunker
from parsers.base import Document

@pytest.fixture
def tokenizer():
    return TiktokenTokenizer()

@pytest.fixture
def chunker(tokenizer):
    # Using small limits for easier testing
    return DocumentChunker(tokenizer=tokenizer, chunk_size=50, chunk_overlap=10)

def test_tiktoken_tokenizer(tokenizer):
    assert tokenizer.count_tokens("Hello, world!") == 4
    assert tokenizer.count_tokens("") == 0
    assert tokenizer.count_tokens("   ") == 1

def test_document_chunking(chunker, tokenizer):
    # Create a dummy document with roughly 100 tokens
    # "word " is 1 token in cl100k_base. Let's make 120 words.
    text = " ".join([f"word{i}" for i in range(120)])
    doc = Document(filename="test.txt", source_path="test.txt", text=text)
    
    chunks = chunker.chunk_document(doc)
    
    assert len(chunks) > 1
    
    for i, chunk in enumerate(chunks):
        assert chunk["chunk_index"] == i
        # The chunker is configured for max 50 tokens
        # Langchain might slightly exceed this if a single word is huge, but here it shouldn't
        assert chunk["token_count"] <= 50 + 5 # Small buffer for separator tokens
        
        # Verify text content
        assert chunk["text"] in text

def test_empty_document_chunking(chunker):
    doc = Document(filename="empty.txt", source_path="empty.txt", text="")
    chunks = chunker.chunk_document(doc)
    assert chunks == []

def test_whitespace_document_chunking(chunker):
    doc = Document(filename="space.txt", source_path="space.txt", text="   \n  \n")
    chunks = chunker.chunk_document(doc)
    assert chunks == []
