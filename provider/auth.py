from typing import Sequence

from loguru import logger
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import and_
from sqlalchemy import exc as sqlexc

from schemes import sql as orm
from .database import init_session_maker, session_maker

from exception import error as exc

# make sure session has already been initialized
init_session_maker()


async def get_user_by_contact_info(login_info: str) -> orm.User | None:
    """
    Try to get user by contact info

    Return:
        ORM User instance if user found. Otherwise, return None
    """
    stmt_username = (
        select(orm.User)
        .options(selectinload(orm.User.roles))
        .where(orm.User.username.__eq__(login_info))
    )
    stmt_contact_info = (
        select(orm.ContactInfo)
        .options(
            selectinload(orm.ContactInfo.user).options(selectinload(orm.User.roles))
        )
        .where(orm.ContactInfo.contact_info.__eq__(login_info))
        .where(orm.ContactInfo.deleted.__eq__(False))
    )
    async with session_maker() as session:
        logger.debug(f"Contact info: {login_info}")
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
        if user.deleted:
            raise exc.AuthError(invalid_contact=True)

        # success
        return user
