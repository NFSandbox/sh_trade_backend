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

from ..database import init_session_maker, session_maker, SessionDep, try_commit
from ..user.core import CurrentUserDep, CurrentUserOrNoneDep, get_user_from_user_id
from ..fav.core import get_fav_count_of_item

from .core import *


from exception import error as exc

init_session_maker()

__all__ = [
    "get_recent_published",
    "get_user_item_count",
    "update_tags_of_item",
    "add_item",
    "update_item",
    "check_item_belong_to_user",
    "get_question_by_id",
    "get_question_by_id",
    "check_question_belongs_to_user",
    "answer_question",
    "get_tags_by_names",
    "add_tags_if_not_exists",
    "remove_tags_of_item",
    "get_user_items",
]


async def get_recent_published(ss: SessionDep):
    """
    Get list of items that published recently
    """
    stmt = select(orm.Item).order_by(orm.Item.created_time.desc()).limit(50)
    return (await ss.scalars(stmt)).all()


async def get_user_items(
    ss: SessionDep,
    user_id: int,
    time_desc: bool = True,
    ignore_hide: bool = True,
    ignore_sold: bool = False,
    load_tags: bool = True,
    pagination: gene_sche.PaginationConfig | None = None,
):
    """
    Get selling items of a user by user id
    """
    # use default pagination
    if pagination is None:
        pagination = gene_sche.PaginationConfig()

    # promise user is valid
    user = await get_user_from_user_id(ss, user_id)

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

    # load tags
    if load_tags:
        stmt = stmt.options(
            selectinload(orm.Item.association_tags).options(
                selectinload(orm.AssociationItemTag.tag)
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

    # get total count
    total_count = await ss.scalar(
        select(func.count(orm.Item.item_id)).select_from(stmt.subquery())
    )

    # apply paginations
    stmt = pagination.use_on(stmt)

    _res = await ss.scalars(stmt)

    res = _res.all()
    assert total_count is not None
    return gene_sche.PaginatedResult(total=total_count, pagination=pagination, data=res)


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


async def update_tags_of_item(
    ss: SessionDep,
    item: orm.Item,
    tag_str_list: list[str],
    commit: bool = True,
    remove_prev: bool = True,
) -> orm.Item:
    """
    Update tags of an item, and return the updated item. Empty tags will be ignored

    Args

    - `remove_prev` Remove all previous tags of item. `item` must be already in database

    Note:

    - All tags string will be performed `.strip()`
    - Empty string tags will be ignored.
    """
    # remove tags duplication,
    tag_str_list = list(set(tag_str_list))

    # remove empty tags, strip operation
    tag_str_list = [t.strip() for t in tag_str_list if t != ""]

    # get tag orm instance list to be added
    tag_orm_list = await add_tags_if_not_exists(ss, tag_str_list)

    await ss.refresh(item, ["association_tags"])
    assert item is not None

    # remove previous tags
    if remove_prev:
        item = await remove_tags_of_item(ss, item)

    await item.awaitable_attrs.association_tags
    # add tags
    for t in tag_orm_list:
        item.tags.append(t)

    # commit if needed
    if commit:
        try:
            await ss.commit()
            await ss.refresh(item)
        except:
            await ss.rollback()
            raise

    return item


async def remove_tags_of_item(ss: SessionDep, item: orm.Item):
    """
    Remove all tags from item, then return updated item
    """
    await item.awaitable_attrs.association_tags
    # create shallow copy of previous tags list
    all_prev_tags_associations = list(item.association_tags)

    # select all associations with this item id
    stmt = select(orm.AssociationItemTag).where(orm.AssociationItemTag.item == item)
    res = await ss.scalars(stmt)
    asso_to_delete = res.all()
    # set this associations as deleted
    for asso in asso_to_delete:
        asso.delete()

    try:
        await ss.commit()
        await ss.refresh(item)
    except:
        await ss.rollback()
        raise

    return item


async def get_item_detailed_info(
    ss: SessionDep, item_id: int
) -> db_sche.ItemDetailedOut:
    """
    Get detailed info of an item
    """
    # get item orm
    item = await get_item_by_id(ss, item_id)
    await ss.refresh(item, ["seller", "questions"])

    # get fav count
    fav_count = await get_fav_count_of_item(ss, item)
    item.fav_count = fav_count

    return await ss.run_sync(lambda ss: db_sche.ItemDetailedOut.model_validate(item))


async def add_item(
    ss: SessionDep,
    user: CurrentUserDep,
    item: db_sche.ItemIn,
):
    """
    Add an item for a user, if tags specified, also add tags to item
    """
    # create new item orm
    try:
        item_orm = orm.Item(**item.model_dump(exclude={"tags"}))

        # add item to user
        await user.awaitable_attrs.items
        user.items.append(item_orm)

        # add tags to item
        tag_list = item.tags
        if tag_list is not None:
            item_orm = await update_tags_of_item(
                ss, item_orm, tag_list, commit=False, remove_prev=False
            )

        await ss.commit()

        # load tags of the item (because of refresh)
        await item_orm.awaitable_attrs.tags
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

    tag_str_list = info.tags
    if tag_str_list is not None:
        await update_tags_of_item(ss, item, tag_str_list)

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

    - `item_not_belongs_to_user`
    """
    # promise this is valid user
    await get_user_from_user_id(ss, user_id)

    stmt = select(orm.User).join(
        orm.User.items.and_(orm.Item.item_id == item_id).and_(
            orm.User.user_id == user_id
        )
    )

    try:
        res = await ss.scalars(stmt)
        res = res.one()
        return res
    except:
        raise exc.PermissionError(
            name="item_not_belongs_to_user",
            message=f"Item with id: {item_id} does not belongs to user with id: {user_id}",
        )


async def check_validity_to_update_item(ss: SessionDep, user: orm.User, item: orm.Item):
    """
    Check validity before updating item info by providing `user` and `item`

    Used as general entry validity checking function.

    Raises

    - `item_not_belongs_to_user`
    - `invalid_item_state`
    - `has_processing_transaction`
    """
    # allowed state
    allowed_states: Sequence[orm.ItemState] = [orm.ItemState.hide, orm.ItemState.valid]

    # check item belongs to user
    await check_item_belong_to_user(ss, item.item_id, user.user_id)

    # check item in valid states for update
    if item.state not in allowed_states:
        allowed_state_string = ", ".join(allowed_states)

        raise exc.IllegalOperationError(
            name="invalid_item_state",
            message=f"Item not in valid state for update operation. "
            f"Allowed item states: {allowed_state_string}",
        )

    # check item has no processing transaction
    trade = await ss.run_sync(lambda ss: item.processing_trade)
    if trade is not None:
        raise exc.IllegalOperationError(
            name="has_processing_transaction",
            message="Could not update an item with processing transaction",
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


async def get_tags_by_names(
    ss: SessionDep, tag_str_list: Sequence[str]
) -> Sequence[orm.Tag]:
    """
    Get a list of orm Tag instance by list of tag name str

    Raises

    - `no_result` Corresponding tag not exists
    """
    # store the retrieve orm tag instance
    orm_tag_list: list[orm.Tag] = []

    # iterate to get tag with corresponding name
    for tag_name in tag_str_list:
        # retrieve tags
        stmt = select(orm.Tag).where(orm.Tag.name == tag_name)
        tag_orm = await ss.scalar(stmt)
        # add to result list
        orm_tag_list.append(tag_orm)

    return orm_tag_list


async def add_tags_if_not_exists(ss: SessionDep, tag_str_list: Sequence[str]):
    """
    Create new tags based on a list of tag name str if the tag with the name
    not exists. Empty string tags will be ignored

    Returns

    A list of orm Tag instance corresponding to the tag string list
    """
    # get list of exists tags
    stmt = select(orm.Tag)
    res = await ss.scalars(stmt)
    exists_tags = res.all()
    exists_tags_str = [t.name for t in exists_tags]

    # add if not exists
    for tag in tag_str_list:
        # tag exists
        if tag in exists_tags_str:
            continue
        # tag is empty
        if tag == "":
            continue

        # add tag
        logger.debug(f"Adding tag with name: {tag}")
        new_tag = orm.Tag(name=tag)
        ss.add(new_tag)

    # persist change
    try:
        await ss.commit()
    except:
        await ss.rollback()
        raise

    # return orm tag list
    return await get_tags_by_names(ss, tag_str_list)
