import time

from typing import Annotated, cast, List, Sequence

from loguru import logger
from sqlalchemy import select, update, func, Column, distinct, or_
from sqlalchemy.orm import selectinload, QueryableAttribute, aliased
from sqlalchemy.sql import and_
from sqlalchemy import exc as sqlexc

from fastapi import Depends, Request, Body

from config import auth as auth_conf

from schemes import sql as orm
from schemes import db as db_sche
from schemes import general as gene_sche

from ..database import SessionDep, try_commit

from exception import error as exc

__all__ = [
    "get_item_by_id",
    "remove_questions",
    "get_cascade_items_from_users",
    "get_cascade_questions_from_items",
    "get_cascade_association_items_tags_from_items",
    "remove_associations_items_tags",
    "remove_items_cascade",
    "clean_up_question_with_deleted_items",
]


async def get_item_by_id(ss: SessionDep, item_id: int):
    """
    Get item using item_id

    Raises:
        exc.NoResultError: if item not found
    """
    # get item
    try:
        item = await ss.get(orm.Item, item_id)
        if item is None or item.deleted_at is not None:
            raise
        return item
    except:
        raise exc.NoResultError(f"Could not find item with with id: {item_id}")


async def remove_questions(
    ss: SessionDep,
    questions: Sequence[orm.Question],
    commit: bool = True,
) -> list[gene_sche.BulkOpeartionInfo]:
    q_count = gene_sche.BulkOpeartionInfo(operation="Delete questions")

    for q in questions:
        if q.deleted_at is None:
            q_count.inc()
            q.delete()

    if commit:
        await try_commit(ss)

    return [q_count]


async def get_cascade_items_from_users(
    ss: SessionDep, users: Sequence[orm.User], exclude_deleted: bool = True
):
    """
    Get a list of sellers(`User`) from a list of items(`Item`)
    """

    # construct statement
    stmt = (
        select(orm.Item)
        .join(orm.Item.seller)
        .where(orm.User.user_id.in_([u.user_id for u in users]))
    )
    if exclude_deleted:
        stmt = stmt.where(orm.Item.deleted_at == None)

    res = await ss.scalars(stmt)
    items = res.all()

    return items


async def get_cascade_association_fav_items_from_user(
    ss: SessionDep, users: Sequence[orm.User]
):
    """
    Get fav items association of a list of users
    """
    stmt = select(orm.AssociationUserFavouriteItem).where(
        orm.AssociationUserFavouriteItem.user_id.in_([u.user_id for u in users])
    )

    return (await ss.scalars(stmt)).all()


async def get_cascade_questions_from_items(
    ss: SessionDep, items: Sequence[orm.Item], exclude_deleted: bool = True
):
    stmt = (
        select(orm.Question)
        .join(orm.Question.item)
        .where(orm.Item.item_id.in_([i.item_id for i in items]))
    )

    if exclude_deleted:
        stmt = stmt.where(orm.Question.deleted_at == None)

    res = await ss.scalars(stmt)
    return res.all()


async def get_cascade_questions_from_askers(ss: SessionDep, askers: Sequence[orm.User]):
    """Get questions by a list of askers"""
    askers_id_list = [a.user_id for a in askers]

    stmt = select(orm.Question).where(orm.Question.asker_id.in_(askers_id_list))

    return (await ss.scalars(stmt)).all()


async def get_cascade_association_items_tags_from_items(
    ss: SessionDep, items: Sequence[orm.Item]
) -> Sequence[orm.AssociationUserFavouriteItem]:
    stmt = select(orm.AssociationItemTag).where(
        orm.AssociationItemTag.item_id.in_([i.item_id for i in items])
    )
    return (await ss.scalars(stmt)).all()


async def remove_associations_items_tags(
    ss: SessionDep, associations: Sequence[orm.AssociationItemTag], commit: bool = True
):
    count = gene_sche.BulkOpeartionInfo(operation="Remove item-tag associations")

    for a in associations:
        count.inc()
        a.delete()

    if commit:
        await try_commit(ss)

    return count


async def remove_items_cascade(
    ss: SessionDep,
    items: Sequence[orm.Item],
    constraint: bool = False,
    commit: bool = True,
) -> List[gene_sche.BulkOpeartionInfo]:
    """
    Soft delete a list of items, with cascade delete of all relavant data

    Args

    - `items` The items need to be cascade delete
    - `constraint` If `True`, raise error if has cascade items

    Cascade

    - `Question` All question related to these items
    - `AssociationItemTag` All tags associations
    - `AssociationFavItem`

    Raises

    - `cascade_constraint`
    """
    # record the effective delete count of all entities
    i_count = gene_sche.BulkOpeartionInfo(operation="Delete items")

    # delete question cascade of item
    questions = await get_cascade_questions_from_items(ss, items)
    # raise error if constraint
    if constraint and len(questions) > 0:
        raise exc.CascadeConstraintError("Could not remove items with active questions")
    q_count_list = await remove_questions(ss, questions, commit=False)

    # remove tag associations
    associations = await get_cascade_association_items_tags_from_items(ss, items)
    t_count = await remove_associations_items_tags(ss, associations, commit=False)

    # late import
    from ..fav.core import remove_fav_items_cascade, get_cascade_fav_items_by_items

    # remove fav item association
    asso_fav_items = await get_cascade_fav_items_by_items(ss, items)

    fav_count = await remove_fav_items_cascade(ss, asso_fav_items, commit=False)

    # todo
    # remove all related trade record

    # delete items itself
    for i in items:
        if i.deleted_at == None:
            i_count.inc()
        i.delete()

    if commit:
        await try_commit(ss)

    # return info
    return [i_count] + q_count_list + [t_count] + fav_count


async def clean_up_question_with_deleted_items(ss: SessionDep):
    """A cleaning function used to remove items that points to soft-deleted items"""

    stmt_question_with_deleted_items = select(orm.Question).join(
        orm.Question.item.and_(orm.Item.deleted_at != None).and_(
            orm.Question.deleted_at == None,
        )
    )

    res = await ss.scalars(stmt_question_with_deleted_items)
    questions = res.all()

    count = 0
    for q in questions:
        if q.deleted_at == None:
            q.delete()
            count += 1

    try:
        await ss.commit()
        logger.info(f"Cleaned {count} unnecessary questions from database")
        return count
    except:
        await ss.rollback()
        raise
