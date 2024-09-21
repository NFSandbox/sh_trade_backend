from typing import Literal
from fastapi import status as httpstatus
from pydantic import BaseModel

from schemes import sql as orm


class BaseError(Exception):
    """
    Base error class for backend application
    """

    name: str
    message: str
    status: int

    def __init__(self, name: str, message: str, status: int = 403) -> None:
        super().__init__(message)
        self.message = message
        self.name = name
        self.status = status

    def to_pydantic_base_error(self):
        """
        Wrapper for ``BaseErrorOut.from_base_error()``
        :return:
        """
        return BaseErrorOut.from_base_error(self)


class PermissionError(BaseError):
    def __init__(
        self, roles: list[orm.Role] | None = None, message: str | None = None
    ) -> None:
        final_message = "You don't have the permission to perform this operation."
        if message is not None:
            final_message = message

        if roles is not None and len(roles) > 0:
            final_message += f" Current roles: "
            for role in roles:
                final_message += f"{role.role_title}({role.role_name}) "

        super().__init__(
            name="permission_required",
            status=httpstatus.HTTP_403_FORBIDDEN,
            message=final_message,
        )


class BaseErrorOut(BaseModel):
    """
    Class that used to convert BaseError to a pydantic class that could be passed to frontend through API.
    """

    name: str
    message: str
    status: int

    @classmethod
    def from_base_error(cls, e: BaseError):
        return cls(name=e.name, message=e.message, status=e.status)


class BaseErrorOutForOpenApi(BaseModel):
    detail: BaseErrorOut


def openApiErrorMark(status_description_dict: dict[int, str]):
    res_dict = {}
    for code, desc in status_description_dict.items():
        res_dict[code] = {
            "model": BaseErrorOutForOpenApi,
            "name": desc,
            "title": desc,
            "description": desc,
        }

    return res_dict


class NoResultError(BaseError):
    """
    Raise when could not find any result satisfying condition from database.
    """

    def __init__(
        self,
        message: str = "Could not found any result satisfying condition from database.",
    ) -> None:
        super().__init__(
            name="no_result",
            message=message,
            status=httpstatus.HTTP_404_NOT_FOUND,
        )


class AuthError(BaseError):
    """
    Raise when backend could not authorize user with given credentials.

    Check `__init__()` for more info.
    """

    def __init__(
        self,
        invalid_contact: bool = False,
        invalid_password: bool = False,
    ):
        """
        Create an `AuthError` instance.

        Parameters:

        - ``invalid_contact`` Set to true if error caused by invalid contact info
        - ``invalid_password`` Set to true if error caused by invalid password
        """
        err_msg: str = (
            "User authentication failed, please check if you passed the correct role name and password"
        )
        if invalid_contact:
            err_msg = f"Invalid account info or username"
        if invalid_password:
            err_msg = f"Incorrect password"
        super().__init__(
            name="auth_error", message=err_msg, status=httpstatus.HTTP_401_UNAUTHORIZED
        )


class TokenError(BaseError):
    """
    Raise when error occurred while verifying token.

    Check out __init__() for more info.

    Params:

    - `invalid_token` Token is invalid, for example, not matching the JWT format
    - `expired` Token expired.
    - `no_token` Pass `True` when error is occurred because of token could not be found.
    - `message` If `None`, will automatically determined by the error cause. Use default if no cause provided.
    - `message` If not `None`, always use the received one as final message despite presets of error cause.
    """

    def __init__(
        self,
        message: str | None = None,
        invalid_format: bool | None = None,
        expired: bool | None = None,
        role_not_match: bool | None = None,
        no_token: bool | None = None,
    ) -> None:
        final_name = "token_error"
        final_message = message
        """
        Create an `TokenError` instance.
        :param message:
        :param expired: If `true`, indicates the token is expired.
        :param role_not_match: If `true`, indicates the role are not match the requirements.
        """
        if message is None:
            message = "Could not verify the user tokens"

        if invalid_format:
            final_name = "invalid_token_format"
            message = "Invalid token format, please try logout and login again"

        if expired:
            final_name = "token_expired"
            message = "Token expired, try login again to get a new token"

        if role_not_match:
            final_name = "token_role_not_match"
            message = "Current role are not match the requirements to perform this operation or access this resources"

        if no_token:
            final_name = "token_required"
            message = "Could not found a valid token, try login to an valid account"

        # only when message is None, then use presets, otherwise always use the original message passed.
        if final_message is None:
            final_message = message

        super().__init__(name=final_name, message=final_message, status=401)


class ParamError(BaseError):
    """
    Raise when the receiving parameters are illegal.

    Notice, the general param type error will be caught and dealt by FastAPI.
    This Error is used when FastAPI couldn't deal with such error.
    """

    def __init__(self, param_name: str, message: str) -> None:
        super().__init__(
            "param_error",
            f'Param error, "{param_name}": {message}',
            httpstatus.HTTP_400_BAD_REQUEST,
        )


class CascadeConstraintError(BaseError):
    """
    Raise when constraint condition trigger in soft delete operation
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            "cascade_constraint",
            message,
            status=httpstatus.HTTP_400_BAD_REQUEST,
        )


class DuplicatedError(BaseError):
    """
    Raise when duplicated info found while adding info
    """

    def __init__(
        self,
        name: str = "already_exists",
        message: str = "Data already exists",
        status: int = httpstatus.HTTP_409_CONFLICT,
    ) -> None:
        super().__init__(name, message, status)


class LimitExceededError(BaseError):
    """
    Raise when operation reachs some of the limitation of this system
    """

    def __init__(
        self,
        name: str = "limit_exceeded",
        message: str = "System limit exceeded",
        status: int = httpstatus.HTTP_400_BAD_REQUEST,
    ) -> None:
        super().__init__(name, message, status)
