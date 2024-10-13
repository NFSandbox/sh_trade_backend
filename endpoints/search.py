import time
from typing import Annotated, cast, List, Sequence

from loguru import logger
from fastapi import APIRouter, Query, Depends, Request, Response, status, Body
from pydantic import BaseModel

from config import system as sys_config

from schemes import db as db_sche
from schemes import general as gene_sche
from schemes import sql as orm

from provider import user as user_provider
from provider import database as db_provider
from provider.database import try_commit
from provider import item as item_provider
from provider import fav as fav_provider
from provider.user import CurrentUserDep, CurrentUserOrNoneDep
from provider import auth as auth_provider
from provider.auth import PermissionsChecker

from provider.database import SessionDep
from exception import error as exc


search_router = APIRouter()


@search_router.get("/item")
async def search_items(
    keyword: str = Query(min_length=1),
    by_name: bool = True,
    by_tag: bool = True,
):
    """
    Search items
    """
    # keyword used in by-name search
    name_search_keyword = keyword
    # tags used in by_tag search
    tag_search_keywords = [t.strip() for t in keyword.split(" ")]

    # TODO
