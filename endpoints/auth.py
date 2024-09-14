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

from config import auth as auth_conf
from schemes import auth as auth_sche
from schemes import db as db_sche
from schemes import sql as orm
from provider import auth as auth_provider
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


def verify_password(original_password: str, hashed_password: str) -> bool:
    """
    Check the validity of a password against a hashed password

    Returns:
        bool value represents the check result
    """
    logger.debug(f"Verifying: Original: {original_password}, hashed: {hashed_password}")

    return passlib_context.verify(original_password, hashed_password)


async def check_password_with_db(contact_info: str, password: str):
    """
    Verify username and password using the data in database

    Parameters:

    - ``contact_info`` Contact info user provided
    - ``password`` Password user provided

    Return:
        ORM User instance if verified

    Exceptions:

    - Raise ``AuthError`` if the password is incorrect or contact info is invalid
    """
    user = await auth_provider.get_user_by_contact_info(contact_info)
    logger.debug(f"Got user from contact! Username: {user.username}")

    # invalid contact info
    if user is None:
        raise exc.AuthError(invalid_contact=True)

    logger.debug(f"Input original password: {password}")
    verify_res = verify_password(password, user.password)
    # invalid password
    if not verify_res:
        raise exc.AuthError(invalid_password=True)

    # success
    return user


async def login_for_token(username: str, password: str):
    # get user info based on auth credentials
    try:
        user = await check_password_with_db(username, password)
    except exc.AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            # this header content is specified in oauth2 spec
            headers={"WWW-Authenticate": "Bearer"},
            detail=exc.BaseErrorOut.from_base_error(e).model_dump(),
        )
    roles: list[str] = [role.role_name for role in user.roles]

    # return generated token based on user info
    return auth_sche.TokenOut(
        access_token=auth_sche.TokenData(
            user_id=user.user_id, roles=roles, created_time=int(time.time())
        ).to_jwt_str(),
        token_type="bearer",
    )


@token_router.post("/token")
async def login_for_token_from_form_data(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    resp: Response,
) -> auth_sche.TokenOut:
    logger.debug("Into /token")
    token = await login_for_token(form_data.username, form_data.password)
    resp.set_cookie(
        key=auth_conf.JWT_FRONTEND_COOKIE_KEY,
        value=token.access_token,
        max_age=auth_conf.TOKEN_EXPIRES_DELTA_HOURS * 60 * 60,
    )
    return token


@auth_router.post("/token")
async def login_for_token_from_json(
    username: Annotated[str, Body()],
    password: Annotated[str, Body()],
    resp: Response,
) -> auth_sche.TokenOut:
    token = await login_for_token(username, password)
    resp.set_cookie(
        key=auth_conf.JWT_FRONTEND_COOKIE_KEY,
        value=token.access_token,
        max_age=auth_conf.TOKEN_EXPIRES_DELTA_HOURS * 60 * 60,
    )
    return token


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


async def get_current_user_use_cookies(req: Request):
    """
    Get current user based on user token
    """

    # no token
    token = req.cookies.get(auth_conf.JWT_FRONTEND_COOKIE_KEY)
    if token is None:
        raise exc.TokenError(no_token=True)

    token_data = auth_sche.TokenData.from_jwt_str(token)

    # token expired
    if token_data.is_expired():
        raise exc.TokenError(expired=True)

    return token_data


# def require_role(
#     role_list: list[str],
# ):
#     """
#     A dependency function generator used to generate a dependency function used by FastAPI to
#     require a certain role.
#
#     The generated dependency function will return the name of the role as a string
#     if verify passed. Else raise ``TokenError``.
#
#     :param role_list: A list of string represents the roles that could pass the verification.
#
#     Exceptions:
#
#     - `token_expired`
#     - `token_role_not_match`
#     - `token_required`
#
#     > Here exceptions means what error the generated dependency function may throw, not generator itself.
#
#     Checkout `TokenError` class for more info.
#     """
#
#     def generated_role_requirement_func(req: Request):
#         jwt_str = req.cookies.get(auth_conf.JWT_FRONTEND_COOKIE_KEY)
#         if jwt_str is None:
#             raise exc.TokenError(no_token=True)
#
#         # convert jwt string to token data
#         token_data = TokenData.from_jwt(jwt_str=jwt_str)
#         token_data.try_verify(role_list)
#         return token_data.role_name
#
#     return generated_role_requirement_func


@auth_router.get("/logout")
async def logout_account():
    resp = JSONResponse(status_code=200, content={"is_logged_out": True})
    resp.delete_cookie(key=auth_conf.JWT_FRONTEND_COOKIE_KEY)
    return resp


@auth_router.get("/user_test", response_model=auth_schema.TokenData)
async def get_current_user_info(
    token_data: Annotated[auth_schema.TokenData, Depends(get_current_user_use_cookies)]
):
    return token_data
