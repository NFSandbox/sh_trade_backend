from typing import Sequence, Annotated, Set

from loguru import logger
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload, Session
from sqlalchemy.sql import and_
from sqlalchemy import exc as sqlexc

from fastapi import Body

from config import rbac as rbac_config

from schemes import sql as orm
from .database import init_session_maker, session_maker, SessionDep
from .user.core import CurrentUserDep, CurrentUserOrNoneDep

from exception import error as exc

from tools import rbac_manager as rbac

# make sure session has already been initialized
init_session_maker()

_rbac_manager = rbac.RBACManager(
    rbac_config.ROLE_LIST, rbac_config.ROLE_INHERIT, rbac_config.ROLE_PERMISSIONS
)
"""
RBAC manager for this auth module.

Should not be used directly.
"""


async def get_user_by_user_id(session: SessionDep, user_id: int):
    """
    Get user from database by user_id

    Return `None` if not valid user

    Notes:
    - Deleted user will not be returned
    """
    return (
        await session.scalars(select(orm.User).where(orm.User.user_id == user_id))
    ).one_or_none()


async def get_user_by_contact_info(
    session: SessionDep, login_info: Annotated[str, Body]
) -> orm.User | None:
    """
    Try to get user by contact info

    Return:
    - ORM User instance if user found. Otherwise, return `None`

    Notes:
    - When used as dependency, the `login_info` is required in request Body.
    """
    stmt_username = select(orm.User).where(orm.User.username.__eq__(login_info))
    stmt_contact_info = (
        select(orm.ContactInfo)
        .options(selectinload(orm.ContactInfo.user))
        .where(orm.ContactInfo.contact_info == login_info)
        .where(orm.ContactInfo.deleted_at == None)
    )

    # first try to find username
    user = (await session.scalars(stmt_username)).one_or_none()
    if not user:
        # there should be at most one result in the database, since contact_info should be unique
        contact = (await session.scalars(stmt_contact_info)).one_or_none()

        # no corresponding contact info found in db
        if contact is None:
            raise exc.AuthError(invalid_contact=True)

        # found corresponding info, find relevant user
        user = contact.user

    # user invalid
    if user.deleted_at is not None:
        raise exc.AuthError(invalid_contact=True)

    # success
    return user


async def check_no_username_duplicate(ss: SessionDep, username: str):
    """
    Check if username already exists in database

    Return None if check pass, else raise.
    """
    stmt = (
        select(func.count()).select_from(orm.User).where(orm.User.username == username)
    )

    res = (await ss.scalars(stmt)).one()

    if res > 0:
        raise exc.DuplicatedError(
            name="username_already_exists",
            message="The choosed username already used by others, please change username and try again",
        )


async def check_user_permission(
    ss: SessionDep,
    user: CurrentUserOrNoneDep,
    required_permissions: Set[rbac_config.AllowedPermissionsLiteral],
):
    """
    Function used to check if user satisfy a set of required permissions.

    Check passed only if the user has ALL permissions required in `required_permissions` set.

    To use permission check as dependency, check out `PermissionsChecker`
    """
    role_set = set()
    # get user role set if user logged in
    if user is not None:

        def get_role_set(ss: Session):
            ret_set = set(user.role_name_list)
            if rbac_config.SIGNED_IN_ROLE is not None:
                ret_set.add(rbac_config.SIGNED_IN_ROLE)
            return ret_set

        role_set = await ss.run_sync(get_role_set)
    # else use guest role
    elif rbac_config.GUEST_ROLE is not None:
        role_set = {rbac_config.GUEST_ROLE}
    else:
        role_set = set()

    for role in role_set:
        try:
            _rbac_manager.check_role_has_all_permissions(role, required_permissions)
            return True
        except rbac.InsufficientPermission:
            pass

    raise exc.PermissionError(roles=role_set, permissions=required_permissions)


class PermissionsChecker:
    """
    Encapsulation of check_user_permission with fixed required permissions set.
    Return a bool value represents the check result. Or raise if `raise_on_fail` is `True`.

    Usage as dependency:

        p = Annotated[bool, PermissionsChecker({"read:all", "write:self"})]

    Args

    - `required_permissions` The permission need to be checked
    - `raise_on_fail` If `True`, will raise error if permission check failed.
      Else will return `False` instead of raise.
    """

    def __init__(
        self,
        required_permissions: Set[rbac_config.AllowedPermissionsLiteral],
        raise_on_fail: bool = True,
    ) -> None:
        self.required_permissions = required_permissions
        self.raise_on_fail = raise_on_fail

    async def __call__(self, ss: SessionDep, user: CurrentUserOrNoneDep):
        return await self.check_permission(ss, user)

    async def check_permission(
        self, ss: SessionDep, user: CurrentUserOrNoneDep
    ) -> bool:
        try:
            await check_user_permission(ss, user, self.required_permissions)
            return True
        except Exception as e:
            if self.raise_on_fail:
                raise e
            return False
