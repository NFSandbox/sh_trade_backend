import time
from typing import Annotated, cast, List, Sequence

from loguru import logger
from fastapi import APIRouter, Query, Depends, Request, Response, status, Body
from pydantic import BaseModel

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
    get_notifications,
    get_notification_by_id,
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


class GetNotificationIn(BaseModel):
    sent: bool = True
    received: bool = False
    time_desc: bool = True
    ignore_read: bool = False
    pagination: gene_sche.PaginationConfig | None = None


class GetNotificationOut(BaseModel):
    total: int
    pagination: gene_sche.PaginationConfig
    data: List[db_sche.NotificationOut]

    class Config:
        from_attributes = True


@notification_router.get(
    "/get",
    response_model=gene_sche.PaginatedResultOut[list[db_sche.NotificationOut]],
    response_model_exclude_none=True,
)
async def get_user_notifications(
    p: Annotated[bool, Depends(PermissionsChecker({"notification:read:self"}))],
    ss: SessionDep,
    user: CurrentUserDep,
    config: Annotated[GetNotificationIn, Body(embed=True)],
):
    notification_res = await get_notifications(
        ss,
        user,
        time_desc=config.time_desc,
        sent=config.sent,
        received=config.received,
        pagination=config.pagination,
    )

    # def valiate_result(ss):
    #     return gene_sche.PaginationedResultOut[
    #         list[db_sche.NotificationOut]
    #     ].model_validate(notification_res)

    return await gene_sche.validate_result(
        ss,
        notification_res,
        gene_sche.PaginatedResultOut[list[db_sche.NotificationOut]],
    )


@notification_router.post("/read", response_model=db_sche.NotificationOut)
async def mark_notification_read(
    p: Annotated[bool, Depends(PermissionsChecker({"notification:read:self"}))],
    ss: SessionDep,
    user: CurrentUserDep,
    notification_id: Annotated[int, Body(embed=True)],
):
    """
    Mark a notification as read

    Only receiver of the notification could mark that notification as read.

    Raises
    - `not_receiver`
    """
    orm_notification = await get_notification_by_id(ss, notification_id)

    # permission check
    if orm_notification.receiver_id != user.user_id:
        raise exc.PermissionError(
            name="not_receiver",
            message="You could only mark notification as read of your own received notifications.",
        )

    orm_notification.read_time = orm.get_current_timestamp_ms()

    await db_provider.try_commit(ss)

    return orm_notification
