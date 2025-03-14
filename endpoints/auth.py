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

from supertokens_python.recipe.emailpassword.asyncio import sign_in, sign_up
from supertokens_python.recipe.emailpassword.interfaces import (
    SignInOkResult,
    SignInWrongCredentialsError,
)

from sqlalchemy.exc import MultipleResultsFound

from config import auth as auth_conf
from schemes import auth as auth_sche
from schemes import db as db_sche
from schemes import sql as orm
from provider import auth as auth_provider
from provider import user as user_provider
from provider import database as db_provider
from exception import error as exc

from schemes import auth as auth_schema

# the auth process is built based on official FastAPI docs
# https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/#hash-and-verify-the-passwords

# crypt context used by passlib
passlib_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# set token retrieving URL to `/token`
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# token router
# this router should be added to app without any prefix,
# since /token endpoint should be at root path based on oauth2 spec
token_router = APIRouter()

# auth router
auth_router = APIRouter()


# def verify_password(original_password: str, hashed_password: str) -> bool:
#     """
#     Check the validity of a password against a hashed password

#     Returns:
#         bool value represents the check result
#     """

#     return passlib_context.verify(original_password, hashed_password)


# async def check_password_with_db(
#     session: db_provider.SessionDep, contact_info: str, password: str
# ):
#     """Verify username and password using the data in database

#     Args:
#         contact_info (str): contact info
#         contact_info: Contact info user provided
#         password: Password user provided

#     Return:
#         user: ORM User instance if verified

#     Raises:
#         AuthError: if the password is incorrect or contact info is invalid
#     """
#     user = await auth_provider.get_user_by_contact_info(session, contact_info)

#     # invalid contact info
#     if user is None:
#         raise exc.AuthError(invalid_contact=True)

#     logger.debug(f"Input original password: {password}")
#     verify_res = verify_password(password, user.password)
#     # invalid password
#     if not verify_res:
#         raise exc.AuthError(invalid_password=True)

#     # success
#     return user


@auth_router.post(
    "/token",
    responses=exc.openApiErrorMark(
        {401: "Error occurred when retrieving or verifying token"}
    ),
    deprecated=True,
)
async def user_sign_in(
    username: Annotated[str, Body()],
    password: Annotated[str, Body()],
    resp: Response,
    session: db_provider.SessionDep,
) -> None:
    # token = await login_for_token(session, username, password)
    # resp.set_cookie(
    #     key=auth_conf.JWT_FRONTEND_COOKIE_KEY,
    #     value=token.access_token,
    #     max_age=auth_conf.TOKEN_EXPIRES_DELTA_HOURS * 60 * 60,
    # )
    return None


async def get_current_user_use_header(
    token: Annotated[str, Depends(oauth2_scheme)],
):
    """
    Get current user based on user token
    """

    token_data = auth_sche.TokenData.from_jwt_str(token)

    # token expired
    if token_data.is_expired():
        raise exc.TokenError(expired=True)

    return token_data


@auth_router.get("/logout", deprecated=True)
async def user_sign_out():
    resp = JSONResponse(status_code=200, content={"is_logged_out": True})
    resp.delete_cookie(key=auth_conf.JWT_FRONTEND_COOKIE_KEY)
    return resp


@auth_router.get(
    "/test/token_dependency", response_model=auth_schema.TokenData, deprecated=True
)
async def get_current_token_info(
    # token_data: Annotated[
    #     auth_schema.TokenData, Depends(user_provider.get_current_token)
    # ]
):
    return None


@auth_router.get(
    "/test/user_dependency",
    response_model=db_sche.UserOut,
    response_model_exclude_none=True,
)
async def get_current_user_info(
    user: user_provider.CurrentUserDep,
):
    return user


@auth_router.post("/test/rbac")
async def test_rbac_permissions(
    p: Annotated[bool, Depends(auth_provider.PermissionsChecker({"rbac:test"}))],
    ss: db_provider.SessionDep,
    user: auth_provider.CurrentUserDep,
    permissions: Annotated[
        set[auth_provider.rbac_config.AllowedPermissionsLiteral], Body(embed=True)
    ],
):
    await auth_provider.check_user_permission(
        ss=ss, user=user, required_permissions=permissions
    )


@auth_router.post("/register", response_model=db_sche.UserOut, deprecated=True)
async def user_sign_up(
    ss: db_provider.SessionDep,
    info: Annotated[db_sche.UserIn, Body(embed=False)],
    resp: Response,
):
    try:
        # check dupliate
        await auth_provider.check_no_username_duplicate(ss, info.username)

        # create new user
        new_user = orm.User(
            username=info.username, password=passlib_context.hash(info.password)
        )
        ss.add(new_user)

        # auto login reusing endpoint function
        # this part also take charge of raising error if username duplicated
        # since if duplicated, there will be two users shared the same `new_user.username`
        try:
            await user_sign_in(
                new_user.username,
                info.password,
                session=ss,
                resp=resp,
            )
        except MultipleResultsFound:
            raise exc.BaseError(
                name="username_already_exists",
                message="Username input has already used by other users, please try another username.",
            )

        # commit
        await ss.commit()
        return new_user

    except:
        logger.debug("Database rolling back...")
        await ss.rollback()
        raise
