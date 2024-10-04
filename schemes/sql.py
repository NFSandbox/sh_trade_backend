"""
Declare all SQLAlchemy ORM classes, relationships and associations.
"""

from datetime import datetime, UTC
from enum import Enum
from typing import Annotated, List, Set, cast
from loguru import logger

from pydantic import BaseModel

# sqlalchemy basics
from sqlalchemy import Select, BIGINT, String, JSON, ForeignKey, Column, Table
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    MappedAsDataclass,
)
from sqlalchemy.sql.type_api import TypeEngine
from sqlalchemy.ext.asyncio import AsyncSession

# sqlalchemy association proxy extensions
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.associationproxy import AssociationProxy

# easy soft delete
from sqlalchemy_easy_softdelete.mixin import generate_soft_delete_mixin_class
from sqlalchemy_easy_softdelete.hook import IgnoredTable

# sqlalchemy json
from sqlalchemy_json import NestedMutableJson


# using datetime to get utc timestamp
# for more info, check out:
# https://blog.miguelgrinberg.com/post/it-s-time-for-a-change-datetime-utcnow-is-now-deprecated
def get_current_timestamp_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


# Create a Class that inherits from our class builder
class SoftDeleteMixin(
    generate_soft_delete_mixin_class(
        # This table will be ignored by the hook
        # even if the table has the soft-delete column
        ignored_tables=[
            IgnoredTable(table_schema="public", name="cars"),
        ],
        delete_method_default_value=get_current_timestamp_ms,
        deleted_field_type=cast("TypeEngine", BIGINT),
    )
):
    # type hint for autocomplete IDE support
    deleted_at: Mapped[int | None]

    def delete(self):
        super().delete()

    def undelete(self):
        super().undelete()


class SQLBaseModel(DeclarativeBase, AsyncAttrs, SoftDeleteMixin):
    type_annotation_map = {int: BIGINT}


# custom column type
IntPrimaryKey = Annotated[int, mapped_column(primary_key=True)]
NormalString = Annotated[str, mapped_column(String(20))]
LongString = Annotated[str, mapped_column(String(100))]
VeryLongString = Annotated[str, mapped_column(String(500))]
ParagraphString = Annotated[str, mapped_column(String(2000))]
TimeStamp = Annotated[int, mapped_column(default=get_current_timestamp_ms)]
NullableTimeStamp = Annotated[int, mapped_column(nullable=True, default=None)]


class AssociationUserRole(SQLBaseModel):
    __tablename__ = "association_users_roles"

    association_users_roles_id: Mapped[IntPrimaryKey] = mapped_column(
        autoincrement=True
    )

    user_id: Mapped[IntPrimaryKey] = mapped_column(ForeignKey("user.user_id"))
    role_id: Mapped[IntPrimaryKey] = mapped_column(ForeignKey("role.role_id"))

    created_time: Mapped[TimeStamp]

    user: Mapped["User"] = relationship(back_populates="association_roles")
    role: Mapped["Role"] = relationship(back_populates="association_users")
    role_name: AssociationProxy[str] = association_proxy("role", "role_name")


class User(SQLBaseModel):
    __tablename__ = "user"

    user_id: Mapped[IntPrimaryKey]

    campus_id: Mapped[NormalString | None]
    username: Mapped[LongString]
    description: Mapped[LongString] = mapped_column(nullable=True)
    created_time: Mapped[TimeStamp]

    buys: Mapped[List["TradeRecord"]] = relationship(
        back_populates="buyer", foreign_keys="TradeRecord.buyer_id"
    )
    contact_info: Mapped[List["ContactInfo"]] = relationship(back_populates="user")
    items: Mapped[List["Item"]] = relationship(back_populates="seller")

    # user-role associations
    association_roles: Mapped[List["AssociationUserRole"]] = relationship(
        back_populates="user",
    )
    roles: AssociationProxy[List["Role"]] = association_proxy(
        "association_roles",
        "role",
        creator=lambda role_orm: AssociationUserRole(role=role_orm),
    )
    role_name_list: AssociationProxy[List[str]] = association_proxy(
        "association_roles",
        "role_name",
    )

    # relation about fav items
    association_fav_items: Mapped[List["AssociationUserFavouriteItem"]] = relationship(
        back_populates="user"
    )
    fav_items: AssociationProxy[List["Item"]] = association_proxy(
        "association_fav_items",
        "item",
        creator=lambda item_orm: AssociationUserFavouriteItem(item=item_orm),
    )

    # super token id relationship
    supertoken_ids: Mapped[List["SuperTokenUser"]] = relationship(back_populates="user")

    # notification relationship
    sent_notifications: Mapped[List["Notification"]] = relationship(
        "Notification", back_populates="sender", foreign_keys="Notification.sender_id"
    )
    received_notifications: Mapped[List["Notification"]] = relationship(
        "Notification",
        back_populates="receiver",
        foreign_keys="Notification.receiver_id",
    )

    async def verify_role(self, ss: AsyncSession, roles: str | list[str]) -> bool:
        """Check if this user has some roles

        Args:
            roles: A str or a list of str. Represents the allowed roles for this verification

        Returns:
            `True`: If this user has **one of the allowedroles** in the `roles` parameters
            `False`: Else case

        Notes:

        Deleted roles will be ignored.

        Please ensure the relavant session of this instance is still active,
        since the `roles` relationship info is retrieved using *Awaitable Attributes*.
        """
        # get user roles
        roles_of_this_user: list[Role] = await ss.run_sync(lambda ss: self.roles)

        def _check_user_has_allowed_roles(ss):
            # iterate through user's roles.
            # once one of the user role is in the allowed role list, pass the test
            for user_role in roles_of_this_user:
                if user_role.role_name in roles:
                    return True

            return False

        return await ss.run_sync(lambda ss: _check_user_has_allowed_roles(ss))


