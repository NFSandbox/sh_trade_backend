from typing import Optional, Annotated

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
