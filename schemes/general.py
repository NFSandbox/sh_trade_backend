"""
Declare models uses as util data structures in API I/O
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Collection, Annotated, Any, Dict, List, Sequence, cast
from dataclasses import dataclass

from pydantic import BaseModel, NonNegativeInt, PositiveInt

from sqlalchemy.sql import Select
from sqlalchemy.ext.asyncio import AsyncSession

from .sql import TradeState


class BackendInfoOut(BaseModel):
    version: str
    on_cloud: bool


class BulkOpeartionInfo(BaseModel):
    """
    Pydantic schema used when backend need to return the result of bulk operation,
    for example Delete All Items"""

    success: bool = True
    operation: str | None = None
    total: NonNegativeInt = 0

    def inc(self, delta: int = 1):
        self.total += delta


class TradesFilterTypeIn(str, Enum):
    """
    Model used to specify the filter condition for trades
    """

    pending = "pending"
    processing = "processing"
    success = "success"
    cancelled = "cancelled"
    active = "active"
    inactive = "inactive"

    def to_trade_states(self) -> list[TradeState]:
        """
        Convert enum instance to `orm.TradeState` enum instance.

        If you are converting a list of instance, consider using
        `bulk_to_trade_states()`
        """
        match self:
            case TradesFilterTypeIn.pending:
                return [TradeState.pending]

            case TradesFilterTypeIn.processing:
                return [TradeState.processing]

            case TradesFilterTypeIn.success:
                return [TradeState.success]

            case TradesFilterTypeIn.cancelled:
                return [TradeState.cancelled]

            case TradesFilterTypeIn.active:
                return [TradeState.pending, TradeState.processing]
            case TradesFilterTypeIn.inactive:
                return [TradeState.success, TradeState.cancelled]

    @classmethod
    def bulk_to_trade_states(
        cls, filters: Collection["TradesFilterTypeIn"]
    ) -> list[TradeState]:
        """
        Convert a list of `TradesFilterTypeIn` to a list of `TradeState`
        """
        target_list: list[TradeState] = []

        # convert each filter type to orm enum
        for filter in filters:
            target_list.extend(filter.to_trade_states())

        # remove duplicates
        target_list = list(set(target_list))

        return target_list


class PaginationConfig(BaseModel):
    """
    Pagination tool class that used to add pagination to select statement

    Fields

    - `size` Specify how many rows in a page
    - `index` Specify the page number, zero-indexed

    Usages

        stmt : Select
        pagi_conf = PaginationConfig(size=..., limit=...)
        stmt = pagi_conf.use_on(stmt)

    Also since this class is extend from `pydantic.BaseModel`, so it can be used as a dependency of
    FastAPI method:

        @router.get('/test')
        def test_endpoint(pagi_conf : PaginationConfig):
            pass
    """

    # how many rows contains in a page
    size: Annotated[int, PositiveInt] = 20

    # zero-index page number
    index: Annotated[int, NonNegativeInt] = 0

    def use_on[T: Select](self, select_stmt: T) -> T:
        """
        Apply this pagination config to a statement object, then return a new select

        Usages:

            stmt: Select
            config: PaginationConfig
            stmt = config.use_on(stmt)

        """
        offset = self.size * self.index
        limit = self.size
        return select_stmt.limit(limit).offset(offset)


class PaginatedResult[DType: Any]:
    def __init__(self, total: int, pagination: PaginationConfig, data: DType) -> None:
        self.total = total
        self.pagination = pagination
        self.data = data


class PaginatedResultOut[DType: Sequence[BaseModel] | List[BaseModel] | BaseModel](
    BaseModel
):
    total: int
    pagination: PaginationConfig
    data: DType

    class Config:
        from_attributes = True


async def validate_result[ClsType](ss: AsyncSession, data, cls: ClsType):
    """
    Automatically validate the result in an SQLAlchemy sync session.

    - `ss` The session used to execute `run_sync`
    - `data` The data to be validated. If its a ORM class instance, then this instance must
      be bound to the received `ss`, otherwise will cause error
    - `cls` The output type of the data, must inherited from Pydantic `BaseModel`

    Note:

    - If the `data` is ORM
    """
    # check attributes
    if not hasattr(cls, "model_validate"):
        raise Exception(
            "Could only validated to type which has 'model_validate' method"
        )

    # validate
    res: ClsType = await ss.run_sync(lambda x: cls.model_validate(data, from_attributes=True))  # type: ignore

    # return
    return res
