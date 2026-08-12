"""
IntentRouter - Phase 9

Classifies every user query into one of five intents before any LLM call is made.
This is the architectural gate that prevents expensive LLM invocations for queries
that can be answered deterministically.

Intent Types
------------
METADATA_SEARCH  -- Query about file names, counts, types. Zero LLM calls.
SUMMARIZATION    -- Request to summarise workspace or file. Served from DB.
SEMANTIC_SEARCH  -- General knowledge question. Routes to full RAG pipeline.
ACTION           -- Request to perform an action (merge, export, quiz, notes).
UNKNOWN          -- Intent could not be determined.

Classification Strategy (Two-Layer)
-------------------------------------
Layer 1 -- Fast regex / keyword heuristics (no LLM call, < 1ms).
Layer 2 -- LLM classification (only when Layer 1 is inconclusive, ~200ms).
"""
import json
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

from utils.logger import logger


class Intent(str, Enum):
    METADATA_SEARCH = "metadata_search"
    SUMMARIZATION = "summarization"
    SEMANTIC_SEARCH = "semantic_search"
    ACTION = "action"
    UNKNOWN = "unknown"


class IntentResult(BaseModel):
    intent: Intent = Field(..., description="The classified intent of the user query.")
    file_type_filter: Optional[str] = Field(None, description="MIME type filter if the user asked for specific files. Examples: 'application/pdf', 'image/%', 'text/plain'.")
    action_type: Optional[str] = Field(None, description="The specific action requested if intent is ACTION. Examples: 'quiz', 'notes', 'export'.")


_LLM_CLASSIFIER_SYSTEM = (
    "You are an intent classifier and entity extractor for a document workspace Q&A system. "
    "Given a user query, analyze it and return a JSON object with the following schema:\n"
    "{\n"
    "  \"intent\": \"metadata_search\" | \"summarization\" | \"action\" | \"semantic_search\",\n"
    "  \"file_type_filter\": \"application/pdf\" | \"image/%\" | \"text/plain\" | null,\n"
    "  \"action_type\": \"quiz\" | \"notes\" | \"export\" | null\n"
    "}\n\n"
    "Intents:\n"
    "- metadata_search: Query explicitly asking to list, count, or find files in the workspace.\n"
    "- summarization: Request to summarise or describe the workspace or a file. This includes 'tell me about this workspace', 'what is this workspace about', 'describe this', 'give me an overview'.\n"
    "- action: Request to perform a workspace action. This includes generating any kind of quiz, test, assessment, flashcards, or Q&A cards (action_type='quiz'), and generating study notes, summaries, revision materials, or cheat sheets (action_type='notes').\n"
    "- semantic_search: General knowledge question, conversational replies, verifying/grading quiz answers, or anything else (default fallback).\n\n"
    "CRITICAL: If the user is answering a quiz, submitting answers, or asking to verify/grade their responses, you MUST classify it as semantic_search.\n\n"
    "Provide ONLY the raw JSON object. No markdown formatting, no explanation."
)


async def classify_intent(query: str) -> IntentResult:
    """
    Classify the query intent and extract entities using a lightning-fast Groq JSON call.
    Falls back to SEMANTIC_SEARCH on failure.
    """
    try:
        from llm.gateway import llm_complete
        # llm_complete now uses the 'fast' model (Groq) by default
        raw = await llm_complete(
            system_prompt=_LLM_CLASSIFIER_SYSTEM,
            user_message=query,
            max_tokens=150,
        )
        
        # Strip potential markdown blocks if the LLM hallucinated them
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.endswith("```"):
            raw = raw[:-3]
            
        data = json.loads(raw.strip())
        result = IntentResult(**data)
        logger.info(f"IntentRouter: classified query as {result.intent.value} (file_type: {result.file_type_filter}, action: {result.action_type})")
        return result
    except Exception as e:
        logger.warning(f"IntentRouter: JSON extraction failed, defaulting to semantic_search ({e})")
        return IntentResult(intent=Intent.SEMANTIC_SEARCH)
