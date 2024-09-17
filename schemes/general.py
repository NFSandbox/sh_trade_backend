from pydantic import BaseModel


class BackendInfoOut(BaseModel):
    version: str
    on_cloud: bool


class BlukOpeartionInfo(BaseModel):
    """
    Pydantic schema used when backend need to return the result of bulk operation,
    for example Delete All Items"""

    success: bool = True
    operation: str | None = None
    total: int
