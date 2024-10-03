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

from inspect import isawaitable

from loguru import logger
from sqlalchemy import select, func, Column, distinct
from sqlalchemy.orm import selectinload, QueryableAttribute, aliased
from sqlalchemy.sql import and_, or_
from sqlalchemy import exc as sqlexc
from sqlalchemy.ext.asyncio import AsyncSession

from config import system as sys_conf

from schemes import sql as orm
from schemes import auth as auth_sche
from schemes import db as db_sche
from schemes import general as gene_sche

from asyncer import asyncify
from asyncio import iscoroutine

from tools.callback_manager import CallbackManager, CallbackInterrupted

from ..database import init_session_maker, session_maker, SessionDep, try_commit
from ..user.core import get_user_contact_info_count

from .error import (
    NotificationError,
    InvalidReceiverError,
    InvalidContent,
    InvalidSession,
    SenderNotTrusted,
)


class NotificationSender:
    """
    Notification sender class

    Set defaults

    You can directly set the following attributes of a `NotificationSender`
    class instance, which would then used as the default value when not provided.

    - `sender` The default sender of the message
    - `receiver` The default receiver of the message
    - `session` The default session used when adding notification to database

    Do not directly write attributes other then the listed ones.
    """

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
        self.callback_manager = CallbackManager[
            ["NotificationSender"],
            Awaitable[Any] | Any,
            Literal["before", "upon", "after"],
        ]()

        # temp value to store the data of next send operation
        # This value is intended to exposed or maybe changed by callbacks
        # in order to control the behaviour of next send
        #
        # notice these variable only valid while `send()` being called.
        self.curr_sender = None
        self.curr_receiver = None
        self.curr_content = None
        self.curr_session = None
        self.curr_orm_notification = None

    def check_validity(self):
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
        self.curr_content = content
        self.curr_session = session if session is not None else self.session
        self.curr_orm_notification = orm_notification

    async def send(
        self,
        content: db_sche.NotificationContentOut,
        receiver: orm.User | None = None,
        ss: AsyncSession | None = None,
    ) -> bool:
        """
        Send a notification

        Return `True` if message sent.
        """
        self.init_curr(content=content, receiver=receiver, session=ss)

        # before callback
        try:
            await self.callback_manager.trigger("before", self)
        except CallbackInterrupted:
            return False

        # validity check
        self.check_validity()

        # construct orm
        self.curr_orm_notification = orm.Notification(
            sender=self.sender,
            receiver=receiver,
            content=content.model_dump(),
        )

        # upon callback
        try:
            await self.callback_manager.trigger("upon", self)
        except CallbackInterrupted:
            return False

        # add to database
        assert self.curr_session is not None
        self.curr_session.add(self.curr_orm_notification)

        await try_commit(self.curr_session)

        # after callback
        try:
            await self.callback_manager.trigger("after", self)
        except CallbackInterrupted:
            return True

        return True
