from .basic import NotificationSender
from schemes import sql as orm

import telegram
from loguru import logger

__all__ = [
    "send_to_telegram_callback",
]

_telegram_bot = telegram.Bot("7971108750:AAEvkWFMh5iXw-Fip6lmKKRv_crANC_KNpQ")


def _escape_markdown(msg: str):
    return telegram.helpers.escape_markdown(text=msg, version=2)


async def send_to_telegram_callback(sender: NotificationSender):
    """
    Callback (middleware) used to sent notification to telegram
    if user provided a telegram id as their contact info.

    This should be add to `after` signal.
    """

    try:
        assert sender.curr_session is not None
        assert sender.curr_receiver is not None
        assert sender.curr_content is not None
        assert sender.curr_orm_notification is not None

        def get_telegram_ids_of_user(ss):
            orm_receiver = sender.curr_receiver

            tg_id_list: list[int] = []

            assert orm_receiver is not None
            for orm_contact_info in orm_receiver.contact_info:
                if orm_contact_info.contact_type == orm.ContactInfoType.telegram:
                    tg_id_list.append(int(orm_contact_info.contact_info))

            return tg_id_list

        # determine sender name and contact
        sender_name = "Unknown"
        sender_contact_type = None
        sender_contact_info = None

        def get_sender_contact_info(ss):
            if sender.curr_sender is None:
                return ("AHUER.COM", "email", "ahuer@ahuer.com")

            orm_sender = sender.curr_sender
            sender_name = orm_sender.username
            sender_contact_type = None
            sender_contact_info = None
            if len(orm_sender.contact_info) > 0:
                sender_contact_type = orm_sender.contact_info[
                    0
                ].contact_type.value.capitalize()
                sender_contact_info = orm_sender.contact_info[0].contact_info

            return (sender_name, sender_contact_type, sender_contact_info)

        (sender_name, sender_contact_type, sender_contact_info) = (
            await sender.curr_session.run_sync(get_sender_contact_info)
        )

        sender_msg_span = f"📩 From: {_escape_markdown(sender_name)}"
        if sender_contact_info is not None and sender_contact_type is not None:
            sender_msg_span += f" \\({_escape_markdown(sender_contact_type)}: `{_escape_markdown(sender_contact_info)}`\\)"

        # get tg id list
        tg_id_list = await sender.curr_session.run_sync(get_telegram_ids_of_user)

        # construct message
        curr_content = sender.curr_content

        msg_content_span = (
            f"\n>{telegram.helpers.escape_markdown(text=curr_content.message,version=2)}||"
            if curr_content.message != ""
            else ""
        )

        tg_message = (
            f"*🔔 Received a new notification:*"
            f"\n\n*{telegram.helpers.escape_markdown(text=curr_content.title,version=2)}*"
            f"{msg_content_span}"
            f"\n\n_View at [AHUER\\.COM](https://ahuer\\.com/notification/{sender.curr_orm_notification.notification_id})_"
            f"\n{sender_msg_span}"
        )

        # send message using bot
        for tgid in tg_id_list:
            await _telegram_bot.send_message(
                chat_id=tgid, text=tg_message, parse_mode="MarkdownV2"
            )
    except Exception as e:
        logger.exception(e)
        logger.error(f"Failed to send message to Telegram ids: {tg_id_list}")
    finally:
        return True
