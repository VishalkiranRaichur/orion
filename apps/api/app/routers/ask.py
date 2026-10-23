import logging

from fastapi import APIRouter, Depends, HTTPException
from openai import OpenAIError
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Workspace
from app.services.embedding_service import OpenAIConfigurationError
from app.services.rag_service import answer_question
from app.workspaces import get_active_workspace

router = APIRouter()
logger = logging.getLogger(__name__)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=5, ge=1, le=10)


@router.post("/ask")
async def ask_question(
    request: AskRequest,
    workspace: Workspace = Depends(get_active_workspace),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await answer_question(
            db=db,
            workspace_id=workspace.id,
            question=request.question,
            limit=request.limit,
        )

        return result

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error
    except OpenAIConfigurationError as error:
        logger.error("OpenAI is not configured: %s", error)
        raise HTTPException(status_code=503, detail=str(error)) from error
    except OpenAIError as error:
        logger.exception("OpenAI request failed while answering a question")
        raise HTTPException(
            status_code=502,
            detail="The AI service is temporarily unavailable. Please try again.",
        ) from error
    except SQLAlchemyError as error:
        logger.exception("Database search failed while answering a question")
        raise HTTPException(
            status_code=503,
            detail="The document database is unavailable. Check PostgreSQL and pgvector.",
        ) from error
    except Exception as error:
        logger.exception("Unexpected question-answering failure")
        raise HTTPException(
            status_code=500,
            detail="Unable to answer the question.",
        ) from error
