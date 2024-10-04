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
from provider import auth as auth_provider
from provider.auth import PermissionsChecker
from provider.notification import (
    NotificationSender,
    log_middleware,
    send_to_telegram_callback,
)

from provider.database import SessionDep
from exception import error as exc


notification_router = APIRouter()

# add test middleware
NotificationSender.callback_manager.add("after", log_middleware)
NotificationSender.callback_manager.add("after", send_to_telegram_callback)


@notification_router.post(
    "/send",
    response_model=db_sche.NotificationOut,
)
async def send_notifications(
    ss: SessionDep,
    user: CurrentUserDep,
    receiver_id: Annotated[int, Body()],
    title: Annotated[
        str, Body(max_length=sys_config.MAX_LENGTH_USER_SENT_MESSAGE_TITLE)
    ],
    message: Annotated[str, Body(max_length=sys_config.MAX_LENGTH_USER_SENT_MESSAGE)],
    p: Annotated[bool, Depends(PermissionsChecker({"notification:send_from:self"}))],
):
    """
    Send a message to other users. Require `notification:send_from:self` permission
    """
    # get receiver
    receiver = await user_provider.get_user_from_user_id(ss, receiver_id)

    # construct notification sender
    n_sender = NotificationSender(session=ss, sender=user, receiver=receiver)
    orm_notification = await n_sender.send(
        content=db_sche.NotificationContentOut(title=title, message=message)
    )

    return await ss.run_sync(
        lambda x: db_sche.NotificationOut.model_validate(orm_notification)
    )
