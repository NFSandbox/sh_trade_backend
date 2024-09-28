import time

from typing import Annotated, cast, List, Sequence

from loguru import logger
from sqlalchemy import select, update, func, Column, distinct, or_
from sqlalchemy.orm import selectinload, QueryableAttribute, aliased
from sqlalchemy.sql import and_
from sqlalchemy import exc as sqlexc


from schemes import sql as orm
from schemes import general as gene_sche

from ..database import SessionDep, try_commit

from exception import error as exc


async def remove_fav_items_of_user(
    ss: SessionDep, user: orm.User, item_id_list: Sequence[int] | None
) -> gene_sche.BulkOpeartionInfo:
    """
    Remove (soft delete) items from user's favourite, return `BulkOpeartionInfo`

    Param

    - `item_id_list` If `None`, will remove all fav items from this user,
      else only remove items which's `item_id` in list
    """
    stmt = select(orm.AssociationUserFavouriteItem).where(
        orm.AssociationUserFavouriteItem.user_id == user.user_id,
    )

    if item_id_list is not None:
        stmt = stmt.where(orm.AssociationUserFavouriteItem.item_id.in_(item_id_list))

    item_asso_to_remove = (await ss.scalars(stmt)).all()

    # remove fav items
    bulk_count = gene_sche.BulkOpeartionInfo(operation="Delete fav items")
    for i_asso in item_asso_to_remove:
        i_asso.delete()  # soft delete
        bulk_count.inc()

    await try_commit(ss)

    return bulk_count


async def get_cascade_fav_items_by_items(ss: SessionDep, items: Sequence[orm.Item]):
    stmt = select(orm.AssociationUserFavouriteItem).where(
        orm.AssociationUserFavouriteItem.item_id.in_([i.item_id for i in items])
    )

    return (await ss.scalars(stmt)).all()


async def get_cascade_fav_items_by_users(ss: SessionDep, users: Sequence[orm.User]):
    """
    Get fav items association of a list of users
    """
    stmt = select(orm.AssociationUserFavouriteItem).where(
        orm.AssociationUserFavouriteItem.user_id.in_([u.user_id for u in users])
    )

    return (await ss.scalars(stmt)).all()


async def remove_fav_items_cascade(
    ss: SessionDep,
    associations: Sequence[orm.AssociationUserFavouriteItem],
    commit: bool = True,
) -> list[gene_sche.BulkOpeartionInfo]:
    count = gene_sche.BulkOpeartionInfo(operation="Remove user-fav-item associations")

    for a in associations:
        count.inc()
        a.delete()

    if commit:
        await try_commit(ss)

    return [count]
