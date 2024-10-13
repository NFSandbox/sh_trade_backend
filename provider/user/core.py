from typing import Annotated, cast, List, Sequence

from loguru import logger
from sqlalchemy import select, func, Column, distinct
from sqlalchemy.orm import selectinload, QueryableAttribute, aliased
from sqlalchemy.sql import and_
from sqlalchemy import exc as sqlexc

from supertokens_python.asyncio import delete_user

from fastapi import Depends, Request

from supertokens_python.recipe.session.framework.fastapi import verify_session
from supertokens_python.recipe.session import SessionContainer

from config import auth as auth_conf

from schemes import sql as orm
from schemes import auth as auth_sche
from schemes import db as db_sche
from schemes import general as gene_sche

from ..database import init_session_maker, session_maker, SessionDep, try_commit

from exception import error as exc

from ..database import init_session_maker, add_eager_load_to_stmt


__all__ = [
    "CurrentUserDep",
    "CurrentUserOrNoneDep",
    "get_user_from_user_id",
    "get_current_user_or_none",
    "get_current_user",
    "remove_users_cascade",
]


SuperTokenSessionDep = Annotated[SessionContainer, Depends(verify_session())]
SuperTokenSessionOrNoneDep = Annotated[
    SessionContainer | None, Depends(verify_session(session_required=False))
]


async def get_current_user(
    session: SessionDep,
    supertoken_user: SuperTokenSessionOrNoneDep,
):
    """
    Get current user based on user token

    This function could be used as a FastAPI dependency
    """
    if supertoken_user is None:
        raise exc.TokenError(no_token=True)

    supertoken_id = supertoken_user.user_id
    orm_supertoken = await session.get(orm.SuperTokenUser, supertoken_id)
    assert orm_supertoken is not None
    orm_user = await session.run_sync(lambda ss: orm_supertoken.user)

    return orm_user


CurrentUserDep = Annotated[orm.User, Depends(get_current_user)]
"""
Dependency annotaion for `get_current_user` function
"""


async def get_current_user_or_none(
    ss: SessionDep,
    supertoken_user: SuperTokenSessionOrNoneDep,
) -> orm.User | None:
    """
    FastAPI dependency to get current user.

    Similar to `get_current_user()` function. With the only difference that
    when this function could not retrieve valid user info, it will NOT raise error
    but return `None`
    """
    if supertoken_user is None:
        return None
    try:
        return await get_current_user(ss, supertoken_user)
    except:
        return None


CurrentUserOrNoneDep = Annotated[orm.User | None, Depends(get_current_user_or_none)]
"""
Similar to `CurrentUserDep`

Check out docs of `get_current_user()` and `get_current_user_or_none()` for more info 
and about the difference of these two deps.
"""


async def get_user_from_user_id(
    session: SessionDep,
    user_id: int,
    eager_load: list[QueryableAttribute] | None = None,
) -> orm.User:
    """
    Get ORM user instance based on ``user_id``

    Args

    - user_id: The unique id of user
    - eager_load: Optional. List of User ORM class relation attributes to be eagerly loaded

    Raises

    - `no_result`
    """
    stmt = (
        select(orm.User)
        .where(orm.User.user_id.__eq__(user_id))
        .where(orm.User.deleted_at.__eq__(None))
    )
    if eager_load is not None:
        add_eager_load_to_stmt(stmt, eager_load)
    try:
        res = (await session.scalars(stmt)).one()
    except sqlexc.NoResultFound as e:
        raise exc.NoResultError(message=f"User with id:{user_id} not exists") from e

    return res


async def get_user_contact_info_count(ss: SessionDep, user: orm.User):
    """
    Return count of user contact info (internal contact info excluded)
    """
    count = await ss.run_sync(lambda x: len(user.external_contact_info))
    return count


async def remove_all_roles_of_users(
    ss: SessionDep,
    users: Sequence[orm.User],
    commit: bool = True,
) -> list[gene_sche.BulkOpeartionInfo]:
    """
    Remove all roles of a list of users
    """
    stmt = select(orm.AssociationUserRole).where(
        orm.AssociationUserRole.user_id.in_([u.user_id for u in users])
    )

    assoc_user_role = (await ss.scalars(stmt)).all()

    assoc_total = gene_sche.BulkOpeartionInfo(operation="Remove user-role associations")

    for assoc in assoc_user_role:
        assoc.delete()
        assoc_total.inc()

    if commit:
        await try_commit(ss)

    return [assoc_total]


