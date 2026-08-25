import pytest
from chat.rag_service import _build_system_prompt
from workspaces.search_schemas import SearchResult

def test_rag_system_prompt_empty_context():
    """
    Test that when no relevant data is found, the system prompt strictly instructs 
    the model to inform the user, preventing hallucinated answers.
    """
    prompt = _build_system_prompt([], {})
    
    assert "No relevant context chunks were found for this query." in prompt
    assert "STRICT GROUNDING: You MUST NOT use your internal knowledge" in prompt
    assert "QUIZ GRADING EXCEPTION" in prompt

def test_rag_system_prompt_with_context():
    """
    Test that when context is provided, the system prompt includes strict grounding rules
    to prevent the model from using internal knowledge or mixing unrelated topics.
    """
    chunks = [
        SearchResult(
            score=0.9, text="Apples are red.", file_id=1, chunk_id=1, 
            chunk_index=0, page_number=1, chunk_type="text"
        )
    ]
    file_names = {1: "fruits.txt"}
    
    prompt = _build_system_prompt(chunks, file_names)
    
    # Check strict grounding rule
    assert "STRICT GROUNDING: You MUST NOT use your internal knowledge" in prompt
    assert "The provided context does not contain the answer to this question" in prompt
    
    # Check context mixing prevention rule
    assert "DO NOT mix options, answers, or text from different questions." in prompt
    
    # Check that context is properly injected
    assert "[Source: fruits.txt | type: text | page=1]" in prompt
    assert "Apples are red." in prompt

def test_rag_system_prompt_max_context_limit():
    """
    Test that context chunks are capped at MAX_CONTEXT_CHUNKS (8) to prevent 
    context window overflow which can lead to hallucination or token limits.
    """
    chunks = []
    for i in range(15):
        chunks.append(
            SearchResult(
                score=0.9, text=f"Fact {i}", file_id=1, chunk_id=i, 
                chunk_index=i, page_number=1, chunk_type="text"
            )
        )
    
    prompt = _build_system_prompt(chunks, {1: "facts.txt"})
    
    # The prompt should contain Fact 0 to 7, but not Fact 8+
    for i in range(8):
        assert f"Fact {i}" in prompt
    
    for i in range(8, 15):
        assert f"Fact {i}" not in prompt
