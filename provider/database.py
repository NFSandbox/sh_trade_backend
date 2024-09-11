import time

from loguru import logger

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from config import sql

_engine = create_async_engine(
    f"mysql+aiomysql://"
    f"{sql.DB_USERNAME}:{sql.DB_PASSWORD}"
    f"@{sql.DB_HOST}/{sql.DB_NAME}"
)

# async version sessionmaker
# call init_sessionmaker() before use this instance
session_maker: async_sessionmaker | None = async_sessionmaker(_engine, expire_on_commit=False)


async def init_sessionmaker(force_create: bool = False) -> async_sessionmaker:
    """
    (Async) Tool function to initialize the session maker if it's not ready.
    :return: None
    """
    global session_maker
    if (session_maker is None) or force_create:
        logger.info('Session maker initializing...')
        session_maker = async_sessionmaker(_engine, expire_on_commit=False)
        logger.success('Session maker initialized')
    else:
        logger.debug('Session maker already ready')
    return session_maker
