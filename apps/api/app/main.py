from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import ask, data_sources, documents, health, investigations, workspaces

app = FastAPI(
    title=settings.app_name,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    workspaces.router,
    prefix=f"{settings.api_prefix}/workspaces",
    tags=["workspaces"],
)

app.include_router(
    health.router,
    prefix=settings.api_prefix,
    tags=["health"],
)

app.include_router(
    documents.router,
    prefix=f"{settings.api_prefix}/documents",
    tags=["documents"],
)

app.include_router(
    data_sources.router,
    prefix=f"{settings.api_prefix}/data-sources",
    tags=["data-sources"],
)

app.include_router(
    ask.router,
    prefix=settings.api_prefix,
    tags=["ask"],
)

app.include_router(
    investigations.router,
    prefix=f"{settings.api_prefix}/investigations",
    tags=["investigations"],
)


@app.get("/")
async def root() -> dict:
    return {"message": "Admin AI API", "docs": "/docs"}
