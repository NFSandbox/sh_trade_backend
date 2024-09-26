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
