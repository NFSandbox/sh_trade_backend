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

from .core import *

__all__ = [
    "update_user_description",
    "check_duplicate_contacts",
    "add_contact_info",
    "get_all_active_buyers",
    "check_get_contact_info_permission",
    "get_user_contact_info_list",
]

init_session_maker()


async def update_user_description(
    session: SessionDep, user: orm.User, description: str
):
    """Update user description in database"""
    user.description = description
    await session.commit()


async def check_duplicate_contacts(ss: SessionDep, info: db_sche.ContactInfoIn) -> None:
    """
    Check if there is a same contact info in database

    Return: `None`

    Raise

    - `contact_info_already_exists`
    """
    check_dup_stmt = (
        select(func.count())
        .select_from(orm.ContactInfo)
        .distinct()
        .where(orm.ContactInfo.contact_info == info.contact_info)
        .where(orm.ContactInfo.contact_type == info.contact_type)
        .where(orm.ContactInfo.deleted_at == None)
    )
    res = await ss.scalars(check_dup_stmt)
    res = res.one()
    if res > 0:
        raise exc.DuplicatedError(
            name="contact_info_already_exists",
            message="Contact info already exists or used by others",
        )


async def add_contact_info(ss: SessionDep, user: orm.User, info: db_sche.ContactInfoIn):
    """
    Add a new contact info to a user

    Raises

    - `contact_info_already_exists`
    """
    try:
        # ensure no duplication
        await check_duplicate_contacts(ss, info)

        # create new contact info orm instance
        new_contact = orm.ContactInfo(**info.model_dump())

        cast("List[orm.ContactInfo]", await user.awaitable_attrs.contact_info).append(
            new_contact
        )

        await ss.commit()
        return new_contact

    except Exception as e:
        await ss.rollback()
        raise


async def get_all_active_buyers(ss: SessionDep, user_id: int):
    """
    Get all active buyers of a user

    Notes:

    - Active buyer of a user means all other users that have **active processing trade records
      of an item owned by this user**
    - The info returned by this function is usually used to check sellers' permission to access
      the contact info of a buyer
    """

    user1 = aliased(orm.User)
    item1 = aliased(orm.Item)

    # all items selling by seller
    _subq_seller_valid_items = (
        select(item1)
        .select_from(user1)
        .join(
            user1.items.of_type(item1)
            .and_(user1.deleted_at == None)
            .and_(user1.user_id == user_id)
        )
        .where(item1.deleted_at == None)
        .where(item1.state == orm.ItemState.valid)
        .subquery()
    )

    valid_item = aliased(orm.Item, _subq_seller_valid_items, "valid_item")

    # all trade record with those items
    _subq_valid_trades = (
        select(orm.TradeRecord).join_from(
            valid_item,
            valid_item.record.and_(orm.TradeRecord.deleted_at == None).and_(
                orm.TradeRecord.state == orm.TradeState.processing
            ),
        )
        # .where(orm.TradeRecord.deleted == False)
        # .where(orm.TradeRecord.state == orm.TradeState.processing)
        .order_by(orm.TradeRecord.created_time.desc())
    ).subquery()

    valid_trade = aliased(orm.TradeRecord, _subq_valid_trades, "valid_trade")

    stmt_valid_buyers = select(orm.User).join(
        valid_trade, orm.User.user_id == valid_trade.buyer_id
    )

    res = await ss.scalars(stmt_valid_buyers)
    res = res.all()

    logger.debug(f"SQL for contact info permission: \n {stmt_valid_buyers}")
    logger.debug(f"Return of SQL execution: {res}")

    return res


async def check_get_contact_info_permission(
    ss: SessionDep,
    requester_id: int,
    user_id: int,
):
    """Check if a specific user has the permission to access another user's contact info

    Return None if check passed. Raise error if insufficient permission

    Args

    - `requester_id`: `user_id` of requester
    - `user_id`: `user_id` of the user whose contact info is being requested

    Raises

    - `permission_required`
    - `no_result`

    For more info about permission check related to contact info, check out
    [this Wiki page](https://github.com/NFSandbox/sh_trade_backend/wiki/User-Contact-Info)
    """
    # promise this two user is exists and valid
    try:
        requester = await get_user_from_user_id(ss, requester_id)
        user = await get_user_from_user_id(ss, user_id)
    except exc.NoResultError as e:
        raise exc.NoResultError(
            message="Could not found requester or user by provided user ID"
        ) from e

    # get self contact info is always allowed
    if user_id == requester_id:
        return

    # get all valid buyers list, check if the requested user in this list
    buyer_list = await get_all_active_buyers(ss, requester_id)
    # for buyer in buyer_list:
    #     if buyer.user_id == user.user_id:
    #         return
    if user in buyer_list:
        return

    # raise error
    raise exc.PermissionError(
        roles=await requester.awaitable_attrs.roles,
        message=f"Current account do not have permission to get contact info of user with user_id: {user.user_id}",
    )


async def get_user_contact_info_list(ss: SessionDep, user: orm.User):
    """
    Return list of contact info of the user

    Notice that is function do not contain any permission check
    """
    stmt = (
        select(orm.ContactInfo)
        .select_from(orm.User)
        .join(orm.User.contact_info.and_(orm.User.user_id == user.user_id))
    )

    contact_list = await ss.scalars(stmt)
    contact_list = contact_list.all()

    return contact_list


async def _get_contact_info_dep(ss: SessionDep, user: CurrentUserDep):
    return get_user_contact_info_list(ss, user)


CurrentContactInfoDep: Annotated[List[orm.ContactInfo], Depends(_get_contact_info_dep)]
"""
Dependency annoations for contact info of current user.
"""
