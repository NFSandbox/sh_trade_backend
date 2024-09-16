import time
import jwt
from enum import Enum
from typing import Annotated, cast, List
from pydantic import BaseModel

from loguru import logger
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from fastapi import APIRouter, Query, Depends, Request, Response, status, Body
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException

from sqlalchemy.ext.asyncio import AsyncSession


from schemes import db as db_sche
from schemes import sql as orm
from provider import user as user_provider
from provider import auth as auth_provider
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


@user_router.get("/contact_info")
async def get_all_contact_infO(
    ss: SessionDep,
    current_user: user_provider.CurrentUserDep,
    user_id: int,
):
    await user_provider.check_get_contact_info_permission(
        ss,
        requester_id=current_user.user_id,
        user_id=user_id,
    )

    return True
