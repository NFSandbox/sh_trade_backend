from fastapi import FastAPI
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.exception_handlers import http_exception_handler
from fastapi.openapi.utils import get_openapi
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from fastapi.datastructures import URL

from supertokens_python.framework.fastapi import get_middleware
from supertokens_python import get_all_cors_headers
from provider import supertokens

import uvicorn
from loguru import logger

from exception.error import BaseError, BaseErrorOut, InternalServerError
from exception.error_handler import add_exception_handlers

import config

# sub routers
from endpoints.auth import auth_router, token_router
from endpoints.user import user_router
from endpoints.item import item_router
from endpoints.fav import fav_router
from endpoints.trade import trade_router
from endpoints.notification import notification_router
from endpoints.search import search_router


# include sub routers
app = FastAPI()

# middlewares
app.add_middleware(get_middleware())
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.general.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # + get_all_cors_headers(),
)
app.include_router(token_router, tags=["Token"])
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(user_router, prefix="/user", tags=["User"])
app.include_router(item_router, prefix="/item", tags=["Item"])
app.include_router(fav_router, prefix="/fav", tags=["Favourite"])
app.include_router(trade_router, prefix="/trade", tags=["Trade"])
app.include_router(notification_router, prefix="/notification", tags=["Notification"])
app.include_router(search_router, prefix="/search", tags=["Search"])

# mount static files
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

# add exceptions handlers
add_exception_handlers(app)


# modify openapi settings
def get_custom_openapi_schema():
    openapi_schema = get_openapi(
        title="AHUER.COM API Services",
        description="The backend API services interative docs for [AHUER.COM](https://ahuer.com)",
        version=config.general.BACKEND_API_VER,
        routes=app.routes,
    )
    openapi_schema["info"]["x-logo"] = {
        "url": f"{config.general.GET_BACKEND_URL()}/assets/icon.png",
    }

    return openapi_schema


app.openapi = get_custom_openapi_schema  # type: ignore


@app.get("/doc", include_in_schema=False)
async def swagger_ui_html():
    logger.debug("Custom docs page loaded")
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="AHUER.COM API Services",
        swagger_favicon_url=f"{config.general.GET_BACKEND_URL()}/assets/icon.png",
    )


@app.get("/", include_in_schema=False)
async def redirect_to_doc():
    if config.general.is_dev():
        return RedirectResponse(f"{config.general.GET_BACKEND_URL()}/doc")
    return RedirectResponse("https://doc.api.ahuer.com")


# Start uvicorn server
if __name__ == "__main__":
    # start uvicorn server with directory monitor
    uvicorn.run(
        app="main:app",
        # here in some VPS 127.0.0.1 won't work, need to use 0.0.0.0 instead
        host=config.general.HOST,
        port=config.general.PORT,
        reload=True,
        # hide uvicorn header
        server_header=False,
    )
