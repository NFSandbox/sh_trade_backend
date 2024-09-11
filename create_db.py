import asyncio

from provider import database
from schemes.sql import SQLBaseModel


async def init_models():
    async with database._engine.begin() as session:
        await session.run_sync(SQLBaseModel.metadata.drop_all)
        await session.run_sync(SQLBaseModel.metadata.create_all)


if __name__ == '__main__':
    asyncio.run(init_models())