class SuperTokenUser(SQLBaseModel):
    """
    Store the user-super_token_user mapping relation
    """

    __tablename__ = "supertoken_user"

    user_id: Mapped[int] = mapped_column(ForeignKey("user.user_id"))
    supertoken_id: Mapped[LongString] = mapped_column(primary_key=True)
    created_time: Mapped[TimeStamp]

    user: Mapped["User"] = relationship(
        back_populates="supertoken_ids",
    )


class ContactInfoType(Enum):
    phone = "phone"
    email = "email"
    telegram = "telegram"


class ContactInfo(SQLBaseModel):
    __tablename__ = "contact_info"

    contact_info_id: Mapped[IntPrimaryKey] = mapped_column()

    user_id: Mapped[int] = mapped_column(ForeignKey("user.user_id"))
    contact_type: Mapped[ContactInfoType] = mapped_column()
    contact_info: Mapped[LongString] = mapped_column()

    user: Mapped["User"] = relationship(back_populates="contact_info")


class ItemState(str, Enum):
    hide = "hide"
    sold = "sold"
    valid = "valid"


class Item(SQLBaseModel):
    __tablename__ = "item"

    item_id: Mapped[IntPrimaryKey] = mapped_column()

    user_id: Mapped[int] = mapped_column(ForeignKey("user.user_id"))

    name: Mapped[NormalString]
    description: Mapped[ParagraphString] = mapped_column(nullable=True)
    created_time: Mapped[TimeStamp] = mapped_column(default=get_current_timestamp_ms)
    price: Mapped[int] = mapped_column()
    state: Mapped[ItemState] = mapped_column(default=ItemState.valid)

    trades: Mapped[List["TradeRecord"]] = relationship(back_populates="item")
    processing_trade: Mapped["TradeRecord | None"] = relationship(
        "TradeRecord",
        primaryjoin="and_(Item.item_id==TradeRecord.item_id, TradeRecord.state=='processing')",
        viewonly=True,
    )

    questions: Mapped[List["Question"]] = relationship(back_populates="item")
    tags: AssociationProxy[List["Tag"]] = association_proxy(
        "association_tags",
        "tag",
        creator=lambda tag_orm: AssociationItemTag(tag=tag_orm),
    )
    tag_name_list: AssociationProxy[List[str]] = association_proxy(
        "association_tags",
        "tag_name",
        creator=lambda tag_str: AssociationItemTag(tag_name=tag_str),
    )
    association_tags: Mapped[List["AssociationItemTag"]] = relationship(
        back_populates="item"
    )
    seller: Mapped["User"] = relationship(back_populates="items")

    # relationships about fav user
    association_faved_by_users: Mapped[List["AssociationUserFavouriteItem"]] = (
        relationship(back_populates="item")
    )
    faved_users: AssociationProxy[List["User"]] = association_proxy(
        "association_faved_by_users",
        "user",
        creator=lambda user_orm: AssociationUserFavouriteItem(user=user_orm),
    )


class TradeState(Enum):
    pending = "pending"
    processing = "processing"
    success = "success"
    cancelled = "cancelled"


class TradeCancelReason(Enum):
    seller_rejected = "seller_rejected"
    seller_accept_timeout = "seller_accept_timeout"
    cancelled_by_buyer = "cancelled_by_buyer"
    cancelled_by_seller = "cancelled_by_seller"
    seller_confirm_timeout = "seller_confirm_timeout"


