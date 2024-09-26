from typing import Annotated, cast, List

from loguru import logger
from sqlalchemy import select, func, Column, distinct
from sqlalchemy.orm import selectinload, QueryableAttribute, aliased
from sqlalchemy.sql import and_
from sqlalchemy import exc as sqlexc

from config import system as sys_conf

from schemes import sql as orm
from schemes import auth as auth_sche
from schemes import db as db_sche

from ..database import init_session_maker, session_maker, SessionDep, try_commit
from ..user.core import get_user_contact_info_count

from exception import error as exc


async def check_item_validity_to_start_transaction(ss: SessionDep, item: orm.Item):
    """
    Check if the item have no processing transaction

    - Item is in valid state
    - Item have no processing transaction

    Raises

    - `processing_transaction_exists` (409)
    - `invalid_item` (404)
    """
    if item.state != orm.ItemState.valid:
        raise exc.NoResultError(
            name="invalid_item",
            message="This item is not in valid state for a transaction",
        )

    if await item.awaitable_attrs.processing_trade is not None:
        raise exc.DuplicatedError(
            name="processing_transaction_exists",
            message="There is already an processing transaction with this item",
        )

    return True


async def check_validity_to_start_transaction(
    ss: SessionDep, user: orm.User, item: orm.Item
):
    """
    Check the buyer and item validity of creating a new transaction between them

    Raises

    - `processing_transaction_exists` (409)
    - `invalid_item` (404)
    - `no_valid_contact_info` (404)
    - `processing_transaction_limit_exceeded` (400)
    """
    await check_item_validity_to_start_transaction(ss, item)
    await check_user_validity_to_start_transaction(ss, user)


async def check_user_validity_to_start_transaction(ss: SessionDep, user: orm.User):
    """
    Check if a user is allowed to start a new transaction, including:

    - User should not exceed max processing transaction per user limit
    - User should have at least one contact info.

    Raises

    - `no_valid_contact_info` (404)
    - `processing_transaction_limit_exceeded` (400)
    """
    # get count of user processing transaction
    if (await get_user_contact_info_count(ss, user)) == 0:
        raise exc.NoResultError(
            name="no_valid_contact_info",
            message="User has no valid contact information",
        )

    # check processing count
    # select all buys of current user, that is in processing state
    stmt = (
        select(orm.TradeRecord)
        .select_from(orm.User)
        .join(
            orm.User.buys.and_(orm.TradeRecord.state == orm.TradeState.processing).and_(
                orm.User.user_id == user.user_id
            )
        )
    )

    # all processing buys
    processing_buys = (await ss.scalars(stmt)).all()

    # if limit exceeded
    if len(processing_buys) >= sys_conf.MAX_TRANSACTION_PER_BUYER:
        raise exc.LimitExceededError(name="processing_transaction_limit_exceeded")

    return True


async def start_transaction(
    ss: SessionDep, user: orm.User, item: orm.Item, skip_check: bool = False
):
    """
    Start a transaction with given user and item, check item validity before create.

    The newly created transaction will be in the `holding` state, waiting for seller
    to accept.

    Return

    Return the newly created transaction if success

    Params

    - `skip_check` Skip item validity check

    Raises

    - `processing_transaction_exists` (409)
    """
    # check item validity
    if not skip_check:
        await check_item_validity_to_start_transaction(ss, item)

    # create new transaction
    new_transaction = orm.TradeRecord(buyer=user, item=item)

    # add to session
    ss.add(new_transaction)

    await try_commit(ss)

    return new_transaction


async def get_seller_holding_transactions(ss: SessionDep, seller: orm.User):
    """
    Get a list of transaction that waiting for acception of certain user as the seller.
    """
    # todo
    pass
