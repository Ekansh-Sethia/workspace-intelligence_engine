"""
LLM Gateway — Phase 9/10

Wraps LiteLLM to provide a unified, provider-agnostic interface for all LLM calls.

Design notes
------------
- LiteLLM uses OpenAI-compatible message format universally. Swapping providers
  means changing the model string — zero business logic changes.

- Primary model:  Gemini 2.5 Flash  (free tier, large context, vision-capable)
- Fallback model: Groq Llama 3.1 8B (free tier, extremely fast inference)

- Fallbacks are declared at the Router level. If the primary call raises any
  exception (RateLimitError, APIConnectionError, etc.), LiteLLM automatically
  retries on the next model in the fallbacks list without manual try/except.

- os.environ is the mechanism LiteLLM uses to pick up API keys. We write them
  once at startup from our Settings object so nothing else in the codebase
  needs to know which env var name each provider expects.

- llm_complete() is a lightweight non-streaming helper for utility calls such
  as conversational query rewriting, classification, and summarisation tasks.
"""
import os
import litellm
from litellm import Router
from utils.config import settings
from utils.logger import logger

# ── silence LiteLLM's overly verbose success logs ──────────────────────────
litellm.success_callback = []
litellm.set_verbose = False
litellm.suppress_debug_info = True


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
                "model": settings.LLM_FALLBACK_MODEL,
                "api_key": settings.GROQ_API_KEY or "not-set",
            },
        },
        {
            "model_name": "fast",
            "litellm_params": {
                "model": settings.LLM_FAST_MODEL,
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


async def llm_complete(
    system_prompt: str,
    user_message: str,
    max_tokens: int = 256,
) -> str:
    """
    Send a single non-streaming request to the LLM Gateway and return the
    full response as a plain string.

    Designed for lightweight utility calls (e.g., query rewriting, classification)
    where streaming is unnecessary and low latency is preferred.

    Args:
        system_prompt: The instruction for the LLM.
        user_message:  The user-facing input to process.
        max_tokens:    Cap the response length to avoid runaway completions.

    Returns:
        The LLM's response as a stripped plain string.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    logger.info("LLMGateway: llm_complete call (non-streaming, using fast model)")

    response = await _router.acompletion(
        model="fast",
        messages=messages,
        stream=False,
        max_tokens=max_tokens,
    )
    content = response.choices[0].message.content
    return content.strip() if content else ""


async def llm_stream(
    system_prompt: str,
    user_message: str,
    max_tokens: int = 1000,
):
    """
    Stream tokens from the LLM Gateway.
    Yields text tokens as they arrive.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    logger.info("LLMGateway: llm_stream call")

    response = await _router.acompletion(
        model="primary",
        messages=messages,
        stream=True,
        max_tokens=max_tokens,
    )
    
    async for chunk in response:
        token = chunk.choices[0].delta.content or ""
        if token:
            yield token
