from typing import Literal, Any, Collection
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


class InternalServerError(BaseError):
    """
    Raise when internal server error occurred

    The status code passed to this error should >= 500, if not,
    the init method will set to 500 forcefully.
    """

    def __init__(
        self,
        name: str = "internal_server_error",
        message: str = "An error occurred in server-side. If error persists, please contact website admin",
        status: int = 500,
    ) -> None:
        # should not have http status code less then 500
        if status < 500:
            status = 500

        super().__init__(
            name=name,
            message=message,
            status=status,
        )


class PermissionError(BaseError):
    """
    Raise when permission error occurred

    - `roles` The roles used when verifying permissions
    - `permissions` The permissions required by this operations

    Both of they should be list of printable object
    """

    def __init__(
        self,
        name: str = "permission_required",
        roles: Collection[Any] | None = None,
        permissions: Collection[Any] | None = None,
        message: str = "Insufficient to perform this operation. ",
    ) -> None:

        if roles is not None:
            message += f"Provided roles: {roles}. "
        if permissions is not None:
            message += f"Required permissions: {permissions}. "

        super().__init__(
            name=name,
            status=httpstatus.HTTP_403_FORBIDDEN,
            message=message,
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
        name="no_result",
        message: str = "Could not found any result satisfying condition from database.",
    ) -> None:
        super().__init__(
            name=name,
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


class ConflictError(BaseError):
    """
    Raise when user's request cause a conflict with current state of system
    """

    def __init__(
        self,
        name: str = "conflict_error",
        message: str = "The operation causes conflict in the system",
        status: int = httpstatus.HTTP_409_CONFLICT,
    ) -> None:
        super().__init__(name, message, status)


class IllegalOperationError(BaseError):
    """
    Raise when user's request is illegal (HTTP_406)
    """

    def __init__(
        self,
        name: str = "illegal_operation",
        message: str = "This operation is not allowed for current user or in current situation",
        status: int = httpstatus.HTTP_406_NOT_ACCEPTABLE,
    ) -> None:
        super().__init__(name, message, status)
