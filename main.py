from fastapi import FastAPI
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from fastapi.exceptions import HTTPException
from fastapi.exception_handlers import http_exception_handler

import uvicorn
from loguru import logger

from exception.error import BaseError, BaseErrorOut

import config

# sub routers
from endpoints.auth import auth_router, token_router

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
app.include_router(token_router,  tags=["Token"])
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])


@app.exception_handler(BaseError)
async def base_error_handler(request: Request, exc: BaseError):
    """
    An error handler used to handle all subclass of BaseError class.

    BaseError is a custom base class for error raised in this application.
    """
    return await http_exception_handler(
        request,
        HTTPException(
            status_code=exc.status, detail=exc.to_pydantic_base_error().model_dump()
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
