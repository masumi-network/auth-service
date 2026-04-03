"""API key authentication dependency for agent endpoints."""

from fastapi import Header, HTTPException

from src import repository


async def require_agent(x_api_key: str = Header()) -> str:
    """Validate API key, return agent_id."""
    agent_id = await repository.verify_api_key(x_api_key)
    if not agent_id:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return agent_id
