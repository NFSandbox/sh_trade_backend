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


class ItemOut(BaseModel):
    item_id: int
    name: str
    description: str | None
    created_time: int
    price: int
    state: orm.ItemState


class ItemIn(BaseModel):
    name: str = Field(max_length=20)
    description: str = Field(max_length=2000)
    price: PositiveInt


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
