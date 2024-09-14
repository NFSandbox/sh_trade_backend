import time

from loguru import logger

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from config import sql

_engine = create_async_engine(
    f"mysql+aiomysql://"
    f"{sql.DB_USERNAME}:{sql.DB_PASSWORD}"
    f"@{sql.DB_HOST}/{sql.DB_NAME}"
)

# async version session maker
# call get_session_maker() before use this instance
session_maker: async_sessionmaker | None = async_sessionmaker(_engine, expire_on_commit=False)


def init_session_maker(force_create: bool = False) -> async_sessionmaker:
    """
    Get the current session maker instance, create one if not exists.

    Parameters:
    - ``force_create`` Always create new session maker if ``True``
    """
    global session_maker
    if (session_maker is None) or force_create:
        logger.info('Session maker initializing...')
        session_maker = async_sessionmaker(_engine, expire_on_commit=False)
        logger.success('Session maker initialized')
    else:
        logger.debug('Session maker already ready')
    return session_maker
