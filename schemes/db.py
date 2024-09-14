from pydantic import BaseModel


class UserOut(BaseModel):
    user_id: int
    campus_id: str
    username: str
    description: str | None
    created_at: int

    class Config:
        from_attributes = True
