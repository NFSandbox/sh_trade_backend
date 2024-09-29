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

    Checks

    - Buyer may already start a transaction with this item, and the transaction
      is waiting for seller's acceptance.
    - Buyer may already have a _processing_ transaction with this item.

    Note

    This function will not check if the item has any other processing transactions.
    For that purpose, use `check_item_validity_to_start_transaction()`

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


async def check_validity_to_accept_transaction(
    ss: SessionDep, user: orm.User, trade: orm.TradeRecord
):
    """
    Check if a user could accept a transaction

    Checks

    - User is the seller of the item of the transaction
    - Item validity to start transaction
    - Transaction is in pending state

    Raises

    - `not_seller` (406)
    - `transaction_not_pending` (406)
    - `processing_transaction_exists` (409)
    - `invalid_item` (404)
    """
    # ensure user is the seller
    seller_id = await ss.run_sync(lambda ss: trade.item.seller.user_id)
    if user.user_id != seller_id:
        raise exc.IllegalOperationError(
            name="not_seller",
            message="Only the seller of the item could accept the transaction",
        )

    # item validity
    await check_item_validity_to_start_transaction(
        ss, await ss.run_sync(lambda ss: trade.item)
    )

    # ensure transaction in pending state
    if trade.state != orm.TradeState.pending:
        raise exc.IllegalOperationError(
            name="transaction_not_pending",
            message="Only transactions in holding state could be accepted",
        )


async def accpet_transaction(ss: SessionDep, trade: orm.TradeRecord):
    """
    Accept a transaction, change its state to `processing`
    """
    # ensure transaction in pending state
    if trade.state != orm.TradeState.pending:
        raise exc.IllegalOperationError(
            name="transaction_not_pending",
            message="Only transactions in pending state could be accepted",
        )

    # update state and accept time
    trade.state = orm.TradeState.processing
    trade.accepted_time = orm.get_current_timestamp_ms()

    await try_commit(ss)

    return trade


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
    states: Sequence[orm.TradeState] | None,
):
    """
    Get related transactions of a user

    Args

    - `states` Filter result using the list of state. If `None`, no filter will be applied.
    """
    # get all transaction of a certain user with certain states
    stmt = (
        select(orm.TradeRecord)
        .join(orm.TradeRecord.item)
        .join(orm.Item.seller)
        .where(
            or_(
                # this user is buyer
                orm.TradeRecord.buyer_id == user.user_id,
                # this user is seller
                orm.User.user_id == user.user_id,
            )
        )
    )

    # apply filters if exists
    if states is not None:
        stmt = stmt.where(orm.TradeRecord.state.in_(states))

    trade_list = (await ss.scalars(stmt)).all()

    return trade_list


async def determine_cancel_reason(
    ss: SessionDep,
    user: orm.User,
    trade: orm.TradeRecord,
    raise_if_uncancellable: bool = False,
) -> orm.TradeCancelReason:
    """
    Determine the cancel reason based on `user` and `trade` info.

    Return `orm.TradeCancelReason` if success, else raise `RuntimeError`

    This function could also be used for cancellation valitity checking,
    for more info, check out `raise_if_uncancellable` parameter.

    Args

    - `raise_if_uncancellable` If `True`, will raise if this cancellation is
      not allowed.

    Possible Reasons

    - `seller_rejected` In pending state, user is seller.
    - `cancelled_by_buyer` In processing state, user is buyer.
    - `cancelled_by_seller` In processing state, user is seller.

    Reason Determination Process:

    - If an explicit not None `cancel_reason` received, use it
    - Else, try auto-determine reason based on received `user`, and use it if
      successfully auto-determined
    - Else, set cancel reason to `None`

    Raises

    - `RuntimeError` Could not determine cancel reason
    - `IllegalOperationError` If `raise_if_uncancellable` is `True` and
      cancellation is not allowed
    """
    # first determine if user is seller / buyer
    seller = await ss.run_sync(lambda ss: trade.item.seller)
    user_is_seller = user.user_id == seller.user_id
    user_is_buyer = trade.buyer_id == user.user_id

    # cancellation validity check if necessary
    if raise_if_uncancellable and trade.confirmed_time is not None:
        raise exc.IllegalOperationError(
            name="could_not_cancel_confirmed_transaction",
            message="Transaction confirmed by seller could not be cancelled",
        )

    if trade.state == orm.TradeState.pending and user_is_seller:
        return orm.TradeCancelReason.seller_rejected

    if trade.state == orm.TradeState.pending and user_is_buyer:
        return orm.TradeCancelReason.cancelled_by_buyer

    if trade.state == orm.TradeState.processing:
        if user_is_seller:
            return orm.TradeCancelReason.cancelled_by_seller
        if user_is_buyer:
            return orm.TradeCancelReason.cancelled_by_buyer

    raise RuntimeError(
        "Could not auto-determine cancel reason: "
        f"User with user_id: {user.user_id}, item with item_id: {trade.item_id}"
    )


async def cancel_transaction(
    ss: SessionDep,
    user: orm.User,
    trade: orm.TradeRecord,
    cancel_reason: orm.TradeCancelReason | None = None,
    commit: bool = True,
):
    """
    Cancel a `transaction` on behalf of `user`

    Note:
    - The `user` args is not used for any validity check, it should only be
      used to auto-generate Cancel Reason.

    In normal cases, it's enough to pass `user` args and let this function
    auto-determine the reason
    """
    # try auto-determine cancel reason if not specify
    if cancel_reason is None:
        try:
            cancel_reason = await determine_cancel_reason(ss, user, trade, False)
        except RuntimeError:
            pass

    # update trade states
    trade.state = orm.TradeState.cancelled
    # update cancel reason if exists
    if cancel_reason is not None:
        trade.cancel_reason = cancel_reason

    # commit and return
    if commit:
        await try_commit(ss)

    # todo
    # add endpoints function that exploit this function
    # testing
    return trade
