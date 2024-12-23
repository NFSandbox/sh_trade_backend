import asyncio
import re

from collections.abc import Collection

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

from sqlalchemy import select, func, Column, distinct, union_all, union, Select
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


class SearchFilterError(exc.BaseError):
    """
    Raised when failed to apply filter config to the search statement.
    """

    def __init__(
        self,
        name: str = "filter_apply_error",
        message: str = "Failed to apply a search filter.",
        key: str | None = None,
        filter_values: list[str] | None = None,
        value_err_msg: str | None = None,
        status: int = 403,
    ) -> None:
        """Create a SearchFilterError

        Args:
            key: The name of the key.
            value_err_msg: The error message indicates how the value of this filter
                went wrong.
        """
        if key is not None:
            message += f" Filter key: {key}."

        if filter_values is not None:
            message += f" Filter values: {filter_values}."

        if value_err_msg is not None:
            message += f" {value_err_msg}."

        super().__init__(name, message, status)


class SearchFilterConfig:
    filter_key_value_regex = re.compile(
        r"(?P<key>[\w-]+?):(?P<value>.*?(?=\s|$))", re.VERBOSE
    )
    """
    Regex that could match a single filter key-value pair in query.
    """

    def __init__(self, search_query: str) -> None:

        self.search_query = search_query.strip()
        """
        Original search query
        """

        self.filter_removed_query: str
        """
        Query string with all valid filter pattern removed.
        """

        self.filters_info_dict: dict[str, list[str]] = {}
        """
        Dict that store all extracted tags info.
        Need to call _extract_filters_info() to generate.
        """

        self._extract_filters_info()

    def _extract_filters_info(self):
        """
        Extract tags info from query string, also generated a new query with
        filter removed.

        Returns:
            dict[str, list[str]] The tags info dict.
        """
        self.filters_info_dict = {}

        # match tags
        match_obj = self.filter_key_value_regex.finditer(self.search_query)

        for m in match_obj:
            # extract k-v
            key = m.group("key")
            value = m.group("value")

            # add to info dict
            self.filters_info_dict.setdefault(key, []).append(value)

        self.filter_removed_query = self.filter_key_value_regex.sub(
            "", self.search_query
        )

        return self.filters_info_dict

    def apply_filter[
        T: Select
    ](self, stmt: T, excluded_filters: Collection[str] | None = None) -> T:
        """
        Apply filter to the search statement.

        Args:
            excluded_filters: List of string represents the filters to ignore.
        """

        for key, value in self.filters_info_dict.items():

            if (excluded_filters is not None) and (key in excluded_filters):
                continue

            if key == "recent":
                stmt = self._recent_filter_applyer(key, value, stmt)
            elif key == "tag":
                stmt = self._tags_filter_applyer(key, value, stmt)

        return stmt

    def _recent_filter_applyer[
        T: Select
    ](self, key: str, value: list[str], stmt: T) -> T:

        # ensure only one recent specified
        if len(value) > 1:
            raise SearchFilterError(
                key=key,
                filter_values=value,
                value_err_msg="Recent filter could only be specified once.",
            )

        # get recent day number
        try:
            recent_day = int(value[0])
            if recent_day < 0:
                raise ValueError
        except:
            raise SearchFilterError(
                key=key,
                filter_values=value,
                value_err_msg="Value of recent filter must be a valid positive number.",
            )

        # calculate the time stamp limit
        timestamp_limit = orm.get_current_timestamp_ms() - recent_day * 24 * 3600 * 1000

        return stmt.where(orm.Item.created_time >= timestamp_limit)

    def _tags_filter_applyer[T: Select](self, key: str, value: list[str], stmt: T) -> T:
        new_stmt = stmt

        for v in value:
            new_stmt = new_stmt.where(
                orm.Item.association_tags.any(orm.AssociationItemTag.tag_name == v)  # type: ignore
            )

        return new_stmt


