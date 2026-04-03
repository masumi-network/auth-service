"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config import settings
from src.db import init_pool, close_pool, run_migrations

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


@app.get("/health")
async def health():
    return {"status": "ok"}
