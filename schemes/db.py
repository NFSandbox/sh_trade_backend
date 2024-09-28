"""
Declare all schemas related to an SQL entities, used for API I/O validations.
"""

from typing import Optional, Annotated
from schemes import sql as orm

from pydantic import BaseModel, Field, PositiveInt


class UserOut(BaseModel):
    user_id: int
    campus_id: str | None = None
    username: str
    description: str | None = None
    created_time: int

    class Config:
        from_attributes = True


class UserIn(BaseModel):
    username: Annotated[str, Field(max_length=20)]
    password: Annotated[str, Field(max_length=20)]


class ContactInfoIn(BaseModel):
    """Model used to validate incoming contact info"""

    contact_type: orm.ContactInfoType
    contact_info: Annotated[str, Field(max_length=100)]


class ContactInfoOut(ContactInfoIn):
    contact_info_id: int


class TagOut(BaseModel):
    tag_id: int
    tag_type: str
    name: str

    class Config:
        from_attributes = True


class ItemOut(BaseModel):
    """
    Notes

    - When directly validate from ORM class `Item`, the orm relation attribute `tags`
      should be loaded in advance, using `selectinload` or `awaitable_attrs`
    """

    item_id: int
    name: str
    description: str | None
    created_time: int
    price: int
    state: orm.ItemState

    # this field need to be loaded manually in advance when validating from ORM class instance
    tags: list[TagOut] | None = None
    tag_name_list: list[str] | None = None

    class Config:
        from_attributes = True


class ItemIn(BaseModel):
    name: str = Field(max_length=20)
    description: str = Field(max_length=2000)
    price: PositiveInt
    tags: list[Annotated[str, Field(max_length=20)]] | None = None


class ItemInWithId(ItemIn):
    item_id: int


class QuestionIn(BaseModel):
    item_id: int
    asker_id: int | None = None
    question: Annotated[str, Field(max_length=500)]
    public: bool = False
    answer: Annotated[str | None, Field(max_length=500)] = None


class QuestionOut(BaseModel):
    question_id: int
    item_id: int
    question: str
    created_time: int
    answered_time: int | None = None
    answer: str | None = None
    public: bool


class TradeRecordOut(BaseModel):
    trade_id: int
    buyer: UserOut
    item: ItemOut

    created_time: int
    accepted_time: int | None
    confirmed_time: int | None
    completed_time: int | None

    state: orm.TradeState
    cancel_reason: orm.TradeCancelReason | None

    class Config:
        from_attributes = True
