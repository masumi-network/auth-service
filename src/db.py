"""asyncpg connection pool management."""

import logging

import asyncpg

from src.config import settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def init_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            settings.database_url,
            min_size=2,
            max_size=10,
        )
        logger.info("Database pool created")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Database pool closed")


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        return await init_pool()
    return _pool


async def run_migrations() -> None:
    """Run SQL migration files in order."""
    import os
    import glob

    pool = await get_pool()
    migrations_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations")

    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

        applied = {
            row["filename"]
            for row in await conn.fetch("SELECT filename FROM _migrations")
        }

        migration_files = sorted(glob.glob(os.path.join(migrations_dir, "*.sql")))
        for filepath in migration_files:
            filename = os.path.basename(filepath)
            if filename in applied:
                continue

            logger.info(f"Running migration: {filename}")
            with open(filepath) as f:
                sql = f.read()
            await conn.execute(sql)
            await conn.execute(
                "INSERT INTO _migrations (filename) VALUES ($1)", filename
            )
            logger.info(f"Migration applied: {filename}")
