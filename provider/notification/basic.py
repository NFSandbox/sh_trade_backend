from typing import (
    Annotated,
    cast,
    List,
    Sequence,
    Callable,
    Awaitable,
    Any,
    Literal,
    Union,
    Coroutine,
    TypeVar,
)

from dataclasses import dataclass

from pydantic import BaseModel

from inspect import isawaitable

from asyncer import asyncify
from asyncio import iscoroutine

from loguru import logger
from sqlalchemy import select, func, Column, distinct, union_all, union
from sqlalchemy.orm import selectinload, QueryableAttribute, aliased
from sqlalchemy.sql import and_, or_

from sqlalchemy.ext.asyncio import AsyncSession

from schemes import sql as orm
from schemes import db as db_sche
from schemes import general as gene_sche

from exception import error as exc

from tools.callback_manager import CallbackManager, CallbackInterrupted

from ..database import init_session_maker, session_maker, SessionDep, try_commit
from ..user.core import get_user_contact_info_count
from ..auth import check_user_permission

from .error import (
    NotificationError,
    InvalidReceiverError,
    InvalidContent,
    InvalidSession,
    SenderNotTrusted,
)

__all__ = [
    "NotificationSender",
    "log_middleware",
    "get_notifications",
    "check_user_could_read_notification",
]


class NotificationSender:
    """
    Notification sender class

    Set defaults

    You can directly set the following attributes of a `NotificationSender`
    class instance, which would then used as the default value when not provided.

    - `sender` The default sender of the message
    - `receiver` The default receiver of the message
    - `session` The default session used when adding notification to database

    Do not directly write attributes other than the listed ones.
    """

    callback_manager = CallbackManager[
        ["NotificationSender"],
        Awaitable[Any] | Any,
        Literal["before", "upon", "after"],
    ]()

    def __init__(
        self,
        sender: orm.User | None = None,
        receiver: orm.User | None = None,
        session: AsyncSession | None = None,
        trusted: bool = False,
    ) -> None:
        """
        Initialize a sender

        For more info about default values `sender`, `receiver` and `session`, check out class docstring.

        `trusted` If not True, this sender will not be allowed to send message on behalf of system.
        """
        self.sender = sender
        """
        Sender of this message, could be `None` which indicates 
        the message is sent on behalf of system.
        """
        self.receiver = receiver
        """
        Receiver of this message
        """
        self.session = session
        """
        Default session used when sending notification
        """
        self.trusted = trusted
        """
        If this message sender instance a trusted instance
        """

        # temp value to store the data of next send operation
        # This value is intended to exposed or maybe changed by callbacks
        # in order to control the behaviour of next send
        #
        # notice these variable only valid while `send()` being called.
        self.curr_sender: orm.User | None = None
        self.curr_receiver: orm.User | None = None
        self.curr_content: db_sche.NotificationContentOut | None = None
        self.curr_session: AsyncSession | None = None
        self.curr_orm_notification: orm.Notification | None = None

    def check_validity(self):
        """
        Check the validity based on the current state of temporary values.
        
        Should be called after init_curr(), since the check based on tmp values.
        """
        if self.curr_content is None or not isinstance(
            self.curr_content, db_sche.NotificationContentOut
        ):
            raise InvalidContent(content=self.curr_content)
        if self.curr_receiver is None:
            raise InvalidReceiverError(receiver=self.receiver)
        if self.curr_session is None:
            raise InvalidSession()
        if self.curr_sender is None and not self.trusted:
            raise SenderNotTrusted()

    def clear_curr(self):
        """
        Clear all temporary value of this sender.
        """
        self.curr_sender = None
        self.curr_receiver = None
        self.curr_content = None
        self.curr_session = None
        self.curr_orm_notification = None

    def init_curr(
        self,
        sender: orm.User | None = None,
        receiver: orm.User | None = None,
        content: db_sche.NotificationContentOut | None = None,
        session: AsyncSession | None = None,
        orm_notification: orm.Notification | None = None,
    ):
        """
        Initial current temporary variables from receiving parameter or default
        """
        self.curr_sender = sender if sender is not None else self.sender
        self.curr_receiver = receiver if receiver is not None else self.receiver
        self.curr_session = session if session is not None else self.session
        self.curr_content = content
        self.curr_orm_notification = orm_notification

    async def send(
        self,
        content: db_sche.NotificationContentOut,
        receiver: orm.User | None = None,
        ss: AsyncSession | None = None,
    ) -> orm.Notification | None:
        """
        Send a notification

        Return the ORM instance of sent notification if success
        """

        self.init_curr(content=content, receiver=receiver, session=ss)

        # before callback
        try:
            await self.callback_manager.trigger("before", self)
        except CallbackInterrupted:
            # Callback interrupted signal detected. This means some of callback wants to stop
            # the execution of this message sending process, so return directly.
            logger.debug("Callback interrupted a message sending process.")
            return None

        # validity check
        self.check_validity()

        # construct orm
        assert self.curr_content is not None
        self.curr_orm_notification = orm.Notification(
            sender=self.curr_sender,
            receiver=self.curr_receiver,
            content=self.curr_content.model_dump(),
        )

        # upon callback
        try:
            await self.callback_manager.trigger("upon", self)
        except CallbackInterrupted:
            # Callback interrupted signal detected. This means some of callback wants to stop
            # the execution of this message sending process, so return directly.
            logger.debug("Callback interrupted a message sending process.")
            return None

        # add to database
        assert self.curr_session is not None
        self.curr_session.add(self.curr_orm_notification)

        await try_commit(self.curr_session)

        # after callback
        try:
            await self.callback_manager.trigger("after", self)
        except CallbackInterrupted:
            logger.error(
                "Callback interrput signal received after a message is sent. Singal does no effect"
            )
            pass

        return self.curr_orm_notification