class SearchResultOut(BaseModel):
    filters: dict[str, list[str]]
    query: str
    filter_removed_query: str
    total: int
    pagination: gene_sche.PaginationConfig
    results: list[db_sche.ItemOut]


class Searcher:
    """
    Class used when perform search in database.
    """

    def __init__(
        self, query: str, pagination: gene_sche.PaginationConfig | None = None
    ) -> None:
        self.query = query
        self.pagination = pagination or gene_sche.PaginationConfig()
        self.filter_config = SearchFilterConfig(query)
        self.filter_removed_query = self.filter_config.filter_removed_query

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
        return self.filter_removed_query.strip()

    async def _get_by_tag_keywords(self, remove_invalid: bool = True):
        """
        Set of tags used in by-tag search

        Args

        - `remove_invalid` Remove the tag in the set which is not a valid tag in database.
        """
        # split keyword string into tag candidates
        splited_tag_str = set([t.strip() for t in self.filter_removed_query.split(" ")])

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

    async def _get_by_name_search_stmt(self):
        """
        Generate basic select statements for by-name search
        based on the search query.
        """
        keyword = await self.by_name_keyword
        logger.debug(f"Using by_name keyword: {keyword}")

        stmt = (
            select(orm.Item)
            .where(orm.Item.name.like(f"%{keyword}%"))
            .where(orm.Item.state == orm.ItemState.valid)
        )

        logger.debug(f"by_name search stmt: \n {stmt}")

        return stmt

        async with session_manager() as ss:
            return (await ss.scalars(stmt)).all()

    async def _get_by_tags_search_stmt(self):
        """
        Generate basic select statements for by-tag search.
        """

        tags = await self.by_tag_keywords

        stmt = (
            select(orm.Item)
            .join(orm.Item.association_tags)
            .join(orm.AssociationItemTag.tag)
            # limited to specified tags
            .where(orm.Tag.name.in_(tags))
            # grouped and ordered by the appearance times of the tags
            .group_by(orm.Item.item_id)
            .order_by(func.count(orm.Item.item_id).desc())
        )

        return stmt

    async def _get_result_count(self, ss: SessionDep, stmt: Select) -> int:
        """
        Get the number of selected rows of a statements.
        """
        return await ss.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    async def _get_results[
        T: Select
    ](
        self,
        ss: SessionDep,
        original_stmt: T,
        excluded_filters: Collection[str] | None = None,
    ):
        """
        Get results based on original stmt.

        Generally, original stmt should be the stmt generated by by-tag or by-name
        stmt generator

        Returns:
            tuple[int, Result] The first number represents the total results in database.
                The result is a list of item result with pagination applied.
        """

        # apply filter to stmt
        stmt_with_filter = self.filter_config.apply_filter(
            original_stmt, excluded_filters=excluded_filters
        )

        # get total result of this search
        total = await self._get_result_count(ss, stmt_with_filter)

        # apply pagination
        stmt_with_pagination = self.pagination.use_on(stmt_with_filter)

        # apply tag eager loading
        stmt_with_pagination = stmt_with_pagination.options(
            selectinload(orm.Item.association_tags).options(
                selectinload(orm.AssociationItemTag.tag)
            )
        )

        # query final result
        res = (await ss.scalars(stmt_with_pagination)).all()

        def get_result(ss):
            return SearchResultOut(
                filters=self.filter_config.filters_info_dict,
                query=self.query,
                filter_removed_query=self.filter_removed_query,
                total=total,
                pagination=self.pagination,
                results=[db_sche.ItemOut.model_validate(i) for i in res],
            )

        # construct result
        return await ss.run_sync(get_result)

    async def by_name_search(self, ss: SessionDep):
        stmt = await self._get_by_name_search_stmt()
        return await self._get_results(ss, stmt)

    async def by_tags_search(self, ss: SessionDep):
        stmt = await self._get_by_tags_search_stmt()
        return await self._get_results(ss, stmt, excluded_filters=["tag"])
