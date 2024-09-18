import time
from pydantic import BaseModel
import jwt

from config import auth as auth_conf
from exception import error as exc

from schemes.sql import get_current_timestamp_ms

__all__ = [
    "TokenOut",
    "TokenData",
]


class TokenData(BaseModel):
    """
    Specify the data stored in the encrypted token

    Parameters:

    - ``user_id`` Unique ID of user
    - ``roles`` List of string represnts the ``role_name`` this user have
    - ``created_time`` UNIX timestamp of created time of this token
    """

    user_id: int
    roles: list[str]
    created_time: int

    def to_jwt_str(self):
        """
        Return encrypted JWT string corresponding to this instance
        """
        return jwt.encode(
            self.model_dump(),
            auth_conf.PYJWT_SECRET_KEY,
            algorithm=auth_conf.PYJWT_ALGORITHM,
        )

    @classmethod
    def from_jwt_str(cls, jwt_str: str):
        try:
            info_dict = jwt.decode(
                jwt_str,
                auth_conf.PYJWT_SECRET_KEY,
                algorithms=[auth_conf.PYJWT_ALGORITHM],
            )
        except:
            raise exc.TokenError(invalid_format=True)
        return cls(**info_dict)

    def is_expired(self):
        """If this token is expired in current time"""
        return (
            self.created_time + auth_conf.TOKEN_EXPIRES_DELTA_HOURS * 3600 * 1000
            < get_current_timestamp_ms()
        )


class TokenOut(BaseModel):
    """
    Pydantic model for out data of ``/token`` endpoint

    This schema is specified in OAuth spec, do not change
    field name and other info.

    This is not the data stored in the token, which will be
    specified by another model called ``TokenData``

    Parameters:

    Check out class member.
    """

    access_token: str
    token_type: str
