"""
Including provider functions related to Favourite Item feature
"""

import time

from typing import Annotated, cast, List, Sequence

from loguru import logger
from sqlalchemy import select, update, func, Column, distinct, or_
from sqlalchemy.orm import selectinload, QueryableAttribute, aliased
from sqlalchemy.sql import and_
from sqlalchemy import exc as sqlexc

from fastapi import Depends, Request, Body

from config import auth as auth_conf
from config import system as sys_conf


from schemes import sql as orm
from schemes import db as db_sche
from schemes import general as gene_sche

from .database import init_session_maker, session_maker, SessionDep, try_commit
from .user import CurrentUserDep, CurrentUserOrNoneDep, get_user_from_user_id
from .item import get_item_by_id

from exception import error as exc

init_session_maker()


async def check_if_item_in_fav(ss: SessionDep, user: orm.User, item_id: int) -> None:
    """
    Check if an item already in the favourite list of a certain user

    Raises

    - `item_already_in_fav` (409) (DuplicatedError)
    """
    stmt = (
        select(func.count())
        .select_from(orm.AssociationUserFavouriteItem)
        .where(
            orm.AssociationUserFavouriteItem.user_id == user.user_id,
            orm.AssociationUserFavouriteItem.item_id == item_id,
        )
    )
    # get count
    count = await ss.scalar(stmt)
    if count is None:
        raise ValueError(f"Count should always be an integer number, current: {count}")

    # if count > 0, means fav relation already exists
    if count > 0:
        raise exc.DuplicatedError(
            name="item_already_in_fav",
            message=f"Item with id: {item_id} already in the favourite list of user with id: {user.user_id}",
        )


async def get_fav_items(ss: SessionDep, user: orm.User) -> Sequence[orm.Item]:
    """
    Get all favourite items of a certain user
    """
    user = await get_user_from_user_id(ss, user.user_id)
    items = await ss.run_sync(lambda ss: user.fav_items)
    return items


async def add_fav_item(ss: SessionDep, user: orm.User, item_id: int) -> orm.Item:
    """
    Add an item to user's favourite, then return the item orm instance

    Raises

    - `fav_items_limit_exceeded` (400) (LimitExceededError)
    - `item_already_in_fav` (409) (DuplicatedError)
    """
    # get item
    item = await get_item_by_id(ss, item_id)

    # check duplication
    await check_if_item_in_fav(ss, user, item_id)

    # get user fav items
    user_fav_count: int = await ss.run_sync(lambda ss: len(user.fav_items))

    # check fav item count max limit
    if user_fav_count >= sys_conf.MAX_USER_FAV_ITEMS:
        raise exc.LimitExceededError(
            name="fav_items_limit_exceeded",
            message=f"User with id: {user.user_id} has reached the maximum favourite item count: {sys_conf.MAX_USER_FAV_ITEMS}",
        )

    # add item to user's fav
    user.fav_items.append(item)

    await try_commit(ss)

    return item


async def remove_fav_items(
    ss: SessionDep, user: orm.User, item_id_list: Sequence[int] | None
) -> gene_sche.BulkOpeartionInfo:
    """
    Remove (soft delete) items from user's favourite, return `BulkOpeartionInfo`

    Param

    - `item_id_list` If `None`, will remove all fav items from this user,
      else only remove items which's `item_id` in list
    """
    stmt = select(orm.AssociationUserFavouriteItem).where(
        orm.AssociationUserFavouriteItem.user_id == user.user_id,
    )

    if item_id_list is not None:
        stmt = stmt.where(orm.AssociationUserFavouriteItem.item_id.in_(item_id_list))

    item_asso_to_remove = (await ss.scalars(stmt)).all()

    # remove fav items
    bulk_count = gene_sche.BulkOpeartionInfo(operation="Delete fav items")
    for i_asso in item_asso_to_remove:
        i_asso.delete()  # soft delete
        bulk_count.inc()

    await try_commit(ss)

    return bulk_count
