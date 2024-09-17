import time
from typing import Annotated, cast, List

from loguru import logger
from fastapi import APIRouter, Query, Depends, Request, Response, status, Body


from schemes import db as db_sche
from schemes import general as gene_sche
from schemes import sql as orm

from provider import user as user_provider
from provider import database as db_provider
from provider.database import SessionDep
from exception import error as exc


user_router = APIRouter()


@user_router.post(
    "/description", response_model=db_sche.UserOut, response_model_exclude_none=True
)
async def update_user_description(
    session: db_provider.SessionDep,
    description: Annotated[str, Body(max_length=100)],
    user: Annotated[orm.User, Depends(user_provider.get_current_user)],
    user_id: Annotated[int | None, Body()] = None,
) -> db_sche.UserOut:
    """
    Update user description.

    Args

    - `user`: Dependency. Current active user.
    - `user_id`: If None, update description of current user. If specified, update user with the `user_id`

    Raises

    - `user_not_exists`
    - `permission_required`
    """

    # using user_id to specify user, need to check roles
    if (user_id is not None) and (not await user.verify_role(["admin"])):
        raise exc.PermissionError(
            message="You don't have permission to change other users description.",
            roles=await user.awaitable_attrs.roles,
        )

    # try get the specified user
    if user_id is not None:
        try:
            user = await user_provider.get_user_from_user_id(session, user_id)
            if user.deleted:
                raise
        except:
            raise exc.ParamError(
                param_name="user_id",
                message="The user you want to update description of is not exists",
            )

    await user_provider.update_user_description(session, user, description)
    await session.commit()

    return db_sche.UserOut.model_validate(user)


@user_router.post("/contact_info/add", response_model=db_sche.ContactInfoIn)
async def add_user_contact_info(
    ss: SessionDep,
    current_user: user_provider.CurrentUserDep,
    info: db_sche.ContactInfoIn,
):
    uew_contact_info = await user_provider.add_contact_info(ss, current_user, info)
    await ss.commit()

    return info


@user_router.get("/contact_info", response_model=List[db_sche.ContactInfoIn])
async def get_user_contact_info(
    ss: SessionDep,
    current_user: user_provider.CurrentUserDep,
    user_id: int | None = None,
):
    """
    Get contact info of a user based on user id.

    Default to current user If `user_id` not specified.
    """
    # validate user_id
    if user_id is None:
        user_id = current_user.user_id

    # check permission (raise if failed)
    await user_provider.check_get_contact_info_permission(
        ss,
        requester_id=current_user.user_id,
        user_id=user_id,
    )

    # retrieve info
    contact_info_list = await user_provider.get_user_contact_info_list(
        ss, await user_provider.get_user_from_user_id(ss, user_id)
    )

    return contact_info_list


@user_router.delete("/contact_info/remove", response_model=db_sche.ContactInfoIn)
async def remove_user_contact_info(
    ss: SessionDep, user: user_provider.CurrentUserDep, info: db_sche.ContactInfoIn
):
    """
    Remove a contact info from current user

    Args

    - `info` The info to be removed

    Raises

    - `no_result`
    """
    contact_info_list = await user_provider.get_user_contact_info_list(ss, user)

    found_flag = False
    for info_orm in contact_info_list:
        if (
            info_orm.contact_type == info.contact_type
            and info_orm.contact_info == info.contact_info
            and info_orm.deleted == False
        ):
            found_flag = True
            info_orm.deleted = True

    if found_flag == False:
        raise exc.NoResultError("Contact info not exists for current user")

    try:
        await ss.commit()
        return info
    except:
        await ss.rollback()
        raise


@user_router.delete(
    "/contact_info/remove_all", response_model=gene_sche.BlukOpeartionInfo
)
async def remove_all_user_contact_info(
    ss: SessionDep, user: user_provider.CurrentUserDep
):
    """
    Remove all contact info of current user
    """
    remove_count: int = 0
    await user.awaitable_attrs.contact_info

    for contact in user.contact_info:
        if not contact.deleted:
            contact.deleted = True
            remove_count += 1

    try:
        await ss.commit()
        return gene_sche.BlukOpeartionInfo(
            operation="Remove all contact info", total=remove_count
        )
    except:
        await ss.rollback()
        raise
