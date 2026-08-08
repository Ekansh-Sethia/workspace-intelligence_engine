"""
LLM Gateway — Phase 9

Wraps LiteLLM to provide a unified, provider-agnostic interface for all LLM calls.

Design notes
------------
- LiteLLM uses OpenAI-compatible message format universally. Swapping providers
  means changing the model string (e.g., "gemini/gemini-2.5-flash" →
  "groq/llama-3.1-70b-versatile") — zero business logic changes.

- Primary model:  Gemini 2.5 Flash  (free tier, large context, vision-capable)
- Fallback model: Groq Llama 3.1 8B (free tier, extremely fast inference)

- Fallbacks are declared at the Router level. If the primary call raises any
  exception (RateLimitError, APIConnectionError, etc.), LiteLLM automatically
  retries on the next model in the fallbacks list without manual try/except.

- os.environ is the mechanism LiteLLM uses to pick up API keys. We write them
  once at startup from our Settings object so nothing else in the codebase
  needs to know which env var name each provider expects.
"""
import os
import litellm
from litellm import Router
from utils.config import settings
from utils.logger import logger

# ── silence LiteLLM's overly verbose success logs ──────────────────────────
litellm.success_callback = []
litellm.set_verbose = False


def _inject_api_keys() -> None:
    """Write configured API keys into the environment for LiteLLM to discover."""
    if settings.GROQ_API_KEY:
        os.environ["GROQ_API_KEY"] = settings.GROQ_API_KEY
    if settings.GEMINI_API_KEY:
        os.environ["GEMINI_API_KEY"] = settings.GEMINI_API_KEY


def _build_router() -> Router:
    """
    Build a LiteLLM Router with primary + fallback model configuration.

    The Router automatically handles:
    - Retry on transient errors (network timeouts, 5xx responses)
    - Fallback to the next model on rate-limit or permanent errors
    - Per-model timeout and retry settings
    """
    model_list = [
        {
            "model_name": "primary",
            "litellm_params": {
                "model": settings.LLM_PRIMARY_MODEL,
                "api_key": settings.GEMINI_API_KEY or "not-set",
            },
        },
        {
            "model_name": "fallback",
            "litellm_params": {
                "model": "groq/llama-3.1-8b-instant",
                "api_key": settings.GROQ_API_KEY or "not-set",
            },
        }
    ]

    router = Router(
        model_list=model_list,
        fallbacks=[{"primary": ["fallback"]}],
        num_retries=2,
        retry_after=1,
        timeout=60,
    )
    return router


# Module-level singleton — created once, reused across all requests
_inject_api_keys()
_router: Router = _build_router()


async def llm_chat_stream(
    system_prompt: str,
    messages: list[dict],
) -> litellm.CustomStreamWrapper:
    """
    Send a chat request to the LLM Gateway and return an async streaming iterator.

    The caller is responsible for iterating over the returned stream and
    yielding each token chunk. On provider failure, LiteLLM's Router
    transparently retries and falls back to the secondary provider.

    Args:
        system_prompt: The grounding system instruction for the LLM.
        messages:      OpenAI-format message list: [{"role": "user"|"assistant", "content": str}]

    Returns:
        An async streaming response object. Iterate over it to get chunks.
    """
    full_messages = [{"role": "system", "content": system_prompt}] + messages

    logger.info(
        f"LLMGateway: sending {len(messages)} message(s) to primary model "
        f"'{settings.LLM_PRIMARY_MODEL}'"
    )

    stream = await _router.acompletion(
        model="primary",
        messages=full_messages,
        stream=True,
    )
    return stream
