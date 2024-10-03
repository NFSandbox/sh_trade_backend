"""
Declare all schemas related to an SQL entities, used for API I/O validations.
"""

from typing import Optional, Annotated, Literal, Sequence, Dict
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
    accepted_time: int | None = None
    confirmed_time: int | None = None
    completed_time: int | None = None

    state: orm.TradeState
    cancel_reason: orm.TradeCancelReason | None = None

    class Config:
        from_attributes = True


class NotificationContentOut(BaseModel):
    """
    Base pydantic model for Notification.content ORM columns.

    Do not use this base class or all of its subclasses directly.
    Instead, use the union type `NotificationContentOutUnion` or
    `NotificationOut` model class.
    """

    content_type: Literal["text"] = "text"

    title: str
    message: str

    class Config:
        from_attributes = True


class MarkDownNotificationContentOut(NotificationContentOut):
    """
    Notifications that with a markdown content as message.

    Fields

    - `trusted` If this markdown content could be trusted.

    Generally, this field is set to `True` only if the message
    is sent by system.

    If `True`, the HTML tags in content may be directly rendered
    on the client browser
    """

    content_type: Literal["markdown"] = "markdown"

    trusted: bool = False


class URLActionNotificationContentOut(MarkDownNotificationContentOut):
    """
    Notification with a list of URL-redirect actions

    Fields

    - All in `MarkDownNotificationContentOut`
    - `actions` List of URL-redirect actions. Check out `URLAction`
    """

    content_type: Literal["url_action"] = "url_action"

    class URLAction(BaseModel):
        """
        Fields

        - `name` Name of this action
        - `url` URL to redirect to
        - `primary` Whether this action is primary
        - `danger` Whether this action is dangerous
        """

        name: str
        url: str
        primary: bool = False
        danger: bool = False

    actions: Sequence[URLAction]


NotificationContentOutUnion = (
    NotificationContentOut
    | MarkDownNotificationContentOut
    | URLActionNotificationContentOut
)


class NotificationOut(BaseModel):
    """
    Model for notification info.

    `content` field is a discriminated union type. For more info, check
    out docs of each discriminator type.
    """

    notification_id: int
    sender_id: int | None
    receiver_id: int
    created_time: int
    read_time: int | None = None
    content: NotificationContentOutUnion = Field(discriminator="content_type")

    class Config:
        from_attributes = True
        # arbitrary_types_allowed = True