async def log_middleware(sender: NotificationSender):
    assert sender.curr_sender is not None
    assert sender.curr_receiver is not None
    logger.debug(
        f"Notification Sent. {sender.curr_sender.user_id} -> {sender.curr_receiver.user_id}"
    )


async def get_notifications(
    ss: SessionDep,
    user: orm.User,
    time_desc: bool = True,
    sent: bool = False,
    received: bool = True,
    ignore_read: bool = False,
    pagination: gene_sche.PaginationConfig | None = None,
):
    """
    Get notifications of a user

    - `time_desc` Order result by sent/received time desc
    - `sent` `received` Filter by sent/received notifications
    - `pagination` Pagination config, use default if not provided
    """
    # param validation
    if sent == False and received == False:
        raise exc.ParamError(
            param_name="sent, received",
            message="sent and received param could not both be false",
        )

    # force to use a pagination config, if None, use default one.
    pagination = pagination or gene_sche.PaginationConfig()

    # basic stmt, used to generated stmt to retrieve sent and received message.
    _basic_stmt = (
        select(orm.Notification)
        .select_from(orm.User)
        .where(orm.User.user_id == user.user_id)
    )

    # sent and received filter
    sent_notification = _basic_stmt.join(orm.User.sent_notifications)
    received_notification = _basic_stmt.join(orm.User.received_notifications)

    # union sent/received notifications based on param
    # unioned condition will be used as subquery, which determines the basic message range.
    #
    # That is,
    # - if `sent` is selected, then all message sent by user will be included in subquery
    # - if `received` is selected, then similarly.
    #
    # All following processes on the return notifications is based on the result of this subquery.
    selected = []
    if sent:
        selected.append(sent_notification)
    if received:
        selected.append(received_notification)
    all_stmt = union_all(*selected).subquery()
    all_notifications = aliased(orm.Notification, all_stmt)

    stmt = select(all_notifications)

    # order
    if time_desc:
        stmt = stmt.order_by(all_notifications.created_time.desc())

    # ignore read
    if ignore_read:
        stmt = stmt.where(all_notifications.read_time == None)

    # calculate total result under the applied criteria
    total = await ss.scalar(select(func.count(all_notifications.notification_id)))
    total = total or 0

    # pagination
    stmt = pagination.use_on(stmt)

    res = (await ss.scalars(stmt)).all()

    return gene_sche.PaginatedResult(total=total, pagination=pagination, data=res)


async def check_user_could_read_notification(
    ss: AsyncSession, user: orm.User, notification: orm.Notification
) -> None:
    """
    Check if a user has the permission to read a notification

    Checks:

    - If notification has been deleted
    - If user has read:all permission on notification
    - If user is sender or receiver

    Raises

    - `permission_required`
    """
    # not exists
    if notification.deleted_at is not None:
        raise exc.NoResultError(
            message=f"The notification with id {notification.notification_id} is not exists"
        )

    # first check if user has read all permission
    try:
        # if user has read all permission, check pass and return
        p_read_all: bool = await check_user_permission(
            ss, user, {"notification:read:all"}
        )
        return
    except:
        pass

    # check pass if user is sender or receiver
    if (
        notification.sender_id == user.user_id
        or notification.receiver_id == user.user_id
    ):
        return

    raise exc.PermissionError(
        message=f"Insufficient permission to read notification with id {notification.notification_id}"
    )
