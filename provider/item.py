import time

from typing import Annotated, cast, List, Sequence

from loguru import logger
from sqlalchemy import select, update, func, Column, distinct, or_
from sqlalchemy.orm import selectinload, QueryableAttribute, aliased
from sqlalchemy.sql import and_
from sqlalchemy import exc as sqlexc

from fastapi import Depends, Request

from config import auth as auth_conf

from schemes import sql as orm
from schemes import db as db_sche
from schemes import general as gene_sche

from .database import init_session_maker, session_maker, SessionDep
from .user import CurrentUserDep, CurrentUserOrNoneDep, get_user_from_user_id

from exception import error as exc

init_session_maker()


async def get_item_by_id(ss: SessionDep, item_id: int):
    # get item
    try:
        item = await ss.get(orm.Item, item_id)
        if item is None or item.deleted_at is not None:
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
                orm.Item.deleted_at == None
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
            orm.User.items.and_(orm.Item.deleted_at == None).and_(
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


async def update_item(ss: SessionDep, info: db_sche.ItemInWithId):
    """Update item info and return updated item info"""
    item = await get_item_by_id(ss, info.item_id)

    item.name = info.name
    item.description = info.description
    item.price = info.price

    try:
        await ss.commit()
        await ss.refresh(item)
        return item
    except:
        await ss.rollback()
        raise


async def check_item_belong_to_user(ss: SessionDep, item_id: int, user_id: int):
    """
    Check if an item belongs to a specific user

    Return Item instance if this item is belong to the user, else raise.

    Raises

    - `item_belonging_test_failed` 403
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
        raise exc.PermissionError(
            message=f"Item with id: {item_id} does not belongs to user with id: {user_id}",
        )


async def get_questions_by_item_id(
    ss: SessionDep,
    item_id: int,
    user_id: int | None = None,
    time_desc: bool = True,
    unanswered_only: bool = False,
):
    """
    Return all questions related to an item

    Args

    - `item_id` The item_id of the item that you want to get questions of
    - `user_id` Which user are requesting this questions, used for access control
    """
    # promise valid user
    if user_id is not None:
        user = await get_user_from_user_id(ss, user_id)
    # promise valid item
    item = await get_item_by_id(ss, item_id)

    # permission flags
    item_owner = False

    # check permission
    if user_id is not None:
        try:
            # check if this user is the owner of the item
            await check_item_belong_to_user(ss, item.item_id, user_id)
            item_owner = True
        except:
            pass

    # lazy load questions
    stmt = select(orm.Question).join_from(
        orm.Item,
        orm.Item.questions.and_(orm.Question.deleted_at == None).and_(
            orm.Item.item_id == item_id
        ),
    )

    # if no user_id (access by guest)
    # only see public question
    if user_id is None:
        stmt = stmt.where(orm.Question.public == True)

    # if user are not owner, only see public or self-asked question
    if (user_id is not None) and (not item_owner):
        stmt = stmt.options(selectinload(orm.Question.asker)).where(
            or_(orm.Question.public == True, orm.Question.asker == user)
        )

    # order
    if time_desc:
        stmt = stmt.order_by(orm.Question.created_time.desc())
    else:
        stmt = stmt.order_by(orm.Question.created_time.asc())

    # unanswered
    if unanswered_only:
        stmt = stmt.where(orm.Question.answer == None)

    # debug
    logger.debug(f"SQL Stmt: \n{stmt}")

    res = await ss.scalars(stmt)
    questions = res.all()

    return questions


async def get_question_by_id(ss: SessionDep, question_id: int):
    """Get question by question_id

    Raises

    - `no_result` (404) No question found with specified ID
    """
    question = await ss.get(orm.Question, question_id)
    if question is None or question.deleted_at is not None:
        raise exc.NoResultError(f"No question found with id: {question_id}")

    return question


async def check_question_belongs_to_user(
    ss: SessionDep, question_id: int, user_id: int
):
    """Check if a question belongs to a specific user

    Return

    - User that the question belongs to if found

    Raises

    - `no_result`
      - No question found with specified ID
      - The item that this question points to no longer exists
      - The user that this question points to no longer exists
    - `permission_required`
      - The question is not belongs to specified user
    """
    # get question
    question = await get_question_by_id(ss, question_id)

    # get item
    item: orm.Item = await question.awaitable_attrs.item
    if item.deleted_at is not None:
        raise exc.NoResultError(
            "The item that this question points to no longer exists"
        )

    # get user
    await item.awaitable_attrs.seller
    user = item.seller
    if user.deleted_at is not None:
        raise exc.NoResultError(
            "The user that this question points to no longer exists"
        )

    if user.user_id != user_id:
        raise exc.PermissionError(
            message="The question is not belongs to specified user"
        )

    return user


async def answer_question(ss: SessionDep, question_id: int, answer: str):
    """Add or update the answer of a question, return the updated ORM instance of question"""
    question = await get_question_by_id(ss, question_id)
    question.answer = answer
    question.answered_time = orm.get_current_timestamp_ms()

    try:
        await ss.commit()
        await ss.refresh(question)
        return question
    except:
        await ss.rollback()
        raise


async def remove_questions(
    ss: SessionDep,
    questions: Sequence[orm.Question],
    commit: bool = True,
):
    q_count = gene_sche.BlukOpeartionInfo(operation="Delete questions")

    for q in questions:
        if q.deleted_at is None:
            q_count.inc()
            q.delete()

    if commit:
        try:
            await ss.commit()
        except:
            await ss.rollback()
            raise

    return q_count


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


async def remove_items_cascade(
    ss: SessionDep,
    items: Sequence[orm.Item],
    constraint: bool = False,
) -> List[gene_sche.BlukOpeartionInfo]:
    """
    Soft delete a list of items, with cascade delete of all relavant data

    Args

    - `items` The items need to be cascade delete
    - `constraint` If `True`, raise error if has cascade items.

    Cascade

    - `Question` All question related to these items

    Raises

    - `cascade_constraint`
    """
    # record the effective delete count of all entities
    q_count = gene_sche.BlukOpeartionInfo(operation="Cascading delete questions")
    i_count = gene_sche.BlukOpeartionInfo(operation="Delete items")
    try:
        # delete question cascade of item
        questions = await get_cascade_questions_from_items(ss, items)
        # raise error if constraint
        if constraint and len(questions) > 0:
            raise exc.CascadeConstraintError(
                "Could not remove items with active questions"
            )

        q_count = await remove_questions(ss, questions, commit=False)

        # delete items itself
        for i in items:
            if i.deleted_at == None:
                i_count.inc()
            i.delete()

        await ss.commit()

        # return info
        return [i_count, q_count]
    except:
        await ss.rollback()
        raise


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
