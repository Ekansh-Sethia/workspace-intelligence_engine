from langchain_text_splitters import RecursiveCharacterTextSplitter
from parsers.base import Document
from .tokenizer import Tokenizer
import logging

logger = logging.getLogger(__name__)

class DocumentChunker:
    def __init__(
        self,
        tokenizer: Tokenizer,
        chunk_size: int = 500,
        chunk_overlap: int = 100
    ):
        self.tokenizer = tokenizer
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=self.tokenizer.count_tokens,
            separators=["\n\n", "\n", " ", ""]
        )

    def chunk_document(self, document: Document) -> list[dict]:
        """
        Splits a Document into semantic chunks.
        Returns a list of dictionaries that can be easily persisted to the Chunk DB model.
        """
        if not document.text.strip():
            logger.warning(f"Document {document.filename} has no text to chunk.")
            return []

        # For V1, we split the entire document text.
        # Future enhancement: Split page-by-page if page boundaries are preserved, 
        # to correctly populate `page_number` for each chunk.
        
        raw_chunks = self.splitter.split_text(document.text)
        
        chunks = []
        for index, text in enumerate(raw_chunks):
            chunk_data = {
                "chunk_index": index,
                "text": text,
                "page_number": None,
                "token_count": self.tokenizer.count_tokens(text)
            }
            chunks.append(chunk_data)
            
        logger.info(f"Chunked '{document.filename}' into {len(chunks)} chunks.")
        return chunks
