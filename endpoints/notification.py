import time
from typing import Annotated, cast, List, Sequence

from loguru import logger
from fastapi import APIRouter, Query, Depends, Request, Response, status, Body

from config import system as sys_config

from schemes import db as db_sche
from schemes import general as gene_sche
from schemes import sql as orm

from provider import user as user_provider
from provider import database as db_provider
from provider import item as item_provider
from provider import fav as fav_provider
from provider.user import CurrentUserDep, CurrentUserOrNoneDep

from provider.database import SessionDep
from exception import error as exc


notification_router = APIRouter()


@notification_router.post("/send", response_model=Sequence[db_sche.NotificationOut])
async def send_notifications(
    ss: SessionDep,
    user: CurrentUserDep,
    receiver_id: Annotated[int, Body()],
    content: Annotated[str, Body(max_length=sys_config.MAX_LENGTH_USER_SENT_MESSAGE)],
):
    """
    Send a message to other
    """
    pass