class TradeRecord(SQLBaseModel):
    __tablename__ = "trade"

    trade_id: Mapped[IntPrimaryKey]

    buyer_id: Mapped[int] = mapped_column(ForeignKey("user.user_id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("item.item_id"))

    created_time: Mapped[TimeStamp]
    accepted_time: Mapped[NullableTimeStamp]
    confirmed_time: Mapped[NullableTimeStamp]
    completed_time: Mapped[NullableTimeStamp]

    review_from_buyer: Mapped[ParagraphString | None] = mapped_column(nullable=True)
    review_from_seller: Mapped[ParagraphString | None] = mapped_column(nullable=True)
    state: Mapped[TradeState] = mapped_column(default=TradeState.pending)
    cancel_reason: Mapped[TradeCancelReason | None] = mapped_column(nullable=True)

    buyer: Mapped["User"] = relationship(back_populates="buys", foreign_keys=[buyer_id])
    item: Mapped["Item"] = relationship(back_populates="trades")


class Question(SQLBaseModel):
    __tablename__ = "question"

    question_id: Mapped[IntPrimaryKey]

    item_id: Mapped[int] = mapped_column(ForeignKey("item.item_id"))
    asker_id: Mapped[int] = mapped_column(ForeignKey("user.user_id"))

    question: Mapped[VeryLongString]
    created_time: Mapped[TimeStamp] = mapped_column(default=get_current_timestamp_ms)
    answered_time: Mapped[NullableTimeStamp]
    answer: Mapped[VeryLongString] = mapped_column(nullable=True)
    public: Mapped[bool] = mapped_column(default=False)

    item: Mapped["Item"] = relationship(back_populates="questions")
    asker: Mapped["User"] = relationship(User)


class TagsType(Enum):
    original = "original"
    user_created = "user_created"


class Tag(SQLBaseModel):
    __tablename__ = "tag"

    tag_id: Mapped[IntPrimaryKey]

    tag_type: Mapped[TagsType] = mapped_column(default=TagsType.user_created)
    created_time: Mapped[TimeStamp]
    name: Mapped[NormalString]

    association_items: Mapped[List["AssociationItemTag"]] = relationship(
        back_populates="tag"
    )
    items: AssociationProxy[List["Item"]] = association_proxy(
        "association_items",
        "item",
        creator=lambda item_orm: AssociationItemTag(item=item_orm),
    )


class AssociationItemTag(SQLBaseModel):

    __tablename__ = "association_items_tags"

    association_items_tags_id: Mapped[IntPrimaryKey] = mapped_column(autoincrement=True)
    item_id: Mapped[IntPrimaryKey] = mapped_column(ForeignKey("item.item_id"))
    tag_id: Mapped[IntPrimaryKey] = mapped_column(ForeignKey("tag.tag_id"))
    created_at: Mapped[TimeStamp]

    tag: Mapped["Tag"] = relationship(back_populates="association_items")
    item: Mapped["Item"] = relationship(back_populates="association_tags")

    tag_name: AssociationProxy[str] = association_proxy("tag", "name")


class AssociationUserFavouriteItem(SQLBaseModel):
    __tablename__ = "association_user_favourite_item"

    association_user_favourite_item_id: Mapped[IntPrimaryKey] = mapped_column(
        autoincrement=True
    )

    user_id: Mapped[IntPrimaryKey] = mapped_column(ForeignKey("user.user_id"))
    item_id: Mapped[IntPrimaryKey] = mapped_column(ForeignKey("item.item_id"))
    created_at: Mapped[TimeStamp]

    user: Mapped["User"] = relationship(back_populates="association_fav_items")
    item: Mapped["Item"] = relationship(back_populates="association_faved_by_users")


class Role(SQLBaseModel):
    """
    ORM Class for role info.

    Parameters:

    Check out class member

    Notice:

    - ``role_name`` and ``role_title`` are two different things.
      ``role_name`` is used in code to check if a user has some kinds of permission.
      ``role_title`` is a user-readable text, and may be used to display in UI to inform user.
    """

    __tablename__ = "role"

    role_id: Mapped[IntPrimaryKey]
    role_name: Mapped[NormalString]
    role_title: Mapped[NormalString]

    # user-role associations
    association_users: Mapped[List["AssociationUserRole"]] = relationship(
        back_populates="role"
    )
    user: AssociationProxy[List["User"]] = association_proxy(
        "association_users",
        "user",
        creator=lambda user_orm: AssociationUserRole(user=user_orm),
    )


class Notification(SQLBaseModel):

    __tablename__ = "notification"

    notification_id: Mapped[IntPrimaryKey] = mapped_column(autoincrement=True)

    sender_id: Mapped[int] = mapped_column(
        ForeignKey("user.user_id"), nullable=True, default=None
    )
    receiver_id: Mapped[int] = mapped_column(ForeignKey("user.user_id"))
    created_time: Mapped[TimeStamp]
    read_time: Mapped[NullableTimeStamp]
    content: Mapped[dict] = mapped_column(NestedMutableJson)

    # relationships
    sender: Mapped["User | None"] = relationship(
        back_populates="sent_notifications", foreign_keys=sender_id
    )
    receiver: Mapped["User"] = relationship(
        back_populates="received_notifications", foreign_keys=receiver_id
    )
