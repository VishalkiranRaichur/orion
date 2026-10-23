from typing import TypeVar

from pydantic import BaseModel

from app.config import settings
from app.services.openai_client import get_openai_client

StructuredResponse = TypeVar("StructuredResponse", bound=BaseModel)


class StructuredResponseError(RuntimeError):
    """Raised when a model returns no parsed structured response."""


async def parse_structured_response(
    *,
    response_type: type[StructuredResponse],
    instructions: str,
    input_text: str,
    model: str | None = None,
) -> StructuredResponse:
    client = get_openai_client()
    response = await client.responses.parse(
        model=model or settings.structured_response_model,
        instructions=instructions,
        input=input_text,
        text_format=response_type,
        temperature=0,
    )

    if response.output_parsed is None:
        raise StructuredResponseError("The model did not return a parsed response.")

    return response.output_parsed
