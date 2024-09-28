from typing import Annotated, cast, List, Sequence

from loguru import logger
from sqlalchemy import select, func, Column, distinct
from sqlalchemy.orm import selectinload, QueryableAttribute, aliased
from sqlalchemy.sql import and_
from sqlalchemy import exc as sqlexc

from fastapi import Depends, Request

from config import auth as auth_conf

from schemes import sql as orm
from schemes import auth as auth_sche
from schemes import db as db_sche
from schemes import general as gene_sche

from ..database import init_session_maker, session_maker, SessionDep, try_commit

from exception import error as exc

from ..database import init_session_maker, add_eager_load_to_stmt


async def get_cascade_trade_from_buyers(ss: SessionDep, buyers: Sequence[orm.User]):
    """
    Get all trades by a list of buyers
    """
    buyer_id_list = [b.user_id for b in buyers]

    stmt = (
        select(orm.TradeRecord)
        .select_from(orm.User)
        .join(orm.User.buys.and_(orm.User.user_id.in_(buyer_id_list)))
    )

    return (await ss.scalars(stmt)).all()


async def remove_trades_cascade(
    ss: SessionDep, trades: Sequence[orm.TradeRecord], commit: bool = True
) -> list[gene_sche.BulkOpeartionInfo]:
    """
    Remove a list of trade records
    """
    t_total = gene_sche.BulkOpeartionInfo(operation="Remove trades")

    for t in trades:
        t.delete()
        t_total.inc()

    if commit:
        await try_commit(ss)

    return [t_total]
