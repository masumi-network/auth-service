"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting auth service (env={settings.sokosumi_environment})")
    yield


app = FastAPI(title="Masumi Auth Service", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}
