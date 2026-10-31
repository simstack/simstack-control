from contextlib import asynccontextmanager
from typing import AsyncIterator


@asynccontextmanager
async def simstack_session() -> AsyncIterator[object]:
    """Open the SimStack context from the project ``simstack.toml``."""
    from simstack.core.context import context

    await context.initialize()
    try:
        yield context
    finally:
        database = context.db
        if database is not None:
            await database.close()