async def get_cascade_contact_info_from_users(
    ss: SessionDep, users: Sequence[orm.User]
):
    """
    Get all contact info of a list of user
    """
    user_id_list = [u.user_id for u in users]

    stmt = (
        select(orm.ContactInfo)
        .select_from(orm.User)
        .join(orm.User.contact_info.and_(orm.User.user_id.in_(user_id_list)))
    )

    return (await ss.scalars(stmt)).all()


async def remove_users_cascade(
    ss: SessionDep,
    users: Sequence[orm.User],
    constraint: bool = False,
    commit: bool = True,
) -> list[gene_sche.BulkOpeartionInfo]:
    """
    Cascade remove user from database

    Cascade:

    - Item
    - Contact Info
    - Trade (as buyer)
    - Question (as asker)
    - Association Fav
    - Association Role

    Constraint(Deprecated, do not use this parameter):

    - The `constraint` provided by this function should not be used in production env.
      Since this constraint just check if there is any foreign key constraint and does
      not fit the actually business logic (For example, user with complete transaction
      should be able to remove their account etc.)
    """
    # lazy import
    from ..item.core import get_cascade_items_from_users, remove_items_cascade
    from ..item.core import get_cascade_questions_from_askers, remove_questions
    from ..trade.core import get_cascade_trade_from_buyers, remove_trades_cascade
    from ..fav.core import remove_fav_items_cascade, get_cascade_fav_items_by_users

    user_id_list = [u.user_id for u in users]

    # remove items
    items = await get_cascade_items_from_users(ss, users)
    if constraint and len(items) > 0:
        raise exc.CascadeConstraintError("Could not remove user with valid items")
    item_total = await remove_items_cascade(ss, items, commit=False)

    # remove contact info
    contact_info_list = await get_cascade_contact_info_from_users(ss, users)
    if constraint and len(contact_info_list) > 0:
        raise exc.CascadeConstraintError(
            "Could not remove user with valid contact info"
        )
    c_total = gene_sche.BulkOpeartionInfo(operation="Remove contact info")
    for c in contact_info_list:
        c.delete()
        c_total.inc()

    # remove trade
    trades = await get_cascade_trade_from_buyers(ss, users)
    if constraint and len(trades) > 0:
        raise exc.CascadeConstraintError("Could not remove user with valid trades")
    trade_total = await remove_trades_cascade(ss, trades, commit=False)

    # remove question
    questions = await get_cascade_questions_from_askers(ss, users)
    if constraint and len(questions) > 0:
        raise exc.CascadeConstraintError(
            "Could not remove user with valid asked questions"
        )
    question_total = await remove_questions(ss, questions, commit=False)

    # remove associations user-fav-item
    assoc_fav_items = await get_cascade_fav_items_by_users(ss, users)
    if constraint and len(assoc_fav_items) > 0:
        raise exc.CascadeConstraintError(
            "Could not remove user with valid associated fav items"
        )
    assoc_fav_items_total = await remove_fav_items_cascade(
        ss, assoc_fav_items, commit=False
    )

    # remove associations user-role
    assoc_user_role_total = await remove_all_roles_of_users(ss, users, commit=False)

    # remove supertokens
    for user in users:
        for supertoken_user in await ss.run_sync(lambda ss: user.supertoken_ids):
            # contact usertoken backend to remove supertoken user
            await delete_user(supertoken_user.supertoken_id)
            # remove supertoken user relationship in business database
            supertoken_user.delete()

    # finally, remove user itself
    user_total = gene_sche.BulkOpeartionInfo(operation="Remove users")
    for u in users:
        u.delete()
        user_total.inc()

    if commit:
        await try_commit(ss)

    remove_user_total: list[gene_sche.BulkOpeartionInfo] = (
        [user_total]
        + [c_total]
        + item_total
        + trade_total
        + question_total
        + assoc_fav_items_total
        + assoc_user_role_total
    )

    return remove_user_total
