from asyncio import get_running_loop

from sqlalchemy.orm import Session

import telegram
from loguru import logger

from schemes import sql as orm
from schemes import db as db_sche

from config import general as gene_config
from provider.database import SessionDep, try_commit, session_manager

from .basic import NotificationSender

__all__ = [
    "send_to_telegram_callback",
]

_telegram_bot = telegram.Bot(gene_config.TG_BOT_TOKEN)


def _escape_markdown(msg: str):
    return telegram.helpers.escape_markdown(text=msg, version=2)


async def send_to_telegram_callback(sender: NotificationSender):
    """
    Callback (middleware) used to sent notification to telegram
    if user provided a telegram id as their contact info.

    This should be add to `after` signal.

    Since TG message sending is time-consuming, this middleware
    will return once the task has been added to async event loop.
    And this middleware will always return `True`.
    """
    try:
        assert sender.curr_content is not None
        loop = get_running_loop()
        loop.create_task(
            _send_to_telegram_callback(
                message_sender=sender.curr_sender,
                message_receiver=sender.receiver,
                message_content=sender.curr_content,
                orm_notification=sender.curr_orm_notification,
            )
        )
    except Exception as e:
        logger.exception(e)
        logger.error(
            "Failed to send notification to telegram due to error occurred above."
        )
    logger.debug("Telegram middleware returned")
    return True


async def _send_to_telegram_callback(
    message_sender: orm.User | None,
    message_receiver: orm.User,
    message_content: db_sche.NotificationContentOut,
    orm_notification: orm.Notification,
):
    try:

        def get_telegram_ids_of_user(ss: Session):
            # rebound orm to this session
            nonlocal message_receiver
            message_receiver = ss.get(orm.User, message_receiver.user_id)

            tg_id_list: list[int] = []

            assert message_receiver is not None
            for orm_contact_info in message_receiver.contact_info:
                if orm_contact_info.contact_type == orm.ContactInfoType.telegram:
                    tg_id_list.append(int(orm_contact_info.contact_info))

            return tg_id_list

        # determine sender name and contact
        sender_name = "Unknown"
        sender_contact_type = None
        sender_contact_info = None

        def get_sender_contact_info(ss: Session):

            nonlocal message_sender

            if message_sender is None:
                return ("AHUER.COM", "email", "ahuer@ahuer.com")

            # rebound object to this session
            message_sender = ss.get(orm.User, message_sender.user_id)
            assert message_sender is not None

            sender_name = message_sender.username
            sender_contact_type = None
            sender_contact_info = None

            if len(message_sender.contact_info) > 0:
                sender_contact_type = message_sender.contact_info[
                    0
                ].contact_type.value.capitalize()
                sender_contact_info = message_sender.contact_info[0].contact_info

            return (sender_name, sender_contact_type, sender_contact_info)

        # generate new database session
        async with session_manager() as ss:
            (sender_name, sender_contact_type, sender_contact_info) = await ss.run_sync(
                get_sender_contact_info
            )

            sender_msg_span = f"📩 From: {_escape_markdown(sender_name)}"
            if sender_contact_info is not None and sender_contact_type is not None:
                sender_msg_span += f" \\({_escape_markdown(sender_contact_type)}: `{_escape_markdown(sender_contact_info)}`\\)"

            # get tg id list
            tg_id_list = await ss.run_sync(get_telegram_ids_of_user)

        msg_content_span = (
            f"\n>{telegram.helpers.escape_markdown(text=message_content.message,version=2)}||"
            if message_content.message != ""
            else ""
        )

        debug_span = ""
        if gene_config.is_dev():
            debug_span = "\n\n_⚠️ Message comes from dev environment\\._"

        tg_message = (
            f"*🔔 Received a new notification:*"
            f"\n\n*{telegram.helpers.escape_markdown(text=message_content.title,version=2)}*"
            f"{msg_content_span}"
            f"\n\n_View at [AHUER\\.COM](https://ahuer\\.com/notification/{orm_notification.notification_id})_"
            f"\n{sender_msg_span}"
            f"{debug_span}"
        )

        # send message using bot
        for tgid in tg_id_list:
            await _telegram_bot.send_message(
                chat_id=tgid, text=tg_message, parse_mode="MarkdownV2"
            )

        logger.debug("Telegram message sent")

    except Exception as e:
        logger.exception(e)
        logger.error(f"Failed to send message to Telegram ids: {tg_id_list}")
    finally:
        return True
