from typing import Annotated

from loguru import logger
from sqlalchemy import select, func, Column
from sqlalchemy.orm import selectinload, QueryableAttribute
from sqlalchemy.sql import and_
from sqlalchemy import exc as sqlexc

from fastapi import Depends, Request

from config import auth as auth_conf

from schemes import sql as orm
from schemes import auth as auth_sche

from .database import init_session_maker, session_maker, SessionDep

from exception import error as exc

from provider import auth as auth_pd

from .database import init_session_maker, session_maker, add_eager_load_to_stmt

init_session_maker()


async def get_current_token(req: Request):
    """
    Get current user based on user token in request cookies

    This function could be used as a FastAPI dependency
    """
    # no token
    token = req.cookies.get(auth_conf.JWT_FRONTEND_COOKIE_KEY)
    if token is None:
        raise exc.TokenError(no_token=True)

    token_data = auth_sche.TokenData.from_jwt_str(token)

    # token expired
    if token_data.is_expired():
        raise exc.TokenError(expired=True)

    return token_data


async def get_current_user(
    session: SessionDep,
    token: Annotated[auth_sche.TokenData, Depends(get_current_token)],
):
    """
    Get current user based on user token

    This function could be used as a FastAPI dependency
    """
    return await get_user_from_user_id(
        session,
        user_id=token.user_id,
        eager_load=[orm.User.roles],
    )


async def get_user_from_user_id(
    session: SessionDep,
    user_id: int,
    eager_load: list[QueryableAttribute] | None = None,
) -> orm.User:
    """
    Get ORM user instance based on ``user_id``

    Parameters:
        user_id: The unique id of user
        eager_load: Optional. List of User ORM class relation attributes to be eagerly loaded

    Raise exception if user not exists
    """
    stmt = (
        select(orm.User)
        .where(orm.User.user_id.__eq__(user_id))
        .where(orm.User.deleted.__eq__(False))
    )
    if eager_load is not None:
        add_eager_load_to_stmt(stmt, eager_load)

    logger.debug(f"Try find user with user_id: {user_id}")
    res = (await session.scalars(stmt)).one()

    return res


async def update_user_description(
    session: SessionDep, user: orm.User, description: str
):
    """Update user description in database"""
    user.description = description
    await session.commit()
