from typing import Any
from exception import error as app_exc
from schemes import sql as orm

__all__ = [
    "NotificationError",
    "InvalidReceiverError",
]


class NotificationError(app_exc.InternalServerError):
    def __init__(
        self,
        name: str = "notification_error",
        message: str = "Error occurred when sending notifications.",
        status: int = 500,
    ) -> None:
        super().__init__(name, message, status)


class SenderNotTrusted(NotificationError):
    def __init__(
        self,
        name: str = "sender_not_trusted",
        message: str = "Could not send notification on behalf of system with a non-trusted sender. "
        "To send message on behalf of system, set trusted=True when initializing a sender.",
    ) -> None:
        super().__init__(name=name, message=message)


class InvalidContent(NotificationError):
    def __init__(
        self,
        content: Any,
        name: str = "invalid_content",
        message: str = "Could not send notification due to invalid content. ",
    ) -> None:
        message += f"Content: {content}"
        super().__init__(name=name, message=message)


class InvalidSession(NotificationError):
    def __init__(
        self,
        name: str = "invalid_session",
        message: str = "Could not send notification due to invalid session. ",
    ) -> None:
        super().__init__(name=name, message=message)


class InvalidReceiverError(NotificationError):
    def __init__(
        self,
        name: str = "invalid_receiver",
        receiver: orm.User | None = None,
        message: str = "Could not send notification due to invalid receiver. ",
    ) -> None:
        message += f"Receiver: {receiver}"

        super().__init__(name=name, message=message)
