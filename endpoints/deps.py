import time

import jwt

from config import auth as auth_conf
from exception import error as exc

from schemes.auth import TokenData


def auth_and_gen_jwt(role_need_to_auth: auth_conf.RoleInfo) -> str:
    """
    Try to authenticate this user with input credentials.
    :param role_need_to_auth: The auth credential.
    :return: The encoded jwt token for this user.
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
            return jwt.encode(
                payload=token_data.model_dump(),
                key=auth_conf.PYJWT_SECRET_KEY,
                algorithm=auth_conf.PYJWT_ALGORITHM,
            )

        # name matched, password incorrect
        if role_need_to_auth.name == valid_role.name:
            raise exc.AuthError(role=role_need_to_auth, has_match=True)

    # no role matched
    raise exc.AuthError(role=role_need_to_auth)
