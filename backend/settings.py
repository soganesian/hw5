"""Shared model and Portkey configuration for every agent."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
MODEL_NAME = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"


def create_shared_model() -> OpenAIChatModel:
    """Create the single required model configuration used by the whole team."""
    load_dotenv(REPOSITORY_ROOT / ".env")
    portkey_api_key = os.environ.get("PORTKEY_API_KEY")
    if not portkey_api_key:
        raise RuntimeError(
            f"PORTKEY_API_KEY is missing; set it in {REPOSITORY_ROOT / '.env'}"
        )

    client = AsyncOpenAI(
        api_key=portkey_api_key,
        base_url=PORTKEY_BASE_URL,
        default_headers={
            "x-portkey-api-key": portkey_api_key,
            "x-portkey-provider": "openai",
        },
    )
    provider = OpenAIProvider(openai_client=client)
    # Portkey's Azure-backed gpt-6-luna route rejects non-none reasoning effort
    # on chat-completion requests that include function tools. Agent workflows
    # rely on those tools, so request the supported setting explicitly.
    return OpenAIChatModel(
        MODEL_NAME,
        provider=provider,
        settings={"openai_reasoning_effort": "none"},
    )
