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

from .database import init_session_maker, session_maker, SessionDep, try_commit
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
    load_tags: bool = True,
):
    """
    Get selling items of a user by user id
    """
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


async def update_tags_of_item(
    ss: SessionDep,
    item: orm.Item,
    tag_str_list: list[str],
    commit: bool = True,
    remove_prev: bool = True,
) -> orm.Item:
    """
    Update tags of an item, and return the updated item

    Args

    - `remove_prev` Remove all previous tags of item. `item` must be already in database

    Note

    - All previous tags will be removed
    """
    # remove tags duplication,
    tag_str_list = list(set(tag_str_list))

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
        await ss.commit()
        await ss.refresh(item_orm)

        # add tags to item
        tag_list = item.tags
        if tag_list is not None:
            item_orm = await update_tags_of_item(
                ss, item_orm, tag_list, commit=False, remove_prev=False
            )

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

    - `item_belonging_test_failed` 403
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
    q_count = gene_sche.BulkOpeartionInfo(operation="Delete questions")

    for q in questions:
        if q.deleted_at is None:
            q_count.inc()
            q.delete()

    if commit:
        await try_commit(ss)

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


async def get_cascade_association_items_tags_from_items(
    ss: SessionDep, items: Sequence[orm.Item]
):
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
) -> List[gene_sche.BulkOpeartionInfo]:
    """
    Soft delete a list of items, with cascade delete of all relavant data

    Args

    - `items` The items need to be cascade delete
    - `constraint` If `True`, raise error if has cascade items

    Cascade

    - `Question` All question related to these items
    - `AssociationItemTag` All tags associations (todo)

    Raises

    - `cascade_constraint`
    """
    # record the effective delete count of all entities
    i_count = gene_sche.BulkOpeartionInfo(operation="Delete items")

    try:
        # delete question cascade of item
        questions = await get_cascade_questions_from_items(ss, items)
        # raise error if constraint
        if constraint and len(questions) > 0:
            raise exc.CascadeConstraintError(
                "Could not remove items with active questions"
            )
        q_count = await remove_questions(ss, questions, commit=False)

        # remove tag associations
        associations = await get_cascade_association_items_tags_from_items(ss, items)
        t_count = await remove_associations_items_tags(ss, associations, commit=False)

        # delete items itself
        for i in items:
            if i.deleted_at == None:
                i_count.inc()
            i.delete()

        await ss.commit()

        # return info
        return [i_count, q_count, t_count]
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
    not exists

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
        if tag in exists_tags_str:
            continue
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
