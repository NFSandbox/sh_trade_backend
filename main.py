from fastapi import FastAPI
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.exception_handlers import http_exception_handler

import uvicorn
from loguru import logger

from exception.error import BaseError, BaseErrorOut

import config

# sub routers
from endpoints.auth import auth_router, token_router
from endpoints.user import user_router
from endpoints.item import item_router
from endpoints.fav import fav_router

# CORS Middleware
middlewares = [
    Middleware(
        CORSMiddleware,
        allow_origins=config.general.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
]

# include sub routers
app = FastAPI(middleware=middlewares)
app.include_router(token_router, tags=["Token"])
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(user_router, prefix="/user", tags=["User"])
app.include_router(item_router, prefix="/item", tags=["Item"])
app.include_router(fav_router, prefix="/fav", tags=["Favourite"])


@app.exception_handler(RequestValidationError)
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


@app.exception_handler(BaseError)
async def base_error_handler(request: Request, e: BaseError):
    """
    An error handler used to handle all subclass of BaseError class.

    BaseError is a custom base class for error raised in this application.
    """
    return await http_exception_handler(
        request,
        HTTPException(
            status_code=e.status, detail=e.to_pydantic_base_error().model_dump()
        ),
    )


@app.exception_handler(Exception)
async def internal_error_handler(request: Request, e: Exception):
    """
    Default error handler, deal with errors that not been caught by previous two handlers
    """
    logger.exception(e)
    return await http_exception_handler(
        request,
        HTTPException(
            status_code=500,
            detail=BaseError(
                name="internal_server_error",
                message="An error occurred in server-side. If error persists, please contact website admin",
                status=500,
            )
            .to_pydantic_base_error()
            .model_dump(),
        ),
    )


# Start uvicorn server
if __name__ == "__main__":
    # determine host
    host = "127.0.0.1"
    if config.general.ON_CLOUD:
        host = "0.0.0.0"

    # logger
    logger.info(f"OnCloud: {config.general.ON_CLOUD}, using host: {host}")

    # start uvicorn server with directory monitor
    uvicorn.run(
        app="main:app",
        # here in some VPS 127.0.0.1 won't work, need to use 0.0.0.0 instead
        host=host,
        port=config.general.PORT,
        reload=True,
        # hide uvicorn header
        server_header=False,
    )
