from typing import Annotated, cast, List

from loguru import logger
from sqlalchemy import select, func, Column, distinct
from sqlalchemy.orm import selectinload, QueryableAttribute, aliased
from sqlalchemy.sql import and_
from sqlalchemy import exc as sqlexc

from fastapi import Depends, Request

from config import auth as auth_conf

from schemes import sql as orm
from schemes import auth as auth_sche
from schemes import db as db_sche

from ..database import init_session_maker, session_maker, SessionDep

from exception import error as exc

from ..database import init_session_maker, add_eager_load_to_stmt


__all__ = [
    "CurrentUserDep",
    "CurrentUserOrNoneDep",
    "get_user_from_user_id",
    "get_current_user_or_none",
    "get_current_user",
    "get_current_token",
]


async def get_current_token(req: Request):
    """
    Get current user based on user token in request cookies or raise error

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


CurrentUserDep = Annotated[orm.User, Depends(get_current_user)]
"""
Dependency annotaion for `get_current_user` function
"""


async def get_current_user_or_none(
    ss: SessionDep,
    req: Request,
) -> orm.User | None:
    """
    FastAPI dependency to get current user.

    Similar to `get_current_user()` function. With the only difference that
    when this function could not retrieve valid user info, it will NOT raise error
    but return `None`
    """
    try:
        token = await get_current_token(req)
        return await get_current_user(ss, token)
    except:
        return None


CurrentUserOrNoneDep = Annotated[orm.User | None, Depends(get_current_user_or_none)]
"""
Similar to `CurrentUserDep`

Check out docs of `get_current_user()` and `get_current_user_or_none()` for more info 
and about the difference of these two deps.
"""


async def get_user_from_user_id(
    session: SessionDep,
    user_id: int,
    eager_load: list[QueryableAttribute] | None = None,
) -> orm.User:
    """
    Get ORM user instance based on ``user_id``

    Args

    - user_id: The unique id of user
    - eager_load: Optional. List of User ORM class relation attributes to be eagerly loaded

    Raises

    - `no_result`
    """
    stmt = (
        select(orm.User)
        .where(orm.User.user_id.__eq__(user_id))
        .where(orm.User.deleted_at.__eq__(None))
    )
    if eager_load is not None:
        add_eager_load_to_stmt(stmt, eager_load)
    try:
        res = (await session.scalars(stmt)).one()
    except sqlexc.NoResultFound as e:
        raise exc.NoResultError(message=f"User with id:{user_id} not exists") from e

    return res
