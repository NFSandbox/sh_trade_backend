import time
from typing import Annotated

from loguru import logger
from fastapi import Depends

from sqlalchemy import Select, select
from sqlalchemy.orm import MappedColumn, selectinload, QueryableAttribute
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from config import sql

_engine = create_async_engine(
    f"mysql+aiomysql://"
    f"{sql.DB_USERNAME}:{sql.DB_PASSWORD}"
    f"@{sql.DB_HOST}/{sql.DB_NAME}",
    echo=False,
)

# async version session maker
# call get_session_maker() before use this instance
session_maker: async_sessionmaker[AsyncSession] | None = async_sessionmaker[
    AsyncSession
](_engine, expire_on_commit=False)


def init_session_maker(force_create: bool = False):
    """
    Get the current session maker instance, create one if not exists.

    Parameters:

    - ``force_create`` Always create new session maker if ``True``
    """
    global session_maker
    if (session_maker is None) or force_create:
        logger.info("Session maker initializing...")
        session_maker = async_sessionmaker[AsyncSession](
            _engine, expire_on_commit=False
        )
        logger.success("Session maker initialized")
    else:
        logger.debug("Returning existing session_maker...")
    return session_maker


async def get_session():
    """Get a new session using session maker

    Notes:

    This function could be used as FastAPI dependency.
    Once you get the returned `Session` object, it must be used in Context Manager pattern like below:

        async with get_session() as session:
            session.execute(...)

    Otherwise, the Session may never be closed properly
    """
    maker = init_session_maker()
    async with maker() as session:
        # logger.debug(f'Before yield session')
        yield session
        # logger.debug(f'After yield session')


def add_eager_load_to_stmt(stmt: Select, attr_list: list[QueryableAttribute]):
    for attr in attr_list:
        stmt = stmt.options(selectinload(attr))
    return stmt


SessionDep = Annotated[AsyncSession, Depends(get_session)]
"""SessionDep type annotation which could be used in FastAPI function

Examples:

    @router.get('/test')
    def get_user_from_db(session: SessionDep):
        return get_user(session)

"""


async def try_commit(ss: SessionDep):
    """
    Try commit the current session and return None.

    Raise if failed to commit

    Usage

        session.add_all(some_entities)
        await try_commit(session)
    """
    try:
        await ss.commit()
        return
    except:
        await ss.rollback()
        raise
