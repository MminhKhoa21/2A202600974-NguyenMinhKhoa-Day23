"""LLM factory helper.

Provides a simple interface to create LLM clients for use in nodes.
Students should use this helper so the lab works with any supported provider.

Usage in nodes:
    from .llm import get_llm
    llm = get_llm()
    response = llm.invoke("Hello")
"""

from __future__ import annotations

import os
from typing import Any


def get_llm(model: str | None = None, temperature: float = 0.0) -> Any:  # noqa: ANN401
    """Create an LLM client from environment configuration.

    Checks for API keys in this order:
    0. OLLAMA_MODEL / OLLAMA_BASE_URL / USE_OLLAMA=true → ChatOllama
    1. GEMINI_API_KEY → ChatGoogleGenerativeAI
    2. OPENAI_API_KEY → ChatOpenAI
    3. ANTHROPIC_API_KEY → ChatAnthropic

    Override model with the `model` parameter or LLM_MODEL env var.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        pass
    else:
        load_dotenv()

    use_ollama = os.getenv("USE_OLLAMA", "").lower() == "true"
    if use_ollama or os.getenv("OLLAMA_MODEL") or os.getenv("OLLAMA_BASE_URL"):
        try:
            from langchain_ollama import ChatOllama
        except ImportError as exc:
            raise RuntimeError("Install: pip install langchain-ollama") from exc
        selected_model = (
            model
            or os.getenv("OLLAMA_MODEL")
            or os.getenv("LLM_MODEL")
            or "llama3.1:8b"
        )
        return ChatOllama(
            model=selected_model,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            temperature=temperature,
        )

    if os.getenv("GEMINI_API_KEY"):
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise RuntimeError("Install: pip install langchain-google-genai") from exc
        selected_model = model or os.getenv("LLM_MODEL") or "gemini-3.1-flash-lite"
        return ChatGoogleGenerativeAI(
            model=selected_model,
            google_api_key=os.getenv("GEMINI_API_KEY"),
            temperature=temperature,
            thinking_level="minimal",
            retries=2,
            request_timeout=45,
        )

    if os.getenv("OPENAI_API_KEY"):
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError("Install: pip install langchain-openai") from exc
        selected_model = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"
        return ChatOpenAI(
            model=selected_model,
            temperature=temperature,
        )

    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise RuntimeError("Install: pip install langchain-anthropic") from exc
        return ChatAnthropic(
            model=model or os.getenv("LLM_MODEL", "claude-sonnet-4-20250514"),
            temperature=temperature,
        )

    raise RuntimeError(
        "No LLM provider configured. Set USE_OLLAMA=true with OLLAMA_MODEL, or set "
        "GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY in .env.\n"
        "See .env.example for configuration."
    )
