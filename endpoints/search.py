import time
from typing import Annotated, cast, List, Sequence

from loguru import logger
from fastapi import APIRouter, Query, Depends, Request, Response, status, Body
from pydantic import BaseModel

from config import system as sys_config

from schemes import db as db_sche
from schemes import general as gene_sche
from schemes import sql as orm

from provider.user import CurrentUserDep, CurrentUserOrNoneDep
from provider import auth as auth_provider
from provider.auth import PermissionsChecker
from provider.search import Searcher

from provider.database import SessionDep
from exception import error as exc


search_router = APIRouter()


@search_router.post("/item/by_name")
async def search_items_by_name(
    q: Annotated[bool, Depends(PermissionsChecker({"search:item:by_name"}))],
    ss: SessionDep,
    keyword: str = Query(min_length=1),
    pagination: gene_sche.PaginationConfig | None = None,
):
    """
    Search items by name
    """
    searcher = Searcher(keyword, pagination=pagination)
    return await searcher.by_name_search(ss)


@search_router.post("/item/by_tags")
async def search_items_by_tags(
    q: Annotated[bool, Depends(PermissionsChecker({"search:item:by_tags"}))],
    ss: SessionDep,
    keyword: str = Query(min_length=1),
    pagination: gene_sche.PaginationConfig | None = None,
):
    """
    Search items by name
    """
    searcher = Searcher(keyword, pagination=pagination)
    return await searcher.by_tags_search(ss)
