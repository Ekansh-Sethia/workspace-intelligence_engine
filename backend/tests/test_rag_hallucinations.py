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
    assert "provide ALL the relevant information you DO find" in prompt
    
    # Check context mixing prevention rule
    assert "DO NOT mix options, answers, or text from different questions." in prompt
    
    # Check that context is properly injected
    assert "[Source: fruits.txt | type: text | page=1]" in prompt
    assert "Apples are red." in prompt

def test_rag_system_prompt_max_context_limit():
    """
    Test that context chunks are capped at MAX_CONTEXT_CHUNKS (15) to prevent
    context window overflow which can lead to hallucination or token limits.
    """
    from chat.rag_service import MAX_CONTEXT_CHUNKS

    chunks = []
    for i in range(MAX_CONTEXT_CHUNKS + 5):
        chunks.append(
            SearchResult(
                score=0.9, text=f"Fact {i}", file_id=1, chunk_id=i,
                chunk_index=i, page_number=1, chunk_type="text"
            )
        )

    prompt = _build_system_prompt(chunks, {1: "facts.txt"})

    # The prompt should contain all facts up to the cap
    for i in range(MAX_CONTEXT_CHUNKS):
        assert f"Fact {i}" in prompt

    # Facts beyond the cap should NOT appear
    for i in range(MAX_CONTEXT_CHUNKS, MAX_CONTEXT_CHUNKS + 5):
        assert f"Fact {i}" not in prompt


def test_rag_system_prompt_with_available_files():
    """Test that available workspace documents are injected into the system prompt."""
    prompt = _build_system_prompt(
        [],
        {},
        available_files=["notes.txt", "interview_prep.pdf"]
    )
    assert "DOCUMENTS IN THIS WORKSPACE:" in prompt
    assert "- notes.txt" in prompt
    assert "- interview_prep.pdf" in prompt


def test_match_files_by_name():
    """Test that query keywords match files by filename correctly."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from chat.rag_service import _match_files_by_name

    async def _test():
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [
            (1, "Ekansh_Sethia_Cover_Letter.pdf"),
            (2, "Goldman probable Interview questions on projects.docx"),
            (3, "Till 4th Sem.pdf"),
        ]
        mock_db.execute.return_value = mock_result

        matched = await _match_files_by_name(
            workspace_id=1,
            query="what are interview questions",
            db=mock_db,
        )
        assert matched == [2]

    asyncio.run(_test())


def test_rewrite_query_empty_fallback():
    """Test that if the LLM query rewriter returns empty string, it falls back to original query."""
    import asyncio
    from unittest.mock import patch
    from chat.rag_service import _rewrite_query

    async def _test():
        with patch("chat.rag_service.llm_complete", return_value="   "):
            res = await _rewrite_query("what are interview questions", [{"role": "user", "content": "hello"}])
            assert res == "what are interview questions"

    asyncio.run(_test())


