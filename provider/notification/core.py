from schemes import sql as orm
from exception import error as exc

from ..database import SessionDep

__all__ = [
    "get_notification_by_id",
]


async def get_notification_by_id(ss: SessionDep, notification_id: int):
    orm_notification = await ss.get(orm.Notification, notification_id)
    if orm_notification is None or orm_notification.deleted_at is not None:
        raise exc.NoResultError(
            message=f"Could not found notification with id: {notification_id}"
        )

    return orm_notification
