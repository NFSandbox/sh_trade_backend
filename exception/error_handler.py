from fastapi import Request, Response, FastAPI
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import HTTPException, RequestValidationError

from loguru import logger

from .error import BaseError, InternalServerError


async def validation_exception_handler(request, e):
    e = e.errors()
    first_exc = e[0]
    logger.error(first_exc)
    return await http_exception_handler(
        request,
        HTTPException(
            status_code=422,
            detail=BaseError(
                name="validation_error",
                message=f"{first_exc['msg']}. Location: {first_exc['loc']}. ({first_exc['type']})",
                status=422,
            )
            .to_pydantic_base_error()
            .model_dump(),
        ),
    )


async def base_error_handler(request: Request, e: BaseError):
    """
    An error handler used to handle all subclass of BaseError class.

    BaseError is a custom base class for error raised in this application.
    """
    # replace error if the error is from serverside.
    # this is to prevent unexpected info leak from server
    error_to_client = e

    if e.status >= 500:
        logger.exception(e)
        error_to_client = InternalServerError()
    else:
        logger.error(e)

    return await http_exception_handler(
        request,
        HTTPException(
            status_code=200,
            detail=error_to_client.to_pydantic_base_error().model_dump(),
        ),
    )


async def internal_error_handler(request: Request, e: Exception):
    """
    Default error handler, deal with errors that not been caught by previous two handlers
    """
    logger.exception(e)
    return await http_exception_handler(
        request,
        HTTPException(
            status_code=500,
            detail=InternalServerError().to_pydantic_base_error().model_dump(),
        ),
    )


def add_exception_handlers(app: FastAPI):
    """
    Add a bunch of error handlers into a FastAPI instance.
    """
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(BaseError, base_error_handler)
    app.add_exception_handler(Exception, internal_error_handler)
