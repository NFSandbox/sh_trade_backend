import time
from typing import Annotated, cast, List

from loguru import logger
from fastapi import APIRouter, Query, Depends, Request, Response, status, Body

from config import system as sys_config

from schemes import db as db_sche
from schemes import general as gene_sche
from schemes import sql as orm

from provider import user as user_provider
from provider import database as db_provider
from provider import item as item_provider
from provider.user import CurrentUserDep, CurrentUserOrNoneDep

from provider.database import SessionDep
from exception import error as exc


item_router = APIRouter()


@item_router.get("", response_model=List[db_sche.ItemOut])
async def get_user_items(
    ss: SessionDep,
    user: CurrentUserOrNoneDep,
    user_id: int | None = None,
    ignore_sold: bool = False,
    time_desc: bool = True,
):
    """
    Get items of a user by user id.

    Args

    - `user_id` Default to current user if ignored
    - `ignore_sold` Ignore all items that already been sold
    - `time_desc` If `True`, result sorted by created time desc order, else by asc order

    Notes:

    - Hidden items will only appeared in the result if you are the owner of those items
    """
    # validate user id
    if user_id is None:
        if user is None:
            raise exc.ParamError(
                param_name="user_id",
                message="user_id should be specified when no active account is signed in",
            )
        user_id = user.user_id

    full_access: bool = False
    # check permission level
    if user is not None and user.user_id == user_id:
        full_access = True

    # retrieve info
    return await item_provider.get_user_items(
        ss,
        user_id,
        ignore_hide=not full_access,
        ignore_sold=ignore_sold,
        time_desc=time_desc,
    )


@item_router.post(
    "/add",
    responses=exc.openApiErrorMark(
        {exc.httpstatus.HTTP_406_NOT_ACCEPTABLE: "Max items-per-user limit reached"}
    ),
    response_model=db_sche.ItemOut,
)
async def add_item(ss: SessionDep, item: db_sche.ItemIn, user: CurrentUserDep):

    # get current user items count
    count = await item_provider.get_user_item_count(ss, user_id=user.user_id)
    if count >= sys_config.MAX_ITEMS_PER_USER:
        raise exc.BaseError(
            "max_items_limit_reached",
            f"There are at most {sys_config.MAX_ITEMS_PER_USER} items published at the same time per user",
            status=406,
        )

    new_item = await item_provider.add_item(ss, user, item)

    return new_item


@item_router.delete("/remove_all", response_model=List[gene_sche.BlukOpeartionInfo])
async def remove_all_items(ss: SessionDep, user: CurrentUserDep):
    """
    Remove all items of current user

    This will also remove all questions related to this item
    """
    # remove all items belongs to this user
    await user.awaitable_attrs.items

    bulk_res = await item_provider.remove_items_cascade(ss, user.items)

    try:
        await ss.commit()
        return bulk_res
    except:
        await ss.rollback()
        raise


@item_router.post(
    "/question/add",
    responses=exc.openApiErrorMark({404: "ItemNotFound", 403: "NoAnswerPermission"}),
    response_model=db_sche.QuestionOut,
    response_model_exclude_none=True,
)
async def add_question(
    ss: SessionDep,
    user: CurrentUserDep,
    question: db_sche.QuestionIn,
):
    """
    Add a question to an item
    """
    # if contains answer part, check permission
    if question.answer is not None:
        try:
            item = await item_provider.item_belong_to_user(
                ss, question.item_id, user.user_id
            )
        except exc.BaseError as e:
            raise exc.PermissionError(
                message="Current user do not have permission to answer this question"
            )

    # get item
    item = await item_provider.get_item_by_id(ss, question.item_id)

    # create new question orm
    question_orm = orm.Question(**question.model_dump())

    # add question
    try:
        await item.awaitable_attrs.questions
        item.questions.append(question_orm)

        await ss.commit()
        await ss.refresh(question_orm)

        return question_orm
    except:
        await ss.rollback()
        raise


async def answer_question(ss: SessionDep, question_id: int, answer: str):
    # todo
    pass


async def delete_question(ss: SessionDep, question_id: int):
    pass
