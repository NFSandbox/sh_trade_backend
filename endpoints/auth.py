import time
from enum import Enum
from typing import Annotated
from pydantic import BaseModel

import jwt

from fastapi import APIRouter, Query, Depends, Request, Response
from fastapi.responses import JSONResponse

from exception import error as exc

from config import auth as auth_conf
from config import general as gene_conf
from exception import error as exc


def check_password(original_password: str, hashed_password: str) -> bool:
    """
    Check the validity of a password against a hashed password

    Returns:
        bool value represents the check result
    """
    # todo
    return True


def auth_and_gen_jwt(role_need_to_auth: auth_conf.RoleInfo) -> str:
    """
    Try to authenticate this user with input credentials.

    Could be used as a Deps of FastAPI endpoints.

    :param role_need_to_auth: The auth credential.
    :return: The encoded jwt token for this user.

    Exceptions:

    - `auth_error` Error occurred when verify user's role with provided credentials.
    """
    # loop the valid role to check
    for valid_role in auth_conf.ROLE_LIST:

        # matched, auth succeed
        if valid_role.auth(role_need_to_auth):
            # create token info for this user
            token_data = TokenData(
                role_name=valid_role.name,
                created_at=int(time.time()),
                disabled=False,
            )

            # return encoded jwt
            return token_data.to_jwt()

        # name matched, password incorrect
        if role_need_to_auth.name == valid_role.name:
            raise exc.AuthError(role=role_need_to_auth, has_match=True)

    # no role matched
    raise exc.AuthError(role=role_need_to_auth)


def require_role(
        role_list: list[str],
):
    """
    A dependency function generator used to generate a dependency function used by FastAPI to
    require a certain role.

    The generated dependency function will return the name of the role as a string
    if verify passed. Else raise ``TokenError``.

    :param role_list: A list of string represents the roles that could pass the verification.

    Exceptions:

    - `token_expired`
    - `token_role_not_match`
    - `token_required`

    > Here exceptions means what error the generated dependency function may throw, not generator itself.

    Checkout `TokenError` class for more info.
    """

    def generated_role_requirement_func(
            req: Request
    ):
        jwt_str = req.cookies.get(auth_conf.JWT_FRONTEND_COOKIE_KEY)
        if jwt_str is None:
            raise exc.TokenError(no_token=True)

        # convert jwt string to token data
        token_data = TokenData.from_jwt(jwt_str=jwt_str)
        token_data.try_verify(role_list)
        return token_data.role_name

    return generated_role_requirement_func


class LoginTokenOut(BaseModel):
    token: str


@auth_router.post('/login', response_model=LoginTokenOut)
async def login_into_account(
        token: Annotated[str, Depends(auth_and_gen_jwt)],
        resp: Response):
    """
    Authenticate the credentials then return jwt token string
    and write cookies.
    """
    resp.set_cookie(key=auth_conf.JWT_FRONTEND_COOKIE_KEY, value=token, max_age=30 * 24 * 60 * 60)
    return LoginTokenOut(token=token)


@auth_router.get('/logout')
async def logout_account(resp: Response):
    resp = JSONResponse(
        status_code=200,
        content={'is_logged_out': True}
    )
    resp.delete_cookie(key=auth_conf.JWT_FRONTEND_COOKIE_KEY)
    return resp


@auth_router.get('/me')
async def get_current_user_info(role: Annotated[str, Depends(require_role(['admin', 'user']))]):
    """
    Return json contains role name if logged in, else raise error `token_required`

    JSON Schema::

        {
            has_role: true,
            role_name: str,
        }

    Exceptions:

    - `token_expired`
    - `token_role_not_match`
    - `token_required`

    Checkout `TokenError` class for more info.
    """
    return JSONResponse(content={
        "has_role": True,
        "role_name": role,
    })


@auth_router.post('/role_test')
async def role_require_test(test: Annotated[str, Depends(require_role(['admin']))]):
    return test
