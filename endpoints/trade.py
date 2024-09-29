import time
from typing import Annotated, cast, List, Collection

from loguru import logger
from fastapi import APIRouter, Query, Depends, Request, Response, status, Body
from pydantic import BaseModel
from config import system as sys_config

from schemes import db as db_sche
from schemes import general as gene_sche
from schemes import sql as orm

from provider import user as user_provider
from provider import database as db_provider
from provider import item as item_provider
from provider import trade as trade_provider
from provider.user import CurrentUserDep, CurrentUserOrNoneDep

from provider.database import SessionDep
from exception import error as exc

trade_router = APIRouter()


@trade_router.post(
    "/start",
    responses=exc.openApiErrorMark(
        {
            404: "Invalid Item Or ContactInfo",
            400: "Maximum Transaction Limit Exceeded",
            409: "Item Already Has Processing Transaction",
        }
    ),
    response_model=db_sche.TradeRecordOut,
    response_model_exclude_none=True,
)
async def start_transaction(
    ss: SessionDep, user: CurrentUserDep, item_id: Annotated[int, Body(embed=True)]
):
    """
    Start a new transaction as a buyer by providing the item's `item_id`

    Raises

    - `processing_transaction_exists` (409)
    - `invalid_item` (404)
    - `no_valid_contact_info` (404)
    - `processing_transaction_limit_exceeded` (400)
    """
    # get item
    item = await item_provider.get_item_by_id(ss, item_id)

    # check validity
    await trade_provider.check_validity_to_start_transaction(ss, user, item)

    # start transaction
    new_transaction = await trade_provider.start_transaction(
        ss, user, item, skip_check=True
    )

    return await ss.run_sync(
        lambda _: db_sche.TradeRecordOut.model_validate(new_transaction)
    )


class GetTransactionsFilters(BaseModel):
    states: list[gene_sche.TradesFilterTypeIn]


@trade_router.get(
    "/get",
    response_model=list[db_sche.TradeRecordOut],
    response_model_exclude_none=True,
)
async def get_transactions(
    ss: SessionDep,
    user: CurrentUserDep,
    pagination: gene_sche.PaginationConfig | None = None,
    filters: GetTransactionsFilters | None = None,
):
    """
    Get transactions related to current user

    Args

    - `filter` If none, return all transactions related to current user.
      Else, only return the transactions satisfy the states that `filter`
      refers to. For more info, check out `TradesFilterTypeIn` model.

    E.g.:

    If passed `filter=["processing", "cancelled"]`, then only transactions
    with this two type will be returned. You could also use `"active"` and
    `"inactive"` specifier specially with this endpoint parameters.
    """
    # convert filter type to orm type
    if filters is None:
        allowed_states = None
    else:
        allowed_states = gene_sche.TradesFilterTypeIn.bulk_to_trade_states(
            filters.states
        )

    transactions = await trade_provider.get_transactions(ss, user, allowed_states)

    def to_pydantic_transactions(ss):
        out_list = [db_sche.TradeRecordOut.model_validate(t) for t in transactions]
        return out_list

    return await ss.run_sync(to_pydantic_transactions)
