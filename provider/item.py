from typing import Annotated, cast, List

from loguru import logger
from sqlalchemy import select, update, func, Column, distinct
from sqlalchemy.orm import selectinload, QueryableAttribute, aliased
from sqlalchemy.sql import and_
from sqlalchemy import exc as sqlexc

from fastapi import Depends, Request

from config import auth as auth_conf

from schemes import sql as orm
from schemes import db as db_sche

from .database import init_session_maker, session_maker, SessionDep
from .user import CurrentUserDep, CurrentUserOrNoneDep, get_user_from_user_id

from exception import error as exc

init_session_maker()


async def get_item_by_id(ss: SessionDep, item_id: int):
    # get item
    try:
        item = await ss.get(orm.Item, item_id)
        if item is None or item.deleted:
            raise
        return item
    except:
        raise exc.NoResultError("The item that question points to does not exists")


async def get_user_items(
    ss: SessionDep,
    user_id: int,
    time_desc: bool = True,
    ignore_hide: bool = True,
    ignore_sold: bool = False,
):
    """
    Get selling items of a user by user id
    """
    # promise user is valid
    await get_user_from_user_id(ss, user_id)

    # get items owned by this user that not been deleted
    stmt = (
        select(orm.Item)
        .select_from(orm.User)
        .join(
            orm.User.items.and_(orm.User.user_id == user_id).and_(
                orm.Item.deleted == False
            )
        )
    )

    # determine order
    if time_desc:
        stmt = stmt.order_by(orm.Item.created_time.desc())
    else:
        stmt = stmt.order_by(orm.Item.created_time.asc())

    # filter by valid state if needed
    if ignore_hide:
        stmt = stmt.where(orm.Item.state != orm.ItemState.hide)
    if ignore_sold:
        stmt = stmt.where(orm.Item.state != orm.ItemState.sold)

    res = await ss.scalars(stmt)
    res = res.all()

    return res


async def get_user_item_count(ss: SessionDep, user_id: int) -> int:
    """
    Get total count of items of a user

    - Hidden item included
    - Sold/deleted items excluded
    """
    # promise valid user
    await get_user_from_user_id(ss, user_id)

    # query count
    stmt = (
        select(func.count())
        .select_from(orm.User)
        .join(
            orm.User.items.and_(orm.Item.deleted == False).and_(
                orm.Item.state != orm.ItemState.sold
            )
        )
        .where(orm.User.user_id == user_id)
    )

    res = await ss.scalars(stmt)
    res = res.one()

    return res


async def add_item(ss: SessionDep, user: CurrentUserDep, item: db_sche.ItemIn):
    """
    Add an item for a user
    """
    # create new item orm
    try:
        item_orm = orm.Item(**item.model_dump())
        await user.awaitable_attrs.items
        user.items.append(item_orm)
        await ss.commit()
        await ss.refresh(item_orm)
        return item_orm
    except:
        await ss.rollback()
        raise


async def item_belong_to_user(ss: SessionDep, item_id: int, user_id: int):
    """
    Check if an item belongs to a specific user

    Return Item instance if this item is belong to the user, else raise.

    Raises

    - `item_belonging_test_failed`
    """
    # promise this is valid user
    await get_user_from_user_id(ss, user_id)

    stmt = select(orm.User).join(
        orm.User.items.and_(orm.Item.deleted == False)
        .and_(orm.Item.item_id == item_id)
        .and_(orm.User.user_id == user_id)
    )

    try:
        res = await ss.scalars(stmt)
        res = res.one()
        return res
    except:
        raise exc.BaseError(
            "item_belonging_test_failed",
            f"Item with id: {item_id} does not belongs to user with id: {user_id}",
            status=500,
        )


async def get_cascade_items_from_users(ss: SessionDep, users: orm.User):
    pass


async def clean_up_question_with_deleted_items(ss: SessionDep):
    """A cleaning function used to remove items that points to soft-deleted items"""

    stmt_question_with_deleted_items = select(orm.Question).join(
        orm.Question.item.and_(orm.Item.deleted == True).and_(
            orm.Question.deleted == False
        )
    )

    res = await ss.scalars(stmt_question_with_deleted_items)
    questions = res.all()

    count = 0
    for q in questions:
        if q.deleted == False:
            q.deleted = True
            count += 1

    try:
        await ss.commit()
        logger.info(f"Cleaned {count} unnecessary questions from database")
        return count
    except:
        await ss.rollback()
        raise
