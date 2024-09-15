from enum import Enum
from typing import Annotated, List

from pydantic import BaseModel
from sqlalchemy import Select, BIGINT, String, ForeignKey, Column, Table
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class SQLBaseModel(DeclarativeBase):
    deleted: Mapped[bool] = mapped_column(default=False)

    type_annotation_map = {int: BIGINT}


# custom column type
IntPrimaryKey = Annotated[int, mapped_column(primary_key=True)]
NormalString = Annotated[str, mapped_column(String(20))]
LongString = Annotated[str, mapped_column(String(100))]
VeryLongString = Annotated[str, mapped_column(String(500))]
ParagraphString = Annotated[str, mapped_column(String(2000))]
TimeStamp = Annotated[int, mapped_column()]


class PaginationConfig(BaseModel):
    """
    Pagination tool class that used to add pagination to select statement::

        stmt : Select
        pagi_conf = PaginationConfig(size=..., limit=...)
        pagi_conf.use_on(stmt)

    Also since this class is extend from ``pydantic.BaseModel``, so it can be used as a dependency of
    FastAPI method::

        @fastApiRouter.get('/test')
        def test_endpoint(pagi_conf : PaginationConfig):
            pass
    """

    # how many rows contains in a page
    size: int = 20

    # zero-index page number
    index: int

    def use_on(self, select_stmt: Select):
        offset = self.size * self.index
        limit = self.size
        return select_stmt.limit(limit).offset(offset)


user_role_association_table = Table(
    "association_users_roles",
    SQLBaseModel.metadata,
    Column("user_id", ForeignKey("user.user_id"), primary_key=True),
    Column("role_id", ForeignKey("role.role_id"), primary_key=True),
)


class User(SQLBaseModel):
    __tablename__ = "user"

    user_id: Mapped[IntPrimaryKey]

    campus_id: Mapped[NormalString] = mapped_column(nullable=True)
    username: Mapped[NormalString]
    password: Mapped[LongString] = mapped_column()
    description: Mapped[LongString] = mapped_column(nullable=True)
    created_at: Mapped[TimeStamp]

    sells: Mapped[List["TradeRecord"]] = relationship(
        back_populates="seller", foreign_keys="TradeRecord.seller_id"
    )
    buys: Mapped[List["TradeRecord"]] = relationship(
        back_populates="buyer", foreign_keys="TradeRecord.buyer_id"
    )
    contact_info: Mapped[List["ContactInfo"]] = relationship(back_populates="user")
    roles: Mapped[List["Role"]] = relationship(
        secondary=user_role_association_table, back_populates="users"
    )


class ContactInfoType(Enum):
    phone = "phone"
    email = "email"


class ContactInfo(SQLBaseModel):
    __tablename__ = "contact_info"

    contact_info_id: Mapped[IntPrimaryKey] = mapped_column()

    user_id: Mapped[int] = mapped_column(ForeignKey("user.user_id"))
    contact_type: Mapped[ContactInfoType] = mapped_column()
    contact_info: Mapped[LongString] = mapped_column(unique=True)

    user: Mapped["User"] = relationship(back_populates="contact_info")


class ItemState(Enum):
    hide = "hide"
    sold = "sold"
    valid = "valid"


association_items_tags = Table(
    "association_items_tags",
    SQLBaseModel.metadata,
    Column("item_id", ForeignKey("item.item_id"), primary_key=True),
    Column("tag_id", ForeignKey("tag.tag_id"), primary_key=True),
)


class Item(SQLBaseModel):
    __tablename__ = "item"

    item_id: Mapped[IntPrimaryKey] = mapped_column()

    user_id: Mapped[int] = mapped_column(ForeignKey("user.user_id"))
    name: Mapped[NormalString]
    description: Mapped[ParagraphString] = mapped_column(nullable=True)
    price: Mapped[int] = mapped_column()
    state: Mapped[ItemState]

    record: Mapped[List["TradeRecord"]] = relationship(back_populates="item")
    questions: Mapped[List["Question"]] = relationship(back_populates="item")
    tags: Mapped[List["Tag"]] = relationship(
        secondary=association_items_tags, back_populates="items"
    )


class TradeState(Enum):
    processing = "processing"
    success = "success"
    cancelled = "cancelled"


class TradeRecord(SQLBaseModel):
    __tablename__ = "trade"

    trade_id: Mapped[IntPrimaryKey]

    seller_id: Mapped[int] = mapped_column(ForeignKey("user.user_id"))
    buyer_id: Mapped[int] = mapped_column(ForeignKey("user.user_id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("item.item_id"))

    created_time: Mapped[TimeStamp]
    review_from_buyer: Mapped[ParagraphString | None]
    review_from_seller: Mapped[ParagraphString | None]
    state: Mapped[TradeState] = mapped_column(default=TradeState.processing)

    seller: Mapped["User"] = relationship(
        back_populates="sells", foreign_keys=[seller_id]
    )
    buyer: Mapped["User"] = relationship(back_populates="buys", foreign_keys=[buyer_id])
    item: Mapped["Item"] = relationship(back_populates="record")


class Question(SQLBaseModel):
    __tablename__ = "question"

    question_id: Mapped[IntPrimaryKey]

    item_id: Mapped[int] = mapped_column(ForeignKey("item.item_id"))

    question: Mapped[VeryLongString]
    created_time: Mapped[TimeStamp]
    answer: Mapped[VeryLongString] = mapped_column(nullable=True)
    public: Mapped[bool] = mapped_column(default=False)

    item: Mapped["Item"] = relationship(back_populates="questions")


class TagsType(Enum):
    original = "original"
    user_created = "user_created"


class Tag(SQLBaseModel):
    __tablename__ = "tag"

    tag_id: Mapped[IntPrimaryKey]

    tag_type: Mapped[TagsType] = mapped_column(default=TagsType.user_created)
    created_time: Mapped[TimeStamp]
    name: Mapped[NormalString]

    items: Mapped[List["Item"]] = relationship(
        secondary=association_items_tags, back_populates="tags"
    )


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

    users: Mapped[List["User"]] = relationship(
        secondary=user_role_association_table, back_populates="roles"
    )
