"""
Declare models uses as util data structures in API I/O
"""

from enum import Enum
from pydantic import BaseModel, NonNegativeInt

from sqlalchemy.sql import Select

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


class TradesFilterTypeIn(Enum):
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
        cls, filters: list["TradesFilterTypeIn"]
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
    Pagination tool class that used to add pagination to select statement:

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
    size: int = 20

    # zero-index page number
    index: int

    def use_on(self, select_stmt: Select):
        offset = self.size * self.index
        limit = self.size
        return select_stmt.limit(limit).offset(offset)
