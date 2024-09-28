from typing import Sequence, Annotated

from loguru import logger
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import and_
from sqlalchemy import exc as sqlexc

from fastapi import Body

from schemes import sql as orm
from .database import init_session_maker, session_maker, SessionDep

from exception import error as exc

# make sure session has already been initialized
init_session_maker()


async def get_user_by_user_id(session: SessionDep, user_id: int):
    """
    Get user from database by user_id

    Return `None` if not valid user

    Notes:
    - Deleted user will not be returned
    """
    return (
        await session.scalars(select(orm.User).where(orm.User.user_id == user_id))
    ).one_or_none()


async def get_user_by_contact_info(
    session: SessionDep, login_info: Annotated[str, Body]
) -> orm.User | None:
    """
    Try to get user by contact info

    Return:
    - ORM User instance if user found. Otherwise, return `None`

    Notes:
    - When used as dependency, the `login_info` is required in request Body.
    """
    stmt_username = select(orm.User).where(orm.User.username.__eq__(login_info))
    stmt_contact_info = (
        select(orm.ContactInfo)
        .options(selectinload(orm.ContactInfo.user))
        .where(orm.ContactInfo.contact_info == login_info)
        .where(orm.ContactInfo.deleted_at == None)
    )

    # first try to find username
    user = (await session.scalars(stmt_username)).one_or_none()
    if not user:
        # there should be at most one result in the database, since contact_info should be unique
        contact = (await session.scalars(stmt_contact_info)).one_or_none()

        # no corresponding contact info found in db
        if contact is None:
            raise exc.AuthError(invalid_contact=True)

        # found corresponding info, find relevant user
        user = contact.user

    # user invalid
    if user.deleted_at is not None:
        raise exc.AuthError(invalid_contact=True)

    # success
    return user


async def check_no_username_duplicate(ss: SessionDep, username: str):
    """
    Check if username already exists in database

    Return None if check pass, else raise.
    """
    stmt = (
        select(func.count()).select_from(orm.User).where(orm.User.username == username)
    )

    res = (await ss.scalars(stmt)).one()

    if res > 0:
        raise exc.DuplicatedError(
            name="username_already_exists",
            message="The choosed username already used by others, please change username and try again",
        )
