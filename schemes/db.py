from typing import Optional, Annotated
from schemes import sql as orm

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    user_id: int
    campus_id: Optional[str]
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
