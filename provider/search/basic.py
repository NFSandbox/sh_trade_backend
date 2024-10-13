import asyncio

from typing import (
    Annotated,
    cast,
    List,
    Sequence,
    Callable,
    Awaitable,
    Any,
    Literal,
    Union,
    Coroutine,
    TypeVar,
)

from dataclasses import dataclass
from functools import cached_property

from pydantic import BaseModel

from inspect import isawaitable

from asyncer import asyncify
from asyncio import iscoroutine

from loguru import logger
from sqlalchemy import select, func, Column, distinct, union_all, union
from sqlalchemy.orm import selectinload, QueryableAttribute, aliased
from sqlalchemy.sql import and_, or_
from sqlalchemy import exc as sqlexc
from sqlalchemy.ext.asyncio import AsyncSession

from config import system as sys_conf

from schemes import sql as orm
from schemes import auth as auth_sche
from schemes import db as db_sche
from schemes import general as gene_sche

from exception import error as exc

from tools.callback_manager import CallbackManager, CallbackInterrupted

# use peer providers
from ..database import (
    init_session_maker,
    session_maker,
    session_manager,
    SessionDep,
    try_commit,
)
from ..user.core import get_user_contact_info_count
from ..auth import check_user_permission


class Searcher:
    def __init__(self, keyword: str) -> None:
        self.keyword = keyword

    @cached_property
    def by_name_keyword(self):
        """Keyword used in by-name search"""
        return self.keyword.strip()

    @cached_property
    async def by_tag_keywords(self):
        """Set of tags used in by-tag search"""
        async with session_manager() as ss:
            pass
        return set([t.strip() for t in self.keyword.split(" ")])
