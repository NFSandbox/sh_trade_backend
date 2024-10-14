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
from provider import fav as fav_provider
from provider.user import CurrentUserDep, CurrentUserOrNoneDep

from provider.database import SessionDep
from exception import error as exc


fav_router = APIRouter()
"""API Router of favourite items related endpoints"""


@fav_router.get("", response_model=List[db_sche.ItemOut])
async def get_fav_items(ss: SessionDep, user: CurrentUserDep):
    """
    Get favourite items of current user
    """
    return await ss.run_sync(
        lambda ss: [db_sche.ItemOut.model_validate(i) for i in user.fav_items]
    )


@fav_router.post(
    "/add",
    responses=exc.openApiErrorMark(
        {409: "Favourite Item Duplicated", 400: "Maximum Fav Limit Exceeded"}
    ),
    response_model=db_sche.ItemOut,
)
async def add_fav_item(
    ss: SessionDep, user: CurrentUserDep, item_id: Annotated[int, Body(ge=1)]
):
    """
    Add an item into favourite by `item_id`, return the info of added item

    Raises

    - `fav_items_limit_exceeded` (400) (LimitExceededError)
    - `item_already_in_fav` (409) (DuplicatedError)
    """
    item = await fav_provider.add_fav_item(ss, user, item_id)
    return await ss.run_sync(lambda ss: db_sche.ItemOut.model_validate(item))


@fav_router.delete("/remove", response_model=gene_sche.BulkOpeartionInfo)
async def remove_favourite_items(
    ss: SessionDep, user: CurrentUserDep, item_id_list: List[int]
):
    """
    Remove an item from favourite by list of `item_id`, return `BulkOpeartionInfo`
    """
    return await fav_provider.remove_fav_items_of_user(ss, user, item_id_list)


@fav_router.delete("/remove_all", response_model=gene_sche.BulkOpeartionInfo)
async def remove_all_favourite_items(ss: SessionDep, user: CurrentUserDep):
    """
    Remove all fav items from user, return `BulkOpeartionInfo`
    """
    return await fav_provider.remove_fav_items_of_user(ss, user, item_id_list=None)
