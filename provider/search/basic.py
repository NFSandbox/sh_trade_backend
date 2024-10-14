import asyncio
import re

import asyncstdlib as alib

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
from functools import cached_property, cache

from pydantic import BaseModel
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


class SearchFilterConfig:
    filter_key_value_regex = re.compile(
        r"(?P<key>[\w-]+?):(?P<value>.*?(?=\s|$))", re.VERBOSE
    )
    """
    Regex that could match a single filter key-value pair in query.
    # TODO
    """

    def __init__(self, search_query: str) -> None:
        self.search_query = search_query.strip()

    async def _extract_filters_info(self):
        pass


class Searcher:
    def __init__(self, keyword: str) -> None:
        self.keyword = keyword

    def clear_cache(self):
        """
        Clear caches of this Searcher instance.
        """
        # keyword properties
        del self.by_name_keyword
        del self.by_tag_keywords

    @alib.cached_property
    async def by_name_keyword(self):
        return self._get_by_name_keyword()

    @alib.cached_property
    async def by_tag_keywords(self):
        return await self._get_by_tag_keywords(remove_invalid=True)

    def _get_by_name_keyword(self):
        """Keyword used in by-name search"""
        return self.keyword.strip()

    async def _get_by_tag_keywords(self, remove_invalid: bool = True):
        """
        Set of tags used in by-tag search

        Args

        - `remove_invalid` Remove the tag in the set which is not a valid tag in database.
        """
        # split keyword string into tag candidates
        splited_tag_str = set([t.strip() for t in self.keyword.split(" ")])

        # check database to filter non-exists tags if needed
        if remove_invalid:
            logger.debug("remove_invalid enabled")
            async with session_manager() as ss:
                # get valid tags
                stmt = select(orm.Tag.name).where(orm.Tag.name.in_(splited_tag_str))
                valid_tag_set = set((await ss.scalars(stmt)).all())
                logger.debug(f"valid tags: {valid_tag_set}")

                # intersection update
                splited_tag_str.intersection_update(valid_tag_set)

        return splited_tag_str

    async def _get_by_name_search_result(self, ignore_processing_items: bool = True):
        """
        Search items in database by name.

        Args

        - `ignore_processing_item` Ignore the items which has a processing transaction
        """
        keyword = await self.by_name_keyword
        logger.debug(f"Using by_name keyword: {keyword}")

        stmt = (
            select(orm.Item)
            .where(orm.Item.name.like(f"%{keyword}%"))
            .where(orm.Item.state == orm.ItemState.valid)
        )

        if ignore_processing_items:
            stmt = stmt.where(orm.Item.processing_trade == None)

        logger.debug(f"by_name search stmt: \n {stmt}")

        async with session_manager() as ss:
            return (await ss.scalars(stmt)).all()
