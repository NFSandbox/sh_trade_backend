from typing import Annotated, cast, List, Sequence

from loguru import logger
from sqlalchemy import select, func, Column, distinct
from sqlalchemy.orm import selectinload, QueryableAttribute, aliased
from sqlalchemy.sql import and_, or_
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


async def check_buyer_is_not_owner_of_item(
    ss: SessionDep, buyer: orm.User, item: orm.Item
):
    """
    Check that buyer is not the owner of the target item himself

    Raises

    - `identical_seller_buyer` (409)
    """
    # get seller of item
    seller: orm.User = await ss.run_sync(lambda ss: item.seller)

    # raise
    if seller.user_id == buyer.user_id:
        raise exc.ConflictError(
            name="identical_seller_buyer",
            message="The seller and buyer of an item could not be the same user",
        )


async def check_no_existing_processing_transaction(
    ss: SessionDep, buyer: orm.User, item: orm.Item
):
    """
    Check if the buyer already have a pending transaction with the item

    Use case

    - Buyer may already start a transaction with this item, and the transaction
      is waiting for seller's acceptance.
    - Buyer may already have a _processing_ transaction with thie item.

    Raises

    - `duplicated_transaction` (409)
    """

    stmt = (
        select(func.count())
        .select_from(orm.TradeRecord)
        .join(orm.TradeRecord.buyer)
        .where(
            and_(
                # determine the item we need to check
                orm.TradeRecord.item_id == item.item_id,
                # check if any transaction in:
                # - pending
                # - processing
                or_(
                    orm.TradeRecord.state == orm.TradeState.processing,
                    orm.TradeRecord.state == orm.TradeState.pending,
                ),
                # actually duplicated, relation will handle this
                orm.TradeRecord.buyer_id == buyer.user_id,
            )
        )
    )

    # check if there's duplictation
    dup_transactions = await ss.scalar(stmt)
    # there should be a return result, which is the count of duplicated transaction
    assert dup_transactions is not None

    # raise if duplicated
    if dup_transactions > 0:
        raise exc.DuplicatedError(
            name="duplicated_transaction",
            message="There is already a transaction with this item and buyer",
        )


async def check_validity_to_start_transaction(
    ss: SessionDep, user: orm.User, item: orm.Item
):
    """
    Check the buyer and item validity of creating a new transaction between them.

    This function act as a general inclusive function to check several validities
    before starting a transaction. The code should promise all condition will be
    satisfied and it's safe to start a transaction if this function has passed.

    Raises

    - `processing_transaction_exists` (409)
    - `duplicated_transaction` (409)
    - `identical_seller_buyer` (409)
    - `invalid_item` (404)
    - `no_valid_contact_info` (404)
    - `processing_transaction_limit_exceeded` (400)

    For more info about validity check, check out
    [Project Wiki - Transaction Design](https://github.com/NFSandbox/sh_trade_backend/wiki/Transaction-Design)
    """
    await check_item_validity_to_start_transaction(ss, item)
    await check_user_validity_to_start_transaction(ss, user)
    await check_buyer_is_not_owner_of_item(ss, user, item)
    await check_no_existing_processing_transaction(ss, user, item)


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
    to accept. (The default behaviour is controlled by ORM class definition)

    Return

    Return the newly created transaction if success

    Params

    - `skip_check` Skip item validity check

    Raises

    - `processing_transaction_exists` (409) Item already have a processing transaction
    - `duplicated_transaction` (409) User already have a valid transaction with this item
    - `identical_seller_buyer` (409)
    - `invalid_item` (404)
    - `no_valid_contact_info` (404)
    - `processing_transaction_limit_exceeded` (400)

    All validity checking is handled in `check_validity_to_start_transaction()`
    """
    # check item validity
    if not skip_check:
        await check_validity_to_start_transaction(ss, user, item)

    # create new transaction
    new_transaction = orm.TradeRecord(buyer=user, item=item)

    # add to session
    ss.add(new_transaction)

    await try_commit(ss)

    return new_transaction


async def get_transactions(
    ss: SessionDep,
    user: orm.User,
    states: Sequence[orm.TradeState],
):
    """
    Get related transactions of a user
    """
    # todo

    # get all transaction of a certain user with certain states
    stmt = select(orm.TradeRecord).where(
        and_(
            orm.TradeRecord.buyer_id == user.user_id,
            orm.TradeRecord.state.in_(states),
        )
    )

    trade_list = (await ss.scalars(stmt)).all()

    return trade_list
