"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.routes import router as api_router
from src.config import settings
from src.db import init_pool, close_pool, run_migrations
from src.oauth.routes import router as oauth_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting auth service (env={settings.sokosumi_environment})")
    await init_pool()
    await run_migrations()
    yield
    await close_pool()


app = FastAPI(title="Masumi Auth Service", lifespan=lifespan)

app.include_router(api_router)
app.include_router(oauth_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
