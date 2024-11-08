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


@item_router.post(
    "", response_model=gene_sche.PaginatedResultOut[List[db_sche.ItemOut]]
)
async def get_items_of_user(
    ss: SessionDep,
    user: CurrentUserOrNoneDep,
    user_id: int | None = None,
    ignore_sold: bool = False,
    time_desc: bool = True,
    pagination: Annotated[
        gene_sche.PaginationConfig | None,
        Body(embed=True),
    ] = None,
):
    """
    Get items of a user by user id.

    Args

    - `user_id` Default to current user if ignored
    - `ignore_sold` Ignore all items that already been sold
    - `time_desc` If `True`, result sorted by created time desc order, else by asc order
    - `pagination` Specified the pagination config of result, could be None.

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
    res = await item_provider.get_user_items(
        ss,
        user_id,
        ignore_hide=not full_access,
        ignore_sold=ignore_sold,
        time_desc=time_desc,
        pagination=pagination,
    )

    return res


@item_router.post(
    "/add",
    responses=exc.openApiErrorMark(
        {exc.httpstatus.HTTP_406_NOT_ACCEPTABLE: "Max items-per-user limit reached"}
    ),
    response_model=db_sche.ItemOut,
)
async def add_item(
    ss: SessionDep,
    user: CurrentUserDep,
    item: db_sche.ItemIn,
):

    # get current user items count
    count = await item_provider.get_user_item_count(ss, user_id=user.user_id)
    if count >= sys_config.MAX_ITEMS_PER_USER:
        raise exc.BaseError(
            "max_items_limit_reached",
            f"There are at most {sys_config.MAX_ITEMS_PER_USER} items published at the same time per user",
            status=406,
        )

    new_item = await item_provider.add_item(ss, user, item)

    # load tags in advance
    await new_item.awaitable_attrs.tags
    return new_item


@item_router.post(
    "/update",
    response_model=db_sche.ItemOut,
    responses=exc.openApiErrorMark({403: "Item No Belong To User"}),
)
async def update_item(ss: SessionDep, user: CurrentUserDep, info: db_sche.ItemInWithId):
    """
    Update info of an item

    Raises

    - `item_not_belongs_to_user`
    - `invalid_item_state`
    - `has_processing_transaction`
    """
    # get item by id
    item = await item_provider.get_item_by_id(ss, item_id=info.item_id)

    # validity check
    await item_provider.check_validity_to_update_item(ss, user, item)

    # update item
    item_orm = await item_provider.update_item(ss, info)
    await item_orm.awaitable_attrs.association_tags
    return await ss.run_sync(lambda ss: db_sche.ItemOut.model_validate(item_orm))


@item_router.delete("/remove_all", response_model=List[gene_sche.BulkOpeartionInfo])
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


@item_router.delete(
    "/remove",
    response_model=List[gene_sche.BulkOpeartionInfo],
    responses=exc.openApiErrorMark({403: "Permission Required"}),
)
async def remove_items(ss: SessionDep, user: CurrentUserDep, item_id_list: list[int]):
    items = [await item_provider.get_item_by_id(ss, iid) for iid in item_id_list]

    # permission check, user could only delete items of themselves
    for item in items:
        # admin, skip permission check
        if await user.verify_role(ss, ["admin"]):
            break
        if item.user_id != user.user_id:
            raise exc.PermissionError(
                message="You could only delete items owned by yourself"
            )

    # cascade delete item
    return await item_provider.remove_items_cascade(ss, items)


@item_router.post(
    "/question/add",
    responses=exc.openApiErrorMark(
        {
            404: "ItemNotFound",
            403: "NoAnswerPermission",
            401: "Auth Required",
        }
    ),
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

    Note:

    - Do not pass `asker_id` field, it will be automatically set to the `user_id`
      of current user.
    """
    # if contains answer part, check permission
    if question.answer is not None:
        try:
            item = await item_provider.check_item_belong_to_user(
                ss, question.item_id, user.user_id
            )
        except exc.BaseError as e:
            raise exc.PermissionError(
                message="Current user do not have permission to answer this question"
            )

    # update question asker by current user info
    question.asker_id = user.user_id

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


@item_router.get("/questions", response_model=List[db_sche.QuestionOut])
async def get_questions_of_item(
    ss: SessionDep,
    user: CurrentUserOrNoneDep,
    item_id: int,
    time_desc: bool = True,
    unanswered_only: bool = False,
):
    """
    Get all questions related to an tiem

    Args

    - `time_desc` Order result by created time desc
    - `unanswered_only` Only return unanswered question

    No account needed for this endpoint
    """
    user_id = None
    if user is not None:
        user_id = user.user_id

    return await item_provider.get_questions_by_item_id(
        ss, item_id, user_id, time_desc, unanswered_only
    )


@item_router.post(
    "/question/answer",
    response_model=db_sche.QuestionOut,
    responses=exc.openApiErrorMark(
        {404: "No Related User", 403: "No Permission To Answer"}
    ),
)
async def answer_question(
    ss: SessionDep,
    user: CurrentUserDep,
    question_id: Annotated[int, Body()],
    answer: Annotated[str, Body()],
):
    # check if the user the owner of the question related item
    await item_provider.check_question_belongs_to_user(ss, question_id, user.user_id)

    return await item_provider.answer_question(ss, question_id, answer)


@item_router.delete(
    "/question/remove",
    response_model=gene_sche.BulkOpeartionInfo,
    responses=exc.openApiErrorMark(
        {404: "No Related User", 403: "No Permission To Answer"}
    ),
)
async def delete_question(ss: SessionDep, user: CurrentUserDep, question_id: int):
    # only related user could delete the question
    if not await user.verify_role(ss, ["admin"]):
        await item_provider.check_question_belongs_to_user(
            ss, question_id, user.user_id
        )

    return await item_provider.remove_questions(
        ss, [await item_provider.get_question_by_id(ss, question_id)]
    )
