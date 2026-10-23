from openai import AsyncOpenAI

from app.config import settings


class OpenAIConfigurationError(RuntimeError):
    """Raised when required OpenAI configuration is missing."""


def get_openai_client() -> AsyncOpenAI:
    if not settings.openai_api_key:
        raise OpenAIConfigurationError("OPENAI_API_KEY is not configured.")

    return AsyncOpenAI(api_key=settings.openai_api_key)
