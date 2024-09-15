import time
import jwt
from enum import Enum
from typing import Annotated
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

    if (user_id is not None) and (not await user.verify_role(["admin"])):
        raise exc.PermissionError(
            message="You don't have permission to change other users description.",
            roles=await user.awaitable_attrs.roles,
        )

    if user_id is not None:
        user = await user_provider.get_user_from_user_id(session, user_id)

    await user_provider.update_user_description(session, user, description)
    await session.commit()

    return db_sche.UserOut.model_validate(user)